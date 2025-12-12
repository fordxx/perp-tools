from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from perpbot.capital_orchestrator import CapitalOrchestrator, CapitalReservation
from perpbot.exchanges.base import ExchangeClient
from perpbot.monitoring.market_data_bus import MarketDataBus
from perpbot.monitoring.state import MonitoringState, WashTaskView
from perpbot.risk_manager import RiskManager
from perpbot.models import Order, OrderRequest, PriceQuote

logger = logging.getLogger(__name__)


@dataclass
class HedgeVolumeResult:
    """刷量单次结果，用于回传资金占用与盈亏。"""

    status: str
    reason: Optional[str] = None
    long_order: Optional[Order] = None
    short_order: Optional[Order] = None
    long_close: Optional[Order] = None
    short_close: Optional[Order] = None
    fee: float = 0.0
    pnl: float = 0.0
    volume: float = 0.0


class HedgeVolumeEngine:
    """跨交易所永续对冲刷量引擎。

    设计要点：
    - 仅对接永续合约，严格双边对冲（A 做多 / B 做空）。
    - 下单前从资金总控申请 L1 额度，名义金额由配置的区间随机/轮询决定。
    - 全流程包含预检查、同步开仓、持仓等待、同步平仓以及结果回传。
    - 所有风险拦截、滑点/时间阈值、单所亏损熔断均在内部完成。
    - 通过显式传入交易所实例与 capital_orchestrator 对接，无需改动套利/风控主模块；
      删除本模块不会影响原有系统运行。
    """

    def __init__(
        self,
        exchanges: Dict[str, ExchangeClient],
        orchestrator: CapitalOrchestrator,
        risk_manager: Optional[RiskManager] = None,
        min_notional: float = 300.0,
        max_notional: float = 800.0,
        hold_seconds: Tuple[int, int] = (10, 90),
        max_hold_seconds: int = 120,
        slippage_bps_limit: float = 30.0,
        time_skew_ms: int = 800,
        loss_limit_pct: float = 0.02,
        wash_usage_cap_pct: float = 0.1,
        fee_table: Optional[Dict[str, Dict[str, float]]] = None,
        funding_blackout_minutes: int = 10,
        funding_cycle_seconds: int = 8 * 60 * 60,
        next_funding_timestamp: Optional[float] = None,
        max_acceptable_loss_pct: float = 0.0001,
        max_wash_pct_per_call: float = 0.1,
        monitoring_state: Optional[MonitoringState] = None,
        market_data_bus: Optional[MarketDataBus] = None,
    ) -> None:
        self.exchanges = exchanges
        self.orchestrator = orchestrator
        self.risk_manager = risk_manager
        self.min_notional = min_notional
        self.max_notional = max_notional
        self.hold_seconds = hold_seconds
        self.max_hold_seconds = max_hold_seconds
        self.slippage_bps_limit = slippage_bps_limit
        self.time_skew_ms = time_skew_ms
        self.loss_limit_pct = loss_limit_pct
        self.wash_usage_cap_pct = wash_usage_cap_pct
        self.fee_table = fee_table or {}
        self.funding_blackout_minutes = funding_blackout_minutes
        self.funding_cycle_seconds = funding_cycle_seconds
        self.next_funding_timestamp = next_funding_timestamp
        self.max_acceptable_loss_pct = max_acceptable_loss_pct
        self.max_wash_pct_per_call = max_wash_pct_per_call
        self.loss_tracker: Dict[str, float] = {}
        self.monitoring_state = monitoring_state
        self.market_data_bus = market_data_bus

    def _select_notional(self) -> float:
        return random.uniform(self.min_notional, self.max_notional)

    def _within_wash_cap(self, exchange: str, notional: float) -> bool:
        snapshot = self.orchestrator.current_snapshot().get(exchange)
        if not snapshot or "wash" not in snapshot:
            return False
        available = snapshot["wash"].get("available", 0.0)
        allowed = available * self.wash_usage_cap_pct
        allowed = min(allowed, available)
        return notional <= allowed

    def _check_loss_limit(self, ex: str, pnl: float) -> bool:
        self.loss_tracker.setdefault(ex, 0.0)
        self.loss_tracker[ex] += pnl
        # 当累计亏损超过配置比例（相对 1WU），直接拒绝后续刷量
        threshold = -self.loss_limit_pct * self.orchestrator.wu_size
        if self.loss_tracker[ex] <= threshold:
            logger.warning("%s 刷量累计亏损超限，暂停该所刷量", ex)
            return False
        return True

    async def _fetch_quote(self, ex: ExchangeClient, symbol: str) -> PriceQuote:
        cached = self.market_data_bus.get_cached(ex.name, symbol) if self.market_data_bus else None
        if cached:
            return cached
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, ex.get_current_price, symbol)

    async def _fetch_orderbook(self, ex: ExchangeClient, symbol: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, ex.get_orderbook, symbol)

    def _in_funding_blackout(self) -> bool:
        if not self.next_funding_timestamp:
            return False
        now = time.time()
        window = self.funding_blackout_minutes * 60
        return abs(self.next_funding_timestamp - now) <= window

    def _estimate_pnl(
        self, long_quote: PriceQuote, short_quote: PriceQuote, notional: float
    ) -> Tuple[Optional[float], float, float, float]:
        # 返回 (滑点bps, 手续费成本, 资金费率成本, 预估Pnl)
        long_size = notional / long_quote.mid
        short_size = notional / short_quote.mid
        long_px = long_quote.executable_price("buy", long_size)
        short_px = short_quote.executable_price("sell", short_size)
        if long_px is None or short_px is None:
            return None, 0.0, 0.0, 0.0

        best_long = long_quote.ask
        best_short = short_quote.bid
        slip_bps_long = (long_px - best_long) / best_long * 10_000
        slip_bps_short = (best_short - short_px) / best_short * 10_000
        slip_bps = max(slip_bps_long, slip_bps_short, 0.0)

        maker_fee = self.fee_table.get(long_quote.exchange, {}).get("maker", 0.0005)
        taker_fee = self.fee_table.get(short_quote.exchange, {}).get("taker", 0.0005)
        fee_cost = notional * (maker_fee + taker_fee)

        # 简化资金费率估算：按双方费率均值乘以名义
        funding_long = self.fee_table.get(long_quote.exchange, {}).get("funding", 0.0)
        funding_short = self.fee_table.get(short_quote.exchange, {}).get("funding", 0.0)
        funding_cost = notional * (funding_long + funding_short) / 2

        gross_spread = (short_px - long_px) * long_size
        expected_pnl = gross_spread - fee_cost - abs(slip_bps) / 10_000 * notional - funding_cost
        return slip_bps, fee_cost, funding_cost, expected_pnl

    def _compute_fee(self, notional: float, long_ex: str, short_ex: str) -> float:
        maker_fee = self.fee_table.get(long_ex, {}).get("maker", 0.0005)
        taker_fee = self.fee_table.get(short_ex, {}).get("taker", 0.0005)
        return notional * (maker_fee + taker_fee) * 2

    async def _precheck(self, long_ex: ExchangeClient, short_ex: ExchangeClient, symbol: str, notional: float) -> Tuple[bool, str]:
        # 伪代码流程：
        # 1) 确认两边均为 DEX 永续
        # 2) 检查是否处于资金费率黑名单窗口
        # 3) 拉取盘口 + 估算滑点
        # 4) 估算预期盈亏（手续费、滑点、资金费率）
        # 5) 若预期亏损超过容忍度则拒绝
        if long_ex.venue_type != "dex" or short_ex.venue_type != "dex":
            return False, "仅支持 DEX 永续合约刷量"

        if self._in_funding_blackout():
            return False, "临近资金费率结算，暂停刷量"

        try:
            ob_long, ob_short = await asyncio.gather(
                self._fetch_orderbook(long_ex, symbol),
                self._fetch_orderbook(short_ex, symbol),
            )
            quotes = await asyncio.gather(
                self._fetch_quote(long_ex, symbol),
                self._fetch_quote(short_ex, symbol),
            )
        except Exception as e:
            return False, f"盘口或行情获取失败: {e}"

        long_quote, short_quote = quotes
        long_quote.order_book = ob_long
        short_quote.order_book = ob_short

        slip, fee_cost, funding_cost, expected_pnl = self._estimate_pnl(
            long_quote, short_quote, notional
        )
        if slip is None:
            return False, "盘口深度不足"
        if slip > self.slippage_bps_limit:
            return False, "预估滑点超阈值"

        expected_edge_bps = expected_pnl / max(notional, 1e-9) * 10_000
        expected_loss_bps = max(0.0, -expected_edge_bps)

        if self.risk_manager:
            vol = abs(long_quote.mid - short_quote.mid) / max((long_quote.mid + short_quote.mid) / 2, 1e-9)
            approved, reason, final_score, safety_score, volume_score = self.risk_manager.evaluate_plan(
                notional=notional,
                expected_edge_bps=expected_edge_bps,
                expected_loss_bps=expected_loss_bps,
                volatility=vol,
                latency_ms=0.0,
                slippage_bps=abs(slip),
                volume_contrib=notional * 2,
            )
            if not approved:
                logger.warning(
                    "刷量因风险评分拒绝(%s)：score=%.1f safe=%.1f vol=%.1f",
                    reason,
                    final_score,
                    safety_score,
                    volume_score,
                )
                return False, reason

        loss_floor_pct = abs(self.max_acceptable_loss_pct)
        if self.risk_manager:
            preset = self.risk_manager.risk_mode_presets.get(self.risk_manager.risk_mode, {})
            loss_floor_pct = max(loss_floor_pct, preset.get("max_acceptable_loss_bps", 0.0) / 10_000)

        if expected_pnl < -loss_floor_pct * notional:
            return False, "预期亏损超出容忍度"

        logger.info(
            "刷量预检通过 %s/%s 名义=%.2f 预估PnL=%.4f 费=%.4f 滑点bps=%.2f 资金费率=%.4f",
            long_ex.name,
            short_ex.name,
            notional,
            expected_pnl,
            fee_cost,
            slip,
            funding_cost,
        )
        return True, "ok"

    async def execute_wash_cycle(self, symbol: str, long_exchange: str, short_exchange: str) -> HedgeVolumeResult:
        # 伪代码（关键路径注释）：
        # 1) 选取名义金额（受 wash 可用额度与占比上限约束）
        # 2) 分别向两边交易所申请 wash 资金 reserve_for_wash
        # 3) 预检：DEX 限制、资金费率黑窗、滑点/预估损益
        # 4) 并发开仓，时间差控制；失败则立即回滚
        # 5) 等待持仓时间，超时强制平仓
        # 6) 并发平仓，计算实际 volume/fee/pnl，写入 orchestrator
        # 7) 无论结果如何，finally 中释放占用资金
        long_ex = self.exchanges.get(long_exchange)
        short_ex = self.exchanges.get(short_exchange)
        if not long_ex or not short_ex:
            return HedgeVolumeResult(status="blocked", reason="交易所不存在")

        notional = self._select_notional()
        task_id = f"{long_exchange}-{short_exchange}-{symbol}-{int(time.time()*1000)}"
        if self.monitoring_state:
            self.monitoring_state.register_wash_task(
                WashTaskView(
                    task_id=task_id,
                    pair=f"{long_exchange}↔{short_exchange}",
                    symbol=symbol,
                    notional=notional,
                    status="precheck",
                )
            )
        if not self._within_wash_cap(long_exchange, notional) or not self._within_wash_cap(short_exchange, notional):
            if self.monitoring_state:
                self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"cap": True})
            return HedgeVolumeResult(status="blocked", reason="名义金额超过 wash 可用占比")

        wash_snapshot = self.orchestrator.current_snapshot().get(long_exchange, {}).get("wash", {})
        available = wash_snapshot.get("available", 0.0)
        if available > 0 and notional > available * self.max_wash_pct_per_call:
            if self.monitoring_state:
                self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"cap": True})
            return HedgeVolumeResult(status="blocked", reason="单次名义金额超过 wash 池上限")

        ok_long = self.orchestrator.reserve_for_wash(long_exchange, notional)
        ok_short = self.orchestrator.reserve_for_wash(short_exchange, notional)
        if not ok_long or not ok_short:
            if ok_long:
                self.orchestrator.release((long_exchange, notional, "wash"))
            if ok_short:
                self.orchestrator.release((short_exchange, notional, "wash"))
            if self.monitoring_state:
                self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"balance": True})
            return HedgeVolumeResult(status="blocked", reason="wash 资金不足")

        inflight_notional = notional * 2
        if self.risk_manager:
            ok, reason = self.risk_manager.register_in_flight(inflight_notional)
            if not ok:
                self.orchestrator.release((long_exchange, notional, "wash"))
                self.orchestrator.release((short_exchange, notional, "wash"))
                if self.monitoring_state:
                    self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"risk": True})
                return HedgeVolumeResult(status="blocked", reason=reason)

        reservation = CapitalReservation(
            approved=True,
            allocations={
                long_exchange: ("wash", notional),
                short_exchange: ("wash", notional),
            },
        )

        try:
            ok, reason = await self._precheck(long_ex, short_ex, symbol, notional)
            if not ok:
                if self.monitoring_state:
                    self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"precheck": True})
                return HedgeVolumeResult(status="blocked", reason=reason)

            if self.monitoring_state:
                self.monitoring_state.update_wash_task(task_id, status="open")

            # 同步开仓
            size_long = notional / (await self._fetch_quote(long_ex, symbol)).mid
            size_short = notional / (await self._fetch_quote(short_ex, symbol)).mid
            open_start = time.time()
            long_order, short_order = await self._open_both(long_ex, short_ex, symbol, size_long, size_short)
            skew_ms = abs(time.time() - open_start) * 1000
            if skew_ms > self.time_skew_ms:
                logger.warning("开仓时间差超阈值 %.0fms", skew_ms)

            if not long_order or not short_order:
                await self._rollback_open(long_ex, short_ex, symbol, long_order, short_order)
                if self.monitoring_state:
                    self.monitoring_state.update_wash_task(task_id, status="error", risk_flags={"leg_fail": True})
                return HedgeVolumeResult(status="failed", reason="一边成交失败已回退")

            # 等待持仓
            hold = random.randint(self.hold_seconds[0], self.hold_seconds[1])
            if hold > self.max_hold_seconds:
                hold = self.max_hold_seconds
            try:
                await asyncio.wait_for(asyncio.sleep(hold), timeout=self.max_hold_seconds)
            except asyncio.TimeoutError:
                logger.warning("持仓等待超时，强制进入平仓")
            if self.monitoring_state:
                self.monitoring_state.update_wash_task(task_id, status="hold", hold_seconds=hold)

            long_close, short_close = await self._close_both(long_ex, short_ex, symbol, size_long, size_short)
            if not long_close or not short_close:
                if self.monitoring_state:
                    self.monitoring_state.update_wash_task(task_id, status="error", risk_flags={"close_fail": True})
                return HedgeVolumeResult(status="failed", reason="平仓异常")

            fee = self._compute_fee(notional, long_ex.name, short_ex.name)
            pnl = (short_close.price - long_close.price) * size_long
            volume = notional * 2

            logger.info(
                "刷量完成 %s/%s %s 名义=%.2f 手续费=%.4f PnL=%.4f", long_exchange, short_exchange, symbol, notional, fee, pnl
            )

            # 回传到资金总控用于统计
            self.orchestrator.record_volume_result(long_exchange, volume, fee, pnl)
            self.orchestrator.record_volume_result(short_exchange, volume, fee, pnl)
            if self.risk_manager:
                self.risk_manager.record_volume(volume)
            if self.monitoring_state:
                self.monitoring_state.finalize_wash_task(task_id, volume=volume, fee=fee, pnl=pnl)

            if not self._check_loss_limit(long_exchange, pnl) or not self._check_loss_limit(short_exchange, pnl):
                if self.monitoring_state:
                    self.monitoring_state.update_wash_task(task_id, status="blocked", risk_flags={"loss": True})
                return HedgeVolumeResult(status="blocked", reason="单所刷量亏损超限", fee=fee, pnl=pnl, volume=volume)

            return HedgeVolumeResult(
                status="filled",
                long_order=long_order,
                short_order=short_order,
                long_close=long_close,
                short_close=short_close,
                fee=fee,
                pnl=pnl,
                volume=volume,
            )
        finally:
            self.orchestrator.release(reservation)
            if self.risk_manager:
                self.risk_manager.release_in_flight(inflight_notional)

    async def _open_both(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_size: float,
        short_size: float,
    ) -> Tuple[Optional[Order], Optional[Order]]:
        async def place(ex: ExchangeClient, side: str, size: float):
            req = OrderRequest(symbol=symbol, side=side, size=size)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, ex.place_open_order, req)

        results = await asyncio.gather(
            place(long_ex, "buy", long_size),
            place(short_ex, "sell", short_size),
            return_exceptions=True,
        )
        long_order = results[0] if isinstance(results[0], Order) else None
        short_order = results[1] if isinstance(results[1], Order) else None
        return long_order, short_order

    async def _close_both(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_size: float,
        short_size: float,
    ) -> Tuple[Optional[Order], Optional[Order]]:
        async def close(ex: ExchangeClient, side: str, size: float):
            req = OrderRequest(symbol=symbol, side=side, size=size)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, ex.place_open_order, req)

        results = await asyncio.gather(
            close(long_ex, "sell", long_size),
            close(short_ex, "buy", short_size),
            return_exceptions=True,
        )
        long_close = results[0] if isinstance(results[0], Order) else None
        short_close = results[1] if isinstance(results[1], Order) else None
        return long_close, short_close

    async def _rollback_open(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_order: Optional[Order],
        short_order: Optional[Order],
    ) -> None:
        # 任一边失败时，快速反向平掉已成交腿，避免裸露风险
        tasks = []
        loop = asyncio.get_event_loop()
        if long_order:
            tasks.append(loop.run_in_executor(None, long_ex.cancel_order, long_order.id, symbol))
            tasks.append(loop.run_in_executor(None, long_ex.place_open_order, OrderRequest(symbol=symbol, side="sell", size=long_order.size)))
        if short_order:
            tasks.append(loop.run_in_executor(None, short_ex.cancel_order, short_order.id, symbol))
            tasks.append(loop.run_in_executor(None, short_ex.place_open_order, OrderRequest(symbol=symbol, side="buy", size=short_order.size)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

