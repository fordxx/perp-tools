from __future__ import annotations

import threading
import time
from typing import Optional

from dataclasses import asdict

from perpbot.events import Event, EventBus, EventKind

from .health_score import HealthScoreCalculator
from .health_snapshot import HealthSnapshot
from ..console.console_state import ConsoleState


class HealthMonitor:
    def __init__(
        self,
        console_state: ConsoleState,
        interval_sec: float = 5.0,
        event_bus: EventBus | None = None,
    ):
        self._console_state = console_state
        self._interval_sec = interval_sec
        self._latest_snapshot: Optional[HealthSnapshot] = None
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._event_bus = event_bus

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._interval_sec)

    def _run_loop(self):
        while self._running:
            state = self._console_state.collect_state()
            snapshot = self._build_snapshot(state)
            with self._lock:
                self._latest_snapshot = snapshot
            self._publish_snapshot(snapshot)
            time.sleep(self._interval_sec)

    def _build_snapshot(self, state: dict) -> HealthSnapshot:
        capital_health = 90.0 if state.get("capital", {}).get("snapshot") else 50.0
        exposure_health = 90.0 if state.get("exposure", {}).get("snapshot") else 50.0
        execution_health = state.get("execution", {}).get("success_rate", 0.0)
        quote_health = state.get("quote", {}).get("freshness", 0.0)
        scanner_health = state.get("scanner", {}).get("freq", 0.0)
        risk_health = state.get("risk", {}).get("guard_health", 0.0)
        latency_health = 100.0 - state.get("latency", {}).get("avg_ms", 0.0)
        overall = HealthScoreCalculator.compute_overall_score(
            capital_health,
            exposure_health,
            execution_health,
            quote_health,
            scanner_health,
            risk_health,
            latency_health,
        )
        return HealthSnapshot(
            overall_score=overall,
            capital_health=capital_health,
            exposure_health=exposure_health,
            execution_health=execution_health,
            quote_health=quote_health,
            scanner_health=scanner_health,
            risk_health=risk_health,
            latency_health=latency_health,
            exchange_latency_ms=state.get("latency", {}).get("per_exchange", {}),
            exchange_health=state.get("health", {}).get("exchange_health", {}),
        )

    def get_latest_snapshot(self) -> Optional[HealthSnapshot]:
        with self._lock:
            return self._latest_snapshot

    def _publish_snapshot(self, snapshot: HealthSnapshot) -> None:
        if not self._event_bus:
            return
        try:
            self._event_bus.publish(
                Event.now(
                    kind=EventKind.HEALTH_SNAPSHOT_UPDATE,
                    source=self.__class__.__name__,
                    payload=asdict(snapshot),
                )
            )
        except Exception:
            pass

    def get_console_state(self) -> ConsoleState:
        return self._console_state
