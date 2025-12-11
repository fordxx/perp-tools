from dataclasses import dataclass

from ..pre_trade_context import PreTradeContext
from .base_guard import BaseGuard, GuardResult


@dataclass
class MaxNotionalGuard(BaseGuard):
    """
    Ensures that the notional value of a single order does not exceed a specified limit.
    """

    max_notional: float

    @property
    def name(self) -> str:
        return "MaxNotionalGuard"

    def evaluate(self, context: PreTradeContext) -> GuardResult:
        """
        Checks if the order's notional value is within the allowed maximum.
        """
        if context.notional > self.max_notional:
            return GuardResult(
                passed=False,
                guard_name=self.name,
                reason=f"Order notional ({context.notional}) exceeds max allowed ({self.max_notional})",
                details={"order_notional": context.notional, "max_notional": self.max_notional},
            )

        return GuardResult(passed=True, guard_name=self.name)