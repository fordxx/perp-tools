import asyncio
import logging
from typing import Any, Dict

from positions.position_aggregator import PositionAggregator
from risk.kill_switch import KillSwitchV2
from risk.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


class WebConsoleUpdater:
    """
    Periodically fetches risk status and updates the web console.

    This is a simplified representation. A real implementation would likely
    use WebSockets to push updates to the frontend.
    """

    def __init__(
        self,
        risk_engine: RiskEngine,
        kill_switch: KillSwitchV2,
        position_aggregator: PositionAggregator,
        update_interval: float = 5.0,
    ):
        self.risk_engine = risk_engine
        self.kill_switch = kill_switch
        self.position_aggregator = position_aggregator
        self.update_interval = update_interval
        self._task: asyncio.Task | None = None

    def get_status_payload(self) -> Dict[str, Any]:
        """
        Gathers status from all relevant risk components to be sent to the console.
        """
        ks_status = self.kill_switch.get_status()

        return {
            "kill_switch": {
                "state": ks_status.state.value,
                "reason": ks_status.reason,
                "activated_at": ks_status.activated_at,
                "details": ks_status.details,
            },
            "risk_engine": {
                "guards": [guard.name for guard in self.risk_engine.get_guards()],
            },
            "exposure": {
                "net_exposure": self.position_aggregator.get_net_exposure(),
                "gross_exposure": self.position_aggregator.get_gross_exposure(),
                "by_symbol": self.position_aggregator.get_exposure_by_symbol(),
            },
        }

    async def _update_loop(self):
        """The background task loop."""
        while True:
            try:
                status_payload = self.get_status_payload()
                # In a real system, this would send the payload over a WebSocket.
                # For example: await self.websocket_manager.broadcast(status_payload)
                logger.info(f"WebConsole Update (simulated): {status_payload}")
            except Exception:
                logger.exception("Error during web console update loop.")
            await asyncio.sleep(self.update_interval)

    def start(self):
        """Starts the background update task."""
        if self._task is None:
            self._task = asyncio.create_task(self._update_loop())
            logger.info("WebConsoleUpdater started.")

    def stop(self):
        """Stops the background update task."""
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("WebConsoleUpdater stopped.")
