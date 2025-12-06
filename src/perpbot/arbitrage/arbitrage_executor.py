from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from perpbot.arbitrage.scanner import ArbitrageOpportunity
from perpbot.exchanges.base import ExchangeClient
from perpbot.models import OrderRequest, Position
from perpbot.position_guard import PositionGuard

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

    def __init__(self, exchanges: Iterable[ExchangeClient], guard: PositionGuard):
        self.exchanges: Dict[str, ExchangeClient] = {ex.name: ex for ex in exchanges}
        self.guard = guard

    def execute(self, opportunity: ArbitrageOpportunity, prefer_limit: bool = True) -> ExecutionResult:
        buy_ex = self.exchanges.get(opportunity.buy_exchange)
        sell_ex = self.exchanges.get(opportunity.sell_exchange)
        if not buy_ex or not sell_ex:
            msg = "Missing exchange client for opportunity"
            logger.error("%s %s/%s", msg, opportunity.buy_exchange, opportunity.sell_exchange)
            return ExecutionResult(opportunity, status="failed", error=msg)

        notional = opportunity.buy_price * opportunity.size
        if not self.guard.allow_trade(notional):
            msg = "Trade blocked by position guard"
            logger.warning("%s: notional %.4f exceeds %s%% of equity", msg, notional, self.guard.max_risk_pct * 100)
            return ExecutionResult(opportunity, status="blocked", error=msg)

        buy_order = None
        sell_order = None
        try:
            buy_req = OrderRequest(
                symbol=opportunity.symbol,
                side="buy",
                size=opportunity.size,
                limit_price=opportunity.buy_price if prefer_limit else None,
            )
            sell_req = OrderRequest(
                symbol=opportunity.symbol,
                side="sell",
                size=opportunity.size,
                limit_price=opportunity.sell_price if prefer_limit else None,
            )

            logger.info(
                "Executing arbitrage: buy %.4f %s @ %s, sell @ %s",
                opportunity.size,
                opportunity.symbol,
                opportunity.buy_exchange,
                opportunity.sell_exchange,
            )
            buy_order = buy_ex.place_open_order(buy_req)
            sell_order = sell_ex.place_open_order(sell_req)
            self.guard.mark_success()
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

        # If buy succeeded but sell failed, offset on buy venue
        if buy_order and not sell_order:
            logger.warning("Hedging buy leg on %s after sell failure", buy_ex.name)
            self._flatten_leg(buy_ex, buy_order, opportunity.symbol)
        # If sell succeeded but buy failed, offset on sell venue
        elif sell_order and not buy_order:
            logger.warning("Hedging sell leg on %s after buy failure", sell_ex.name)
            self._flatten_leg(sell_ex, sell_order, opportunity.symbol)

    def _flatten_leg(self, ex: ExchangeClient, order, symbol: str) -> None:
        try:
            latest = ex.get_current_price(symbol)
            close_price = latest.ask if order.side == "buy" else latest.bid
            position = Position(id=f"hedge-{order.id}", order=order, target_profit_pct=0.0)
            ex.place_close_order(position, close_price)
            logger.info("Submitted hedge close on %s for %s", ex.name, order.id)
        except Exception as hedge_exc:  # pragma: no cover - safety net
            logger.error("Failed to hedge incomplete leg on %s: %s", ex.name, hedge_exc)
