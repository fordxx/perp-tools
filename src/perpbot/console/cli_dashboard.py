from __future__ import annotations

import os
import threading
import time
from typing import Optional

from health.health_monitor import HealthMonitor


class CLIDashboard:
    def __init__(self, health_monitor: HealthMonitor, refresh_sec: float = 2.0):
        self.health_monitor = health_monitor
        self.refresh_sec = refresh_sec
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self.refresh_sec)

    def _loop(self):
        while self._running:
            snapshot = self.health_monitor.get_latest_snapshot()
            state = self.health_monitor.get_console_state().collect_state()
            self._render(snapshot, state)
            time.sleep(self.refresh_sec)

    def _render(self, snapshot, state):
        os.system("cls" if os.name == "nt" else "clear")
        print("================== PERPBOT V2 DASHBOARD ==================")
        if snapshot is None:
            print("Waiting for health data...")
            return
        print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(snapshot.timestamp))}")
        print(f"Overall Health: {snapshot.overall_score:.1f}\n")
        capital = state.get("capital", {})
        print("[ Capital ]")
        print(f"available_balance: {capital.get('available_balance', 0.0)}")
        print(f"open_notional: {capital.get('open_notional', 0.0)}\n")
        exposure = state.get("exposure", {})
        print("[ Exposure ]")
        print(f"net: {exposure.get('net', 0.0)}")
        print(f"gross: {exposure.get('gross', 0.0)}\n")
        execution = state.get("execution", {})
        print("[ Execution ]")
        print(f"success: {execution.get('success_rate', 0.0)}%   fallback: {execution.get('fallback_rate', 0.0)}%\n")
        scanner = state.get("scanner", {})
        print("[ Scanner ]")
        print(f"last_signal: {scanner.get('last_signal')}\n"
              f"signals_per_minute: {scanner.get('freq', 0.0)}\n")
        quote = state.get("quote", {})
        print("[ Quote ]")
        print(f"fresh: {quote.get('freshness', 0.0) >= 80.0}   quality: {quote.get('quality', 0.0)}\n")
        risk = state.get("risk", {})
        print("[ Risk ]")
        print(f"last_guard_fail: {risk.get('recent_fail')}\n")
        latency = state.get("latency", {}).get("per_exchange", {})
        print("[ Latency ]")
        for exchange, ms in latency.items():
            print(f"{exchange}: {ms} ms")
        print("===========================================================")
