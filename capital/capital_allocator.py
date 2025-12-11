from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from .capital_limits import CapitalLimitConfig
from .capital_snapshot import GlobalCapitalSnapshot


@dataclass
class CapitalReservation:
    """Represents the result of a capital allocation decision for a potential order."""

    ok: bool
    reason: Optional[str]
    allowed_notional: float
    exchange: str
    strategy: str


class CapitalAllocator:
    """
    Decides the maximum notional amount a strategy can use for an order on a given exchange,
    based on the current global capital snapshot and configured limits.
    This class is stateless and only performs decision-making, not capital locking.
    """

    def __init__(self, limits: CapitalLimitConfig):
        self._limits = limits

    def decide_for_order(
        self,
        snapshot: GlobalCapitalSnapshot,
        exchange: str,
        strategy: str,
        requested_notional: float,
        current_open_notional_per_exchange: Dict[str, float],
        current_open_notional_per_strategy: Dict[str, float],
    ) -> CapitalReservation:
        """
        Determines if a requested order notional is within configured capital limits.

        Returns:
            - CapitalReservation(ok=False, ...): If the order is rejected due to limits.
            - CapitalReservation(ok=True, allowed_notional=...): If the order is allowed.
              The `allowed_notional` may be less than the `requested_notional`.

        Checks performed:
        - Strategy's max notional per order.
        - Strategy's max total open notional.
        - Exchange's max equity usage percentage.
        - Exchange's max open notional percentage relative to its equity.
        """
        # --- Get relevant limits and current state ---
        strategy_limit = self._limits.get_strategy_limit(strategy)
        exchange_limit = self._limits.get_exchange_limit(exchange)
        exchange_snapshot = snapshot.per_exchange.get(exchange)

        if not exchange_snapshot:
            return CapitalReservation(False, f"No capital snapshot available for exchange '{exchange}'", 0.0, exchange, strategy)

        # --- Strategy-level checks ---
        if strategy_limit:
            # 1. Check max notional per order
            if requested_notional > strategy_limit.max_notional_per_order:
                return CapitalReservation(
                    False,
                    f"Requested notional ({requested_notional:,.0f}) exceeds strategy's max per order ({strategy_limit.max_notional_per_order:,.0f})",
                    0.0, exchange, strategy
                )

            # 2. Check max open notional for the strategy
            if strategy_limit.max_open_notional is not None:
                current_strategy_notional = current_open_notional_per_strategy.get(strategy, 0.0)
                if current_strategy_notional + requested_notional > strategy_limit.max_open_notional:
                    return CapitalReservation(
                        False,
                        f"Order would exceed strategy's max open notional ({strategy_limit.max_open_notional:,.0f})",
                        0.0, exchange, strategy
                    )

        # --- Exchange-level checks ---
        if exchange_limit:
            # 3. Check max equity usage percentage for the exchange
            exchange_equity_limit = snapshot.total_equity * exchange_limit.max_equity_usage_pct
            if exchange_snapshot.equity > exchange_equity_limit:
                return CapitalReservation(
                    False,
                    f"Exchange equity ({exchange_snapshot.equity:,.0f}) already exceeds its usage limit ({exchange_equity_limit:,.0f})",
                    0.0, exchange, strategy
                )

            # 4. Check max open notional percentage for the exchange
            exchange_notional_limit = exchange_snapshot.equity * exchange_limit.max_open_notional_pct
            current_exchange_notional = current_open_notional_per_exchange.get(exchange, 0.0)
            if current_exchange_notional + requested_notional > exchange_notional_limit:
                return CapitalReservation(
                    False,
                    f"Order would exceed exchange's max open notional limit ({exchange_notional_limit:,.0f})",
                    0.0, exchange, strategy
                )

        # --- All checks passed ---
        # The allowed notional is simply the requested one, as we only check for breaches,
        # but a more complex allocator could cap it based on available margin.
        allowed_notional = requested_notional

        if allowed_notional > exchange_snapshot.available_balance:
            # This is a soft warning; the exchange will ultimately reject it.
            # We can choose to cap it or just let it pass to the exchange.
            # For now, we cap it.
            allowed_notional = min(allowed_notional, exchange_snapshot.available_balance)

        return CapitalReservation(True, None, allowed_notional, exchange, strategy)
