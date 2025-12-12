from dataclasses import dataclass

from ..pre_trade_context import PreTradeContext
from .base_guard import BaseGuard, GuardResult


@dataclass
class MaxExposureGuard(BaseGuard):
    """
    Ensures that the account's gross exposure does not exceed a specified limit after the trade.
    """

    max_gross_exposure: float

    @property
    def name(self) -> str:
        return "MaxExposureGuard"

    def evaluate(self, context: PreTradeContext) -> GuardResult:
        """
        Checks if the account's gross exposure is within the allowed maximum.
        """
        if context.gross_exposure > self.max_gross_exposure:
            return GuardResult(
                passed=False,
                guard_name=self.name,
                reason=f"Account gross exposure ({context.gross_exposure}) would exceed max allowed ({self.max_gross_exposure})",
                details={"gross_exposure": context.gross_exposure, "max_gross_exposure": self.max_gross_exposure},
            )

        return GuardResult(passed=True, guard_name=self.name)