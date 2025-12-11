from dataclasses import dataclass

from ..pre_trade_context import PreTradeContext
from .base_guard import BaseGuard, GuardResult


@dataclass
class MaxLeverageGuard(BaseGuard):
    """
    Ensures that the account leverage does not exceed a specified limit after the trade.
    """

    max_leverage: float

    @property
    def name(self) -> str:
        return "MaxLeverageGuard"

    def evaluate(self, context: PreTradeContext) -> GuardResult:
        """
        Checks if the account's leverage is within the allowed maximum.
        """
        if context.leverage > self.max_leverage:
            return GuardResult(
                passed=False,
                guard_name=self.name,
                reason=f"Account leverage ({context.leverage:.2f}x) would exceed max allowed ({self.max_leverage:.2f}x)",
                details={"current_leverage": context.leverage, "max_leverage": self.max_leverage},
            )

        return GuardResult(passed=True, guard_name=self.name)