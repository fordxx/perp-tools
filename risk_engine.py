from typing import List

from .guards.base_guard import BaseGuard, GuardResult
from .pre_trade_context import PreTradeContext


class RiskEngine:
    """
    A pipeline for executing a series of pre-trade risk guards.
    """

    def __init__(self):
        self._guards: List[BaseGuard] = []

    def add_guard(self, guard: BaseGuard):
        """
        Adds a risk guard to the pipeline.
        """
        self._guards.append(guard)

    def check(self, context: PreTradeContext) -> List[GuardResult]:
        """
        Evaluates the given trade context against all registered guards.

        Returns:
            A list of failed GuardResult objects. An empty list means all checks passed.
        """
        failed_results: List[GuardResult] = []

        for guard in self._guards:
            result = guard.evaluate(context)
            if not result.passed:
                failed_results.append(result)

        return failed_results

    def get_guards(self) -> List[BaseGuard]:
        return self._guards.copy()