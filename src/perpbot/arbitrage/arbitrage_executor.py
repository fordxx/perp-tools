from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence

from perpbot.arbitrage.profit import ProfitContext, calculate_real_profit, chunk_order_sizes, resolve_exchange_cost
from perpbot.arbitrage.scanner import ArbitrageOpportunity, DEX_ONLY_PAIRS
from perpbot.capital_orchestrator import CapitalOrchestrator, CapitalReservation
from perpbot.exchanges.base import ExchangeClient
from perpbot.execution.execution_engine import ExecutionEngine, ExecutionPlan
from perpbot.execution.execution_mode import ExecutionConfig
from perpbot.models import ExchangeCost, Order, OrderRequest, Position, PriceQuote
from perpbot.persistence import TradeRecorder
from perpbot.position_guard import PositionGuard
from perpbot.risk_manager import RiskManager
from perpbot.scoring.fee_model import FeeModel
from perpbot.scoring.slippage_model import SlippageModel

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    opportunity: ArbitrageOpportunity
    status: str
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    error: Optional[str] = None


class ArbitrageExecutor:
    """执行双边套利机会，内置风控与对冲。"""

    def __init__(
        self,
        exchanges: Iterable[ExchangeClient],
        guard: PositionGuard,
        risk_manager: Optional[RiskManager] = None,
        exchange_costs: Optional[Dict[str, ExchangeCost]] = None,
        recorder: Optional[TradeRecorder] = None,
        capital_orchestrator: Optional[CapitalOrchestrator] = None,
        execution_engine: Optional[ExecutionEngine] = None,
        execution_config: Optional[ExecutionConfig] = None,
    ):
        self.exchanges: Dict[str, ExchangeClient] = {ex.name: ex for ex in exchanges}
        self.guard = guard
        self.risk_manager = risk_manager
        self.exchange_costs = exchange_costs or {}
        self.recorder = recorder
        self.capital_orchestrator = capital_orchestrator
        self.execution_engine = execution_engine or ExecutionEngine(
            fee_model=FeeModel(),
            slippage_model=SlippageModel(),
            config=execution_config or ExecutionConfig(),
        )

    def execute(
        self,
        opportunity: ArbitrageOpportunity,
        prefer_limit: bool = True,
        positions: Optional[Sequence[Position]] = None,
        quotes=None,
        strategy: str = "arbitrage",
    ) -> ExecutionResult:
        buy_ex = self.exchanges.get(opportunity.buy_exchange)
        sell_ex = self.exchanges.get(opportunity.sell_exchange)
        if not buy_ex or not sell_ex:
            msg = "缺少对应的交易所客户端"
            logger.error("%s %s/%s", msg, opportunity.buy_exchange, opportunity.sell_exchange)
            return ExecutionResult(opportunity, status="failed", error=msg)

        if self.risk_manager and (
            self.risk_manager.exchange_blocked(buy_ex.name) or self.risk_manager.exchange_blocked(sell_ex.name)
        ):
            msg = "交易所因连续失败被暂时熔断"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        if getattr(buy_ex, "venue_type", "dex") != "dex" or getattr(sell_ex, "venue_type", "dex") != "dex":
            msg = "中心化交易所仅做行情参考/风控过滤，套利执行严格基于各交易所实时盘口"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        if (buy_ex.name, sell_ex.name) not in DEX_ONLY_PAIRS:
            msg = "该套利组合不在允许列表"
            logger.warning("%s: %s -> %s", msg, buy_ex.name, sell_ex.name)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        notional = opportunity.buy_price * opportunity.size
        if not self.guard.allow_trade(notional):
            msg = "仓位保护阻止了本次下单"
            logger.warning("%s: notional %.4f exceeds %s%% of equity", msg, notional, self.guard.max_risk_pct * 100)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        quotes_list = list(quotes) if quotes is not None else []
        quote_map = {(q.exchange, q.symbol): q for q in quotes_list}
        reservation: Optional[CapitalReservation] = None

        if self.risk_manager:
            positions = positions or self.risk_manager.collect_positions(self.exchanges.values())
            allowed, reason = self.risk_manager.can_trade(
                opportunity.symbol,
                side="buy",
                size=opportunity.size,
                price=opportunity.buy_price,
                positions=positions,
                quotes=quotes_list,
            )
            if not allowed:
                msg = reason or "被风控拦截"
                logger.warning("套利被拦截: %s", msg)
                return ExecutionResult(opportunity, status="blocked", error=msg)
            balances = {}
            for ex in (buy_ex, sell_ex):
                try:
                    bal = sum(b.free for b in ex.get_account_balances())
                    balances[ex.name] = bal
                except Exception:
                    logger.debug("获取余额失败: %s", ex.name)
            self.risk_manager.evaluate_balances(balances)

        buy_order = None
        sell_order = None
        failure_bias = 0.0
        if self.risk_manager and getattr(self.risk_manager, "consecutive_failures", 0) > 0:
            failure_bias = min(0.5, self.risk_manager.consecutive_failures / 10)
        profit_ctx = ProfitContext(
            buy_cost=resolve_exchange_cost(buy_ex.name, self.exchange_costs, ExchangeCost()),
            sell_cost=resolve_exchange_cost(sell_ex.name, self.exchange_costs, ExchangeCost()),
            failure_probability=failure_bias,
        )
        expected_profit = calculate_real_profit(opportunity, notional, profit_ctx)
        if expected_profit.net_profit_abs <= 0:
            msg = "套利不再有正收益"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        plan = self._plan_execution(opportunity, expected_profit, quote_map)
        if not plan.valid:
            msg = plan.reason or "执行计划未通过约束"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)
        buy_is_taker = plan.decision.open_order_type == "taker"
        sell_is_taker = plan.decision.close_order_type == "taker"
        if not prefer_limit:
            buy_is_taker = True
            sell_is_taker = True
        had_fallback = False

        try:
            if self.capital_orchestrator:
                reservation = self.capital_orchestrator.reserve_for_strategy(
                    [buy_ex.name, sell_ex.name], amount=notional, strategy=strategy
                )
                if not reservation.approved:
                    msg = reservation.reason or "资金分配失败"
                    logger.warning("资金调度拒绝本次套利: %s", msg)
                    return ExecutionResult(opportunity, status="blocked", error=msg)
            chunks = list(chunk_order_sizes(opportunity.size, opportunity.buy_price))
            logger.info(
                "执行套利: %s 笔拆单 %s -> %s (预期净收益 %.4f%%)",
                len(chunks),
                opportunity.buy_exchange,
                opportunity.sell_exchange,
                expected_profit.net_profit_pct * 100,
            )

            for chunk in chunks:
                buy_limit = None if buy_is_taker else opportunity.buy_price
                sell_limit = None if sell_is_taker else opportunity.sell_price
                buy_req = OrderRequest(
                    symbol=opportunity.symbol,
                    side="buy",
                    size=chunk,
                    limit_price=buy_limit,
                )
                sell_req = OrderRequest(
                    symbol=opportunity.symbol,
                    side="sell",
                    size=chunk,
                    limit_price=sell_limit,
                )

                latest_buy = buy_ex.get_current_price(opportunity.symbol)
                latest_sell = sell_ex.get_current_price(opportunity.symbol)
                if self.risk_manager:
                    buy_reference = buy_limit or latest_buy.ask
                    sell_reference = sell_limit or latest_sell.bid
                    ok_buy, reason_buy = self.risk_manager.check_slippage(buy_reference, latest_buy.ask)
                    ok_sell, reason_sell = self.risk_manager.check_slippage(sell_reference, latest_sell.bid)
                    if not (ok_buy and ok_sell):
                        msg = reason_buy or reason_sell or "滑点校验未通过"
                        logger.warning(msg)
                        return ExecutionResult(opportunity, status="blocked", error=msg)

                buy_order = buy_ex.place_open_order(buy_req)
                sell_order = sell_ex.place_open_order(sell_req)

                buy_filled = self._wait_for_fill(buy_ex, buy_order, opportunity.symbol)
                sell_filled = self._wait_for_fill(sell_ex, sell_order, opportunity.symbol)
                fallback_triggered = False
                if plan.decision.may_fallback:
                    if not buy_filled and not buy_is_taker:
                        fallback_triggered = True
                        buy_filled, buy_order = self._fallback_to_taker(
                            buy_ex, opportunity.symbol, "buy", chunk, buy_order
                        )
                    if not sell_filled and not sell_is_taker:
                        fallback_triggered = True
                        sell_filled, sell_order = self._fallback_to_taker(
                            sell_ex, opportunity.symbol, "sell", chunk, sell_order
                        )
                had_fallback |= fallback_triggered
                if not buy_filled or not sell_filled:
                    logger.warning("出现部分成交，启动对冲保护")
                    self._hedge_incomplete_legs(
                        opportunity,
                        buy_ex,
                        sell_ex,
                        buy_order if buy_filled else None,
                        sell_order if sell_filled else None,
                    )
                    raise RuntimeError("Partial fill hedge executed")

            if self.risk_manager:
                self.risk_manager.record_success()
            self.guard.mark_success()
            if plan.decision.may_fallback and (not buy_is_taker or not sell_is_taker):
                self.execution_engine.record_execution_outcome(
                    buy_ex.name, sell_ex.name, plan.decision, success=True, had_fallback=had_fallback
                )
            if self.recorder:
                self.recorder.record_trade(opportunity, success=True, actual_profit=expected_profit.net_profit_abs)
            return ExecutionResult(
                opportunity,
                status="filled",
                buy_order_id=buy_order.id,
                sell_order_id=sell_order.id if sell_order else None,
            )
        except Exception as exc:  # pragma: no cover - runtime protection
            logger.exception("套利腿执行失败: %s", exc)
            self._hedge_incomplete_legs(opportunity, buy_ex, sell_ex, buy_order, sell_order)
            self.guard.mark_failure()
            if self.risk_manager:
                self.risk_manager.record_failure()
                self.risk_manager.record_exchange_failure(buy_ex.name)
                self.risk_manager.record_exchange_failure(sell_ex.name)
            if plan.decision.may_fallback and (not buy_is_taker or not sell_is_taker):
                self.execution_engine.record_execution_outcome(
                    buy_ex.name, sell_ex.name, plan.decision, success=False, had_fallback=had_fallback
                )
            if self.recorder:
                self.recorder.record_trade(opportunity, success=False, actual_profit=0.0, error_message=str(exc))
            return ExecutionResult(opportunity, status="failed", error=str(exc))
        finally:
            if reservation:
                self.capital_orchestrator.release(reservation)

    def _plan_execution(
        self,
        opportunity: ArbitrageOpportunity,
        expected_profit,
        quote_map: Dict[tuple[str, str], PriceQuote],
    ) -> ExecutionPlan:
        base_liq = (opportunity.liquidity_score / 100) if opportunity.liquidity_score else 0.5
        default_liq = max(0.05, min(0.95, base_liq))
        buy_quote = quote_map.get((opportunity.buy_exchange, opportunity.symbol))
        sell_quote = quote_map.get((opportunity.sell_exchange, opportunity.symbol))
        buy_liq = self._liquidity_score(buy_quote, "buy", opportunity.size, default_liq)
        sell_liq = self._liquidity_score(sell_quote, "sell", opportunity.size, default_liq)
        return self.execution_engine.plan_execution(
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            symbol=opportunity.symbol,
            notional=opportunity.buy_price * opportunity.size,
            buy_liquidity_score=buy_liq,
            sell_liquidity_score=sell_liq,
            expected_pnl=expected_profit.net_profit_abs,
        )

    def _liquidity_score(
        self,
        quote: Optional[PriceQuote],
        side: str,
        size: float,
        fallback: float,
    ) -> float:
        if quote and quote.order_book:
            try:
                ratio = quote.order_book.fill_ratio(side, size)
                return max(0.05, min(0.95, ratio))
            except Exception:
                logger.debug("计算盘口流动性失败: %s %s", quote.exchange, quote.symbol)
        return fallback

    def _fallback_to_taker(
        self,
        ex: ExchangeClient,
        symbol: str,
        side: str,
        size: float,
        order: Order,
    ) -> tuple[bool, Order]:
        try:
            ex.cancel_order(order.id, symbol)
        except Exception:
            logger.debug("取消未成交订单失败: %s", order.id)
        logger.info("Maker 订单 fallback 到 taker: %s %s %s", ex.name, symbol, side)
        fallback_req = OrderRequest(symbol=symbol, side=side, size=size, limit_price=None)
        fallback_order = ex.place_open_order(fallback_req)
        filled = self._wait_for_fill(ex, fallback_order, symbol)
        return filled, fallback_order

    def _hedge_incomplete_legs(
        self,
        opportunity: ArbitrageOpportunity,
        buy_ex: ExchangeClient,
        sell_ex: ExchangeClient,
        buy_order,
        sell_order,
    ) -> None:
        """在任意一腿失败时中和持仓敞口。"""

        fallback_ex = next(
            (ex for ex in self.exchanges.values() if ex.name not in {buy_ex.name, sell_ex.name} and getattr(ex, "venue_type", "dex") == "dex"),
            None,
        )

        # 如果买腿成功但卖腿失败，在买入交易所对冲
        if buy_order and not sell_order:
            logger.warning("卖腿失败，在 %s 对买腿做对冲", buy_ex.name)
            hedger = fallback_ex or buy_ex
            self._flatten_leg(hedger, buy_order, opportunity.symbol)
        # 如果卖腿成功但买腿失败，在卖出交易所对冲
        elif sell_order and not buy_order:
            logger.warning("买腿失败，在 %s 对卖腿做对冲", sell_ex.name)
            hedger = fallback_ex or sell_ex
            self._flatten_leg(hedger, sell_order, opportunity.symbol)

    def _flatten_leg(self, ex: ExchangeClient, order, symbol: str) -> None:
        try:
            latest = ex.get_current_price(symbol)
            close_price = latest.ask if order.side == "buy" else latest.bid
            position = Position(id=f"hedge-{order.id}", order=order, target_profit_pct=0.0)
            ex.place_close_order(position, close_price)
            logger.info("已在 %s 提交对冲平仓，来源订单 %s", ex.name, order.id)
        except Exception as hedge_exc:  # pragma: no cover - safety net
            logger.error("在 %s 对冲未完成腿失败: %s", ex.name, hedge_exc)

    def _wait_for_fill(self, ex: ExchangeClient, order, symbol: str) -> bool:
        timeout = getattr(self.risk_manager, "order_fill_timeout_seconds", 5) if self.risk_manager else 5
        deadline = time.time() + timeout
        while time.time() < deadline:
            active = ex.get_active_orders(symbol)
            still_open = any(o.id == order.id for o in active)
            if not still_open:
                return True
            time.sleep(0.5)
        return False
