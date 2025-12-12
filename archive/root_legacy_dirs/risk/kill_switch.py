import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

logger = logging.getLogger(__name__)


class KillSwitchState(Enum):
    """
    Defines the possible states of the Kill Switch.
    """

    INACTIVE = "INACTIVE"
    ACTIVATED = "ACTIVATED"


@dataclass
class KillSwitchStatus:
    """
    Represents the current status of the Kill Switch.
    """

    state: KillSwitchState
    reason: Optional[str] = None
    activated_at: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)


# Type hint for an async function that cancels all orders for a given exchange.
CancelOrdersFunc = Callable[[str], Coroutine[Any, Any, None]]


class KillSwitchV2:
    """
    A global kill switch to halt all trading activities.

    When activated, it blocks new orders and can be configured to automatically
    cancel all existing open orders for a specific exchange.
    """

    def __init__(self, cancel_all_orders_func: Optional[CancelOrdersFunc] = None):
        self._status = KillSwitchStatus(state=KillSwitchState.INACTIVE)
        self._lock = asyncio.Lock()
        self._cancel_all_orders_func = cancel_all_orders_func

    async def activate(
        self,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        exchange_to_cancel: Optional[str] = None,
    ):
        """
        Activates the kill switch, halting all trading activities.
        If an exchange is provided, it will attempt to cancel all open orders on it.
        This is an idempotent operation.
        """
        async with self._lock:
            if self._status.state == KillSwitchState.ACTIVATED:
                logger.warning(f"Kill Switch already activated. Ignoring new activation request.")
                return

            self._status = KillSwitchStatus(
                state=KillSwitchState.ACTIVATED,
                reason=reason,
                activated_at=time.time(),
                details=details or {},
            )
            logger.critical(f"KILL SWITCH ACTIVATED: {reason}", extra={"details": details})

        if exchange_to_cancel and self._cancel_all_orders_func:
            try:
                logger.info(f"Kill Switch: Cancelling all open orders for exchange '{exchange_to_cancel}'...")
                await self._cancel_all_orders_func(exchange_to_cancel)
                logger.info(f"Kill Switch: Successfully cancelled orders for '{exchange_to_cancel}'.")
            except Exception as e:
                logger.exception(f"Kill Switch: Failed to cancel orders for '{exchange_to_cancel}': {e}")

    async def deactivate(self):
        """
        Deactivates the kill switch, allowing trading to resume. Requires manual intervention.
        """
        async with self._lock:
            if self._status.state == KillSwitchState.INACTIVE:
                return
            self._status = KillSwitchStatus(state=KillSwitchState.INACTIVE)
            logger.warning("KILL SWITCH DEACTIVATED. Trading can now resume.")

    def get_status(self) -> KillSwitchStatus:
        """Returns a copy of the current status."""
        return self._status