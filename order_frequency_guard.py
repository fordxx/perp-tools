import time
from dataclasses import dataclass

from ..pre_trade_context import PreTradeContext
from .base_guard import BaseGuard, GuardResult


@dataclass
class OrderFrequencyGuard(BaseGuard):
    """
    Ensures that the number of orders placed within a specified time window
    does not exceed a defined frequency limit.
    """

    max_orders: int
    time_window_seconds: float

    @property
    def name(self) -> str:
        return "OrderFrequencyGuard"

    def evaluate(self, context: PreTradeContext) -> GuardResult:
        """
        Checks if the order frequency is within the allowed limit.
        """
        current_time = time.time()
        # Filter out timestamps older than the time window
        recent_orders = [
            ts for ts in context.recent_order_timestamps if current_time - ts <= self.time_window_seconds
        ]

        if len(recent_orders) >= self.max_orders:
            return GuardResult(
                passed=False,
                guard_name=self.name,
                reason=f"Order frequency ({len(recent_orders)} orders in {self.time_window_seconds}s) exceeds max allowed ({self.max_orders})",
                details={"recent_orders_count": len(recent_orders), "max_orders": self.max_orders, "time_window_seconds": self.time_window_seconds},
            )

        return GuardResult(passed=True, guard_name=self.name)