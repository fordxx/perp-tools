"""Metrics tracking for monitoring system health."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class OrderMetrics:
    """Track order execution metrics."""

    # Stop-loss order tracking
    sl_orders_attempted: int = 0
    sl_orders_success: int = 0
    sl_orders_failed: int = 0
    emergency_closes_executed: int = 0
    emergency_closes_failed: int = 0

    # Entry order tracking
    entry_orders_attempted: int = 0
    entry_orders_success: int = 0
    entry_orders_failed: int = 0

    # TP order tracking
    tp_orders_attempted: int = 0
    tp_orders_success: int = 0
    tp_orders_failed: int = 0

    # Timing metrics
    last_sl_failure_ts: float = 0.0
    last_emergency_close_ts: float = 0.0

    # Recent failures (keep last 100)
    recent_sl_failures: list[dict] = field(default_factory=list)

    def record_sl_attempt(self, *, success: bool, inst_id: str, reason: str = "") -> None:
        """Record stop-loss order attempt."""
        self.sl_orders_attempted += 1
        if success:
            self.sl_orders_success += 1
        else:
            self.sl_orders_failed += 1
            self.last_sl_failure_ts = time.time()

            # Keep only last 100 failures
            self.recent_sl_failures.append({
                "ts": time.time(),
                "inst_id": inst_id,
                "reason": reason,
            })
            if len(self.recent_sl_failures) > 100:
                self.recent_sl_failures.pop(0)

    def record_emergency_close(self, *, success: bool, inst_id: str) -> None:
        """Record emergency close attempt."""
        if success:
            self.emergency_closes_executed += 1
        else:
            self.emergency_closes_failed += 1
        self.last_emergency_close_ts = time.time()

    def record_entry_order(self, *, success: bool) -> None:
        """Record entry order attempt."""
        self.entry_orders_attempted += 1
        if success:
            self.entry_orders_success += 1
        else:
            self.entry_orders_failed += 1

    def record_tp_order(self, *, success: bool) -> None:
        """Record TP order attempt."""
        self.tp_orders_attempted += 1
        if success:
            self.tp_orders_success += 1
        else:
            self.tp_orders_failed += 1

    @property
    def sl_failure_rate(self) -> float:
        """Calculate stop-loss failure rate."""
        if self.sl_orders_attempted == 0:
            return 0.0
        return self.sl_orders_failed / self.sl_orders_attempted

    @property
    def entry_failure_rate(self) -> float:
        """Calculate entry order failure rate."""
        if self.entry_orders_attempted == 0:
            return 0.0
        return self.entry_orders_failed / self.entry_orders_attempted

    @property
    def tp_failure_rate(self) -> float:
        """Calculate TP order failure rate."""
        if self.tp_orders_attempted == 0:
            return 0.0
        return self.tp_orders_failed / self.tp_orders_attempted

    def get_recent_sl_failures(self, *, last_n_minutes: int = 60) -> list[dict]:
        """Get stop-loss failures in the last N minutes."""
        cutoff = time.time() - (last_n_minutes * 60)
        return [f for f in self.recent_sl_failures if f["ts"] >= cutoff]

    def should_alert(self, *, threshold: float = 0.05, min_attempts: int = 10) -> bool:
        """Check if failure rate exceeds alert threshold."""
        if self.sl_orders_attempted < min_attempts:
            return False
        return self.sl_failure_rate >= threshold

    def get_summary(self) -> dict:
        """Get metrics summary."""
        return {
            "sl_orders": {
                "attempted": self.sl_orders_attempted,
                "success": self.sl_orders_success,
                "failed": self.sl_orders_failed,
                "failure_rate": f"{self.sl_failure_rate:.2%}",
            },
            "entry_orders": {
                "attempted": self.entry_orders_attempted,
                "success": self.entry_orders_success,
                "failed": self.entry_orders_failed,
                "failure_rate": f"{self.entry_failure_rate:.2%}",
            },
            "tp_orders": {
                "attempted": self.tp_orders_attempted,
                "success": self.tp_orders_success,
                "failed": self.tp_orders_failed,
                "failure_rate": f"{self.tp_failure_rate:.2%}",
            },
            "emergency_closes": {
                "executed": self.emergency_closes_executed,
                "failed": self.emergency_closes_failed,
            },
            "recent_sl_failures_1h": len(self.get_recent_sl_failures(last_n_minutes=60)),
            "last_sl_failure": self.last_sl_failure_ts,
            "last_emergency_close": self.last_emergency_close_ts,
        }


# Global metrics instance
_metrics = OrderMetrics()


def get_metrics() -> OrderMetrics:
    """Get global metrics instance."""
    return _metrics


def reset_metrics() -> None:
    """Reset all metrics (for testing)."""
    global _metrics
    _metrics = OrderMetrics()
