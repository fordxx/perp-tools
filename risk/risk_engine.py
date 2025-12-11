from typing import List

from perpbot.events import Event, EventBus, EventKind

from .guards.base_guard import BaseGuard, GuardResult
from .pre_trade_context import PreTradeContext


class RiskEngine:
    """
    A pipeline for executing a series of pre-trade risk guards.
    """

    def __init__(self, event_bus: EventBus | None = None):
        self._guards: List[BaseGuard] = []
        self._event_bus = event_bus

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
                self._publish_guard_failure(context, result)

        return failed_results

    def get_guards(self) -> List[BaseGuard]:
        return self._guards.copy()

    def _publish_guard_failure(self, context: PreTradeContext, result: GuardResult) -> None:
        if not self._event_bus:
            return
        payload = {
            "guard_name": result.guard_name,
            "reason": result.reason,
            "details": result.details or {},
            "exchange": context.exchange,
            "symbol": context.symbol,
            "context": {
                "size": context.size,
                "price": context.price,
                "notional": context.notional,
            },
        }
        try:
            self._event_bus.publish(
                Event.now(
                    kind=EventKind.RISK_REJECT,
                    source=self.__class__.__name__,
                    payload=payload,
                )
            )
        except Exception:
            pass
