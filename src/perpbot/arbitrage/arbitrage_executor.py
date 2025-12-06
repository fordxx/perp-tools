from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Sequence

from perpbot.arbitrage.profit import ProfitContext, calculate_real_profit, chunk_order_sizes, resolve_exchange_cost
from perpbot.arbitrage.scanner import ArbitrageOpportunity, DEX_ONLY_PAIRS
from perpbot.exchanges.base import ExchangeClient
from perpbot.models import ExchangeCost, OrderRequest, Position
from perpbot.persistence import TradeRecorder
from perpbot.position_guard import PositionGuard
from perpbot.risk_manager import RiskManager

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    opportunity: ArbitrageOpportunity
    status: str
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    error: Optional[str] = None


class ArbitrageExecutor:
    """Execute two-sided arbitrage opportunities with risk controls and hedging."""

    def __init__(
        self,
        exchanges: Iterable[ExchangeClient],
        guard: PositionGuard,
        risk_manager: Optional[RiskManager] = None,
        exchange_costs: Optional[Dict[str, ExchangeCost]] = None,
        recorder: Optional[TradeRecorder] = None,
    ):
        self.exchanges: Dict[str, ExchangeClient] = {ex.name: ex for ex in exchanges}
        self.guard = guard
        self.risk_manager = risk_manager
        self.exchange_costs = exchange_costs or {}
        self.recorder = recorder

    def execute(
        self,
        opportunity: ArbitrageOpportunity,
        prefer_limit: bool = True,
        positions: Optional[Sequence[Position]] = None,
        quotes=None,
    ) -> ExecutionResult:
        buy_ex = self.exchanges.get(opportunity.buy_exchange)
        sell_ex = self.exchanges.get(opportunity.sell_exchange)
        if not buy_ex or not sell_ex:
            msg = "Missing exchange client for opportunity"
            logger.error("%s %s/%s", msg, opportunity.buy_exchange, opportunity.sell_exchange)
            return ExecutionResult(opportunity, status="failed", error=msg)

        if self.risk_manager and (
            self.risk_manager.exchange_blocked(buy_ex.name) or self.risk_manager.exchange_blocked(sell_ex.name)
        ):
            msg = "Exchange temporarily disabled due to failures"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        if getattr(buy_ex, "venue_type", "dex") != "dex" or getattr(sell_ex, "venue_type", "dex") != "dex":
            msg = "CEX venues cannot be used for arbitrage execution"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        if (buy_ex.name, sell_ex.name) not in DEX_ONLY_PAIRS:
            msg = "Arbitrage pair not permitted"
            logger.warning("%s: %s -> %s", msg, buy_ex.name, sell_ex.name)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        notional = opportunity.buy_price * opportunity.size
        if not self.guard.allow_trade(notional):
            msg = "Trade blocked by position guard"
            logger.warning("%s: notional %.4f exceeds %s%% of equity", msg, notional, self.guard.max_risk_pct * 100)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        if self.risk_manager:
            positions = positions or self.risk_manager.collect_positions(self.exchanges.values())
            allowed, reason = self.risk_manager.can_trade(
                opportunity.symbol,
                side="buy",
                size=opportunity.size,
                price=opportunity.buy_price,
                positions=positions,
                quotes=quotes,
            )
            if not allowed:
                msg = reason or "Blocked by risk manager"
                logger.warning("Arbitrage blocked: %s", msg)
                return ExecutionResult(opportunity, status="blocked", error=msg)
            balances = {}
            for ex in (buy_ex, sell_ex):
                try:
                    bal = sum(b.free for b in ex.get_account_balances())
                    balances[ex.name] = bal
                except Exception:
                    logger.debug("Balance fetch failed for %s", ex.name)
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
            msg = "Arbitrage no longer profitable"
            logger.warning(msg)
            return ExecutionResult(opportunity, status="blocked", error=msg)
        try:
            chunks = list(chunk_order_sizes(opportunity.size, opportunity.buy_price))
            logger.info(
                "Executing arbitrage: %s chunks across %s -> %s (expected net %.4f%%)",
                len(chunks),
                opportunity.buy_exchange,
                opportunity.sell_exchange,
                expected_profit.net_profit_pct * 100,
            )

            for chunk in chunks:
                buy_req = OrderRequest(
                    symbol=opportunity.symbol,
                    side="buy",
                    size=chunk,
                    limit_price=opportunity.buy_price if prefer_limit else None,
                )
                sell_req = OrderRequest(
                    symbol=opportunity.symbol,
                    side="sell",
                    size=chunk,
                    limit_price=opportunity.sell_price if prefer_limit else None,
                )

                latest_buy = buy_ex.get_current_price(opportunity.symbol)
                latest_sell = sell_ex.get_current_price(opportunity.symbol)
                if self.risk_manager:
                    ok_buy, reason_buy = self.risk_manager.check_slippage(opportunity.buy_price, latest_buy.ask)
                    ok_sell, reason_sell = self.risk_manager.check_slippage(opportunity.sell_price, latest_sell.bid)
                    if not (ok_buy and ok_sell):
                        msg = reason_buy or reason_sell or "Slippage check failed"
                        logger.warning(msg)
                        return ExecutionResult(opportunity, status="blocked", error=msg)

                buy_order = buy_ex.place_open_order(buy_req)
                sell_order = sell_ex.place_open_order(sell_req)

                filled = self._wait_for_fill(buy_ex, buy_order, opportunity.symbol)
                filled &= self._wait_for_fill(sell_ex, sell_order, opportunity.symbol)
                if not filled:
                    logger.warning("Partial fill detected; hedging exposure")
                    self._hedge_incomplete_legs(opportunity, buy_ex, sell_ex, buy_order, sell_order)
                    raise RuntimeError("Partial fill hedge executed")

            if self.risk_manager:
                self.risk_manager.record_success()
            self.guard.mark_success()
            if self.recorder:
                self.recorder.record_trade(opportunity, success=True, actual_profit=expected_profit.net_profit_abs)
            return ExecutionResult(
                opportunity,
                status="filled",
                buy_order_id=buy_order.id,
                sell_order_id=sell_order.id,
            )
        except Exception as exc:  # pragma: no cover - runtime protection
            logger.exception("Arbitrage leg failed: %s", exc)
            self._hedge_incomplete_legs(opportunity, buy_ex, sell_ex, buy_order, sell_order)
            self.guard.mark_failure()
            if self.risk_manager:
                self.risk_manager.record_failure()
                self.risk_manager.record_exchange_failure(buy_ex.name)
                self.risk_manager.record_exchange_failure(sell_ex.name)
            if self.recorder:
                self.recorder.record_trade(opportunity, success=False, actual_profit=0.0, error_message=str(exc))
            return ExecutionResult(opportunity, status="failed", error=str(exc))

    def _hedge_incomplete_legs(
        self,
        opportunity: ArbitrageOpportunity,
        buy_ex: ExchangeClient,
        sell_ex: ExchangeClient,
        buy_order,
        sell_order,
    ) -> None:
        """Neutralize open exposure when one leg fails."""

        fallback_ex = next(
            (ex for ex in self.exchanges.values() if ex.name not in {buy_ex.name, sell_ex.name} and getattr(ex, "venue_type", "dex") == "dex"),
            None,
        )

        # If buy succeeded but sell failed, offset on buy venue
        if buy_order and not sell_order:
            logger.warning("Hedging buy leg on %s after sell failure", buy_ex.name)
            hedger = fallback_ex or buy_ex
            self._flatten_leg(hedger, buy_order, opportunity.symbol)
        # If sell succeeded but buy failed, offset on sell venue
        elif sell_order and not buy_order:
            logger.warning("Hedging sell leg on %s after buy failure", sell_ex.name)
            hedger = fallback_ex or sell_ex
            self._flatten_leg(hedger, sell_order, opportunity.symbol)

    def _flatten_leg(self, ex: ExchangeClient, order, symbol: str) -> None:
        try:
            latest = ex.get_current_price(symbol)
            close_price = latest.ask if order.side == "buy" else latest.bid
            position = Position(id=f"hedge-{order.id}", order=order, target_profit_pct=0.0)
            ex.place_close_order(position, close_price)
            logger.info("Submitted hedge close on %s for %s", ex.name, order.id)
        except Exception as hedge_exc:  # pragma: no cover - safety net
            logger.error("Failed to hedge incomplete leg on %s: %s", ex.name, hedge_exc)

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
