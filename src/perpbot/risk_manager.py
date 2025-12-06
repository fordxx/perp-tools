from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from perpbot.models import Position, PriceQuote, Side

logger = logging.getLogger(__name__)


class RiskManager:
    """账户层面的风险控制，覆盖回撤、敞口与异常行情。

    增强点：
    - 全局开关 + 人工 override：自动暂停后可人工授予短期继续交易权限。
    - 风险模式档位：conservative / balanced / aggressive，不同档位对应 edge、亏损、波动容忍度以及评分权重。
    - 交易额约束：支持单笔 / 同时在途名义金额上限，日内亏损与目标成交量跟踪。
    - 综合评分：基于安全与成交贡献计算 final_score，不达标直接拦截。
    """

    def __init__(
        self,
        assumed_equity: float,
        max_drawdown_pct: float = 0.1,
        max_consecutive_failures: int = 3,
        max_symbol_exposure_pct: float = 0.2,
        enforce_direction_consistency: bool = True,
        freeze_threshold_pct: float = 0.005,
        freeze_window_seconds: int = 1,
        max_trade_risk_pct: float = 0.05,
        daily_loss_limit_pct: float = 0.08,
        max_slippage_bps: float = 50.0,
        order_fill_timeout_seconds: int = 5,
        circuit_breaker_failures: int = 3,
        balance_concentration_pct: float = 0.5,
        *,
        enabled: bool = True,
        risk_mode: str = "balanced",
        risk_mode_presets: Optional[Dict[str, Dict[str, float]]] = None,
        manual_override_minutes: int = 0,
        manual_override_trades: int = 0,
        daily_loss_limit: float = 0.0,
        daily_volume_target: float = 0.0,
        max_notional_per_trade: float = 0.0,
        max_total_notional_in_flight: float = 0.0,
    ):
        self.assumed_equity = max(assumed_equity, 1.0)
        self.peak_equity = self.assumed_equity
        self.last_equity = self.assumed_equity
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_failures = max_consecutive_failures
        self.max_symbol_exposure_pct = max_symbol_exposure_pct
        self.enforce_direction_consistency = enforce_direction_consistency
        self.freeze_threshold_pct = freeze_threshold_pct
        self.freeze_window = timedelta(seconds=freeze_window_seconds)
        self.max_trade_risk_pct = max_trade_risk_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct

        self.enabled = enabled
        self.risk_mode = risk_mode
        self.risk_mode_presets = risk_mode_presets or {
            "conservative": {
                "min_expected_edge_bps": 5.0,
                "max_acceptable_loss_bps": 1.0,
                "volatility_threshold": 0.004,
                "safety_weight": 0.8,
                "volume_weight": 0.2,
                "final_score_threshold": 75.0,
            },
            "balanced": {
                "min_expected_edge_bps": 3.0,
                "max_acceptable_loss_bps": 2.0,
                "volatility_threshold": 0.006,
                "safety_weight": 0.65,
                "volume_weight": 0.35,
                "final_score_threshold": 70.0,
            },
            "aggressive": {
                "min_expected_edge_bps": 1.5,
                "max_acceptable_loss_bps": 3.5,
                "volatility_threshold": 0.01,
                "safety_weight": 0.55,
                "volume_weight": 0.45,
                "final_score_threshold": 60.0,
            },
        }
        self.manual_override_until: Optional[datetime] = None
        self.manual_override_trades = max(manual_override_trades, 0)
        if manual_override_minutes > 0:
            self.manual_override_until = datetime.utcnow() + timedelta(minutes=manual_override_minutes)
        self.daily_loss_limit = daily_loss_limit
        self.daily_volume_target = daily_volume_target
        self.max_notional_per_trade = max_notional_per_trade
        self.max_total_notional_in_flight = max_total_notional_in_flight
        self.notional_in_flight = 0.0
        self.daily_volume = 0.0

        self.consecutive_failures = 0
        self.trading_halted = False
        self.auto_paused = False
        self.halt_reason: Optional[str] = None
        self._frozen_until: Optional[datetime] = None
        self._freeze_reason: Optional[str] = None
        self._last_price: Dict[str, Tuple[float, datetime]] = {}
        self._daily_anchor_equity = self.assumed_equity
        self._daily_anchor_date = datetime.utcnow().date()
        self.max_slippage_bps = max_slippage_bps
        self.order_fill_timeout_seconds = order_fill_timeout_seconds
        self.circuit_breaker_failures = circuit_breaker_failures
        self.balance_concentration_pct = balance_concentration_pct
        self.exchange_failures: Dict[str, int] = {}

    def collect_positions(self, exchanges: Iterable) -> List[Position]:
        positions: List[Position] = []
        for ex in exchanges:
            try:
                positions.extend(ex.get_account_positions())
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.debug("获取 %s 持仓失败: %s", getattr(ex, "name", "unknown"), exc)
        return positions

    def update_equity(self, positions: Sequence[Position], quotes: Optional[Iterable[PriceQuote]] = None) -> float:
        quote_map = {q.symbol: q for q in quotes} if quotes else {}
        now = datetime.utcnow()
        if now.date() != self._daily_anchor_date:
            # 每日 UTC 0 点重置基准，用于监控当日亏损
            self._daily_anchor_date = now.date()
            self._daily_anchor_equity = self.last_equity or self.assumed_equity

        equity = self.assumed_equity
        for pos in positions:
            price = quote_map.get(pos.order.symbol).mid if quote_map.get(pos.order.symbol) else pos.order.price
            direction = 1 if pos.order.side == "buy" else -1
            equity += direction * pos.order.size * price
        self.last_equity = max(equity, 0.0)
        self.peak_equity = max(self.peak_equity, self.last_equity)
        drawdown = (self.peak_equity - self.last_equity) / self.peak_equity if self.peak_equity else 0.0
        if drawdown >= self.max_drawdown_pct:
            self.auto_paused = True
            self.trading_halted = True
            self.halt_reason = f"触及最大回撤: {drawdown * 100:.2f}%"
            logger.warning(self.halt_reason)

        if self.daily_loss_limit_pct and self._daily_anchor_equity:
            daily_loss = (self._daily_anchor_equity - self.last_equity) / self._daily_anchor_equity
            if daily_loss >= self.daily_loss_limit_pct:
                self.auto_paused = True
                self.trading_halted = True
                self.halt_reason = f"触及当日亏损上限: {daily_loss * 100:.2f}%"
                logger.warning(self.halt_reason)
        if self.daily_loss_limit > 0 and (self._daily_anchor_equity - self.last_equity) >= self.daily_loss_limit:
            self.auto_paused = True
            self.trading_halted = True
            self.halt_reason = f"当日净亏损超过绝对上限 {self.daily_loss_limit:.2f}"
            logger.warning(self.halt_reason)
        return self.last_equity

    def evaluate_market(self, quotes: Iterable[PriceQuote]) -> None:
        now = datetime.utcnow()
        for quote in quotes:
            mid = quote.mid
            last_price = self._last_price.get(quote.symbol)
            if last_price:
                prev_price, ts = last_price
                if now - ts <= self.freeze_window and prev_price > 0:
                    move = abs(mid - prev_price) / prev_price
                    if move >= self.freeze_threshold_pct:
                        self._frozen_until = now + self.freeze_window
                        self._freeze_reason = (
                            f"Market freeze triggered for {quote.symbol}: {move * 100:.2f}% move in {self.freeze_window.total_seconds():.0f}s"
                        )
                        logger.warning(self._freeze_reason)
            self._last_price[quote.symbol] = (mid, now)

    def can_trade(
        self,
        symbol: str,
        side: Side,
        size: float,
        price: float,
        positions: Sequence[Position],
        quotes: Optional[Iterable[PriceQuote]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not self.enabled:
            return False, "全局开关关闭，已停止交易"
        if self.auto_paused and not self._override_active():
            return False, self.halt_reason or "风控暂停"
        if self._is_frozen():
            return False, self._freeze_reason
        if self.max_consecutive_failures and self.consecutive_failures >= self.max_consecutive_failures:
            return False, "连续失败次数已达上限"

        equity = max(self.last_equity, self.assumed_equity)
        notional = size * price
        if self.max_trade_risk_pct and equity > 0 and notional > equity * self.max_trade_risk_pct:
            return False, f"名义金额超过单笔上限 {self.max_trade_risk_pct * 100:.2f}%"
        if self.max_notional_per_trade and notional > self.max_notional_per_trade:
            return False, f"名义金额超过单笔硬上限 {self.max_notional_per_trade:.2f}"
        if self.max_total_notional_in_flight and (self.notional_in_flight + notional) > self.max_total_notional_in_flight:
            return False, "在途名义金额超限"

        net_size, _ = self._symbol_net_and_exposure(symbol, positions, quotes, price)
        direction = 1 if side == "buy" else -1
        new_net = net_size + direction * size
        new_exposure = abs(new_net) * price

        if self.max_symbol_exposure_pct and equity > 0 and new_exposure > equity * self.max_symbol_exposure_pct:
            return False, f"{symbol} 的敞口超过上限"

        if self.enforce_direction_consistency and abs(net_size) > 1e-9 and (net_size > 0) != (direction > 0):
            return False, "持仓方向与下单方向冲突"

        approved, reason = self._override_gate()
        if not approved:
            return False, reason

        return True, None

    def evaluate_plan(
        self,
        *,
        notional: float,
        expected_edge_bps: float,
        expected_loss_bps: float,
        volatility: float,
        latency_ms: float,
        slippage_bps: float,
        volume_contrib: float = 0.0,
    ) -> Tuple[bool, str, float, float, float]:
        """按当前 risk_mode 计算综合评分，返回 (通过?, 原因, final_score, safety_score, volume_score)。"""

        preset = self.risk_mode_presets.get(self.risk_mode, self.risk_mode_presets.get("balanced", {}))
        min_edge = preset.get("min_expected_edge_bps", 0.0)
        max_loss = preset.get("max_acceptable_loss_bps", 10_000.0)
        vol_th = preset.get("volatility_threshold", 1.0)
        w1 = preset.get("safety_weight", 0.6)
        w2 = preset.get("volume_weight", 0.4)
        threshold = preset.get("final_score_threshold", 70.0)

        if expected_edge_bps < min_edge:
            return False, f"期望 edge {expected_edge_bps:.3f}bps 低于档位下限 {min_edge:.3f}", 0.0, 0.0, 0.0
        if expected_loss_bps > max_loss:
            return False, f"预估亏损 {expected_loss_bps:.3f}bps 超过档位上限 {max_loss:.3f}", 0.0, 0.0, 0.0

        vol_penalty = max(0.0, (volatility - vol_th) / max(vol_th, 1e-9))
        slippage_penalty = slippage_bps / 100.0
        latency_penalty = latency_ms / 1000.0
        loss_penalty = expected_loss_bps / max(max_loss, 1e-9)

        safety_score = max(0.0, 100.0 - (vol_penalty * 30 + slippage_penalty * 10 + latency_penalty * 5 + loss_penalty * 25))
        target = self.daily_volume_target if self.daily_volume_target > 0 else notional
        volume_score = min(100.0, (volume_contrib or notional) / max(target, 1e-9) * 100.0)
        final_score = w1 * safety_score + w2 * volume_score

        if final_score < threshold:
            return False, f"综合评分 {final_score:.1f} 低于阈值 {threshold:.1f}", final_score, safety_score, volume_score
        return True, "ok", final_score, safety_score, volume_score

    def set_risk_mode(self, mode: str) -> None:
        if mode not in self.risk_mode_presets:
            logger.warning("风险模式 %s 未配置，保持原档位 %s", mode, self.risk_mode)
            return
        logger.info("切换风险模式为 %s", mode)
        self.risk_mode = mode

    def enable(self) -> None:
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False
        self.auto_paused = True
        self.halt_reason = "人工关闭系统"

    def manual_override(self, minutes: int = 0, trades: int = 0) -> None:
        now = datetime.utcnow()
        if minutes > 0:
            self.manual_override_until = now + timedelta(minutes=minutes)
        if trades > 0:
            self.manual_override_trades = trades
        logger.warning(
            "人工 override 生效：分钟=%s, 笔数=%s, 当前亏损=%.4f, 当日成交=%.2f, 模式=%s",
            minutes,
            trades,
            (self._daily_anchor_equity - self.last_equity),
            self.daily_volume,
            self.risk_mode,
        )

    def record_volume(self, volume: float) -> None:
        self.daily_volume += max(volume, 0.0)

    def register_in_flight(self, notional: float) -> Tuple[bool, Optional[str]]:
        if self.max_total_notional_in_flight and (self.notional_in_flight + notional) > self.max_total_notional_in_flight:
            return False, "在途名义金额超限"
        self.notional_in_flight += notional
        return True, None

    def release_in_flight(self, notional: float) -> None:
        self.notional_in_flight = max(self.notional_in_flight - notional, 0.0)

    def is_frozen(self) -> bool:
        return self._is_frozen()

    def freeze_reason(self) -> Optional[str]:
        if self._is_frozen():
            return self._freeze_reason
        return None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        logger.warning("记录一次失败，连续失败=%s", self.consecutive_failures)
        if self.max_consecutive_failures and self.consecutive_failures >= self.max_consecutive_failures:
            self.auto_paused = True
            self.halt_reason = "连续失败次数超限，停止交易"
            logger.error(self.halt_reason)

    def record_success(self) -> None:
        if self.consecutive_failures:
            logger.info("成功成交，连续失败计数清零")
        self.consecutive_failures = 0

    def check_slippage(self, intended_price: float, current_price: float) -> Tuple[bool, Optional[str]]:
        move = abs(current_price - intended_price) / max(intended_price, 1e-9)
        if move * 10_000 > self.max_slippage_bps:
            return False, f"滑点 {move*100:.3f}% 超过上限"
        return True, None

    def record_exchange_failure(self, exchange: str) -> None:
        self.exchange_failures[exchange] = self.exchange_failures.get(exchange, 0) + 1
        logger.warning("记录交易所 %s 失败（累计=%s）", exchange, self.exchange_failures[exchange])

    def exchange_blocked(self, exchange: str) -> bool:
        return self.exchange_failures.get(exchange, 0) >= self.circuit_breaker_failures

    def evaluate_balances(self, balances: Dict[str, float]) -> Optional[str]:
        if not balances:
            return None
        total = sum(balances.values())
        if total <= 0:
            return None
        for ex, bal in balances.items():
            if bal / total >= self.balance_concentration_pct:
                msg = f"{ex} 余额占比过高: {bal/total*100:.2f}%"
                logger.warning(msg)
                return msg
        return None

    def _override_gate(self) -> Tuple[bool, Optional[str]]:
        """自动暂停时允许人工 override，记录剩余有效期。"""

        if not self.auto_paused:
            return True, None
        if self._override_active():
            if self.manual_override_trades > 0:
                self.manual_override_trades -= 1
            return True, None
        return False, self.halt_reason or "风控暂停"

    def _override_active(self) -> bool:
        if self.manual_override_until and datetime.utcnow() <= self.manual_override_until:
            return True
        if self.manual_override_trades and self.manual_override_trades > 0:
            return True
        return False

    def _symbol_net_and_exposure(
        self,
        symbol: str,
        positions: Sequence[Position],
        quotes: Optional[Iterable[PriceQuote]],
        fallback_price: float,
    ) -> Tuple[float, float]:
        quote_map = {q.symbol: q for q in quotes} if quotes else {}
        price = quote_map.get(symbol).mid if quote_map.get(symbol) else fallback_price
        net = 0.0
        for pos in positions:
            if pos.order.symbol != symbol:
                continue
            net += pos.order.size if pos.order.side == "buy" else -pos.order.size
        return net, abs(net) * price

    def _is_frozen(self) -> bool:
        if not self._frozen_until:
            return False
        if datetime.utcnow() <= self._frozen_until:
            return True
        self._frozen_until = None
        self._freeze_reason = None
        return False
