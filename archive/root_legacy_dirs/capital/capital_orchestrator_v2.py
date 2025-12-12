from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from perpbot.events import Event, EventBus, EventKind

from .capital_allocator import CapitalAllocator, CapitalReservation
from .capital_limits import CapitalLimitConfig
from .capital_snapshot import GlobalCapitalSnapshot


class CapitalOrchestratorV2:
    """
    A unified capital coordinator (V2) that makes allocation decisions without
    direct dependency on exchange implementations. It uses snapshots provided
    from an external source.

    - Manages capital allocation decisions via CapitalAllocator.
    - Provides a `reserve_for_order` interface for higher-level modules.
    - Maintains an in-memory "soft lock" on capital to prevent over-allocation
      in concurrent scenarios.
    """

    def __init__(
        self,
        limits: CapitalLimitConfig,
        event_bus: EventBus | None = None,
    ):
        self._limits = limits
        self._allocator = CapitalAllocator(limits)
        self._last_snapshot: Optional[GlobalCapitalSnapshot] = None
        self._last_snapshot_ts: float = 0.0
        self._event_bus = event_bus

        # Simple in-memory soft locks: (exchange, strategy) -> notional_locked
        self._soft_locks: Dict[Tuple[str, str], float] = defaultdict(float)

    def update_snapshot(self, snapshot: GlobalCapitalSnapshot) -> None:
        """Updates the orchestrator with the latest global capital snapshot."""
        self._last_snapshot = snapshot
        self._last_snapshot_ts = time.time()
        if self._event_bus:
            try:
                self._event_bus.publish(
                    Event.now(
                        kind=EventKind.CAPITAL_SNAPSHOT_UPDATE,
                        source=self.__class__.__name__,
                        payload={
                            "timestamp": self._last_snapshot_ts,
                            "exchanges": list(snapshot.per_exchange.keys()),
                            "total_open_notional": snapshot.total_open_notional,
                        },
                    )
                )
            except Exception:
                pass

    def get_snapshot(self) -> Optional[GlobalCapitalSnapshot]:
        """Returns the last known global capital snapshot."""
        return self._last_snapshot

    def reserve_for_order(
        self,
        exchange: str,
        strategy: str,
        requested_notional: float,
        current_open_notional_per_exchange: Dict[str, float],
        current_open_notional_per_strategy: Dict[str, float],
    ) -> CapitalReservation:
        """
        Called by upper layers (e.g., Execution Engine) before placing an order.

        - It accounts for existing soft-locked capital in its decision.
        - If the allocation is approved, it creates a new soft lock for the
          `allowed_notional` amount.
        - Returns a CapitalReservation object indicating the decision.
        """
        if not self._last_snapshot:
            return CapitalReservation(False, "Capital snapshot not available", 0.0, exchange, strategy)

        # Account for existing soft locks in the calculation
        open_notional_exchange = current_open_notional_per_exchange.copy()
        open_notional_strategy = current_open_notional_per_strategy.copy()

        for (lock_exchange, lock_strategy), locked_amount in self._soft_locks.items():
            open_notional_exchange[lock_exchange] = open_notional_exchange.get(lock_exchange, 0.0) + locked_amount
            open_notional_strategy[lock_strategy] = open_notional_strategy.get(lock_strategy, 0.0) + locked_amount

        # Make the allocation decision
        reservation = self._allocator.decide_for_order(
            snapshot=self._last_snapshot,
            exchange=exchange,
            strategy=strategy,
            requested_notional=requested_notional,
            current_open_notional_per_exchange=open_notional_exchange,
            current_open_notional_per_strategy=open_notional_strategy,
        )

        # If successful, create a soft lock
        if reservation.ok and reservation.allowed_notional > 0:
            lock_key = (exchange, strategy)
            self._soft_locks[lock_key] += reservation.allowed_notional

        return reservation

    def release_reservation(
        self,
        exchange: str,
        strategy: str,
        notional: float,
    ) -> None:
        """
        Called by upper layers after an order is filled, cancelled, or failed
        to release the soft-locked capital.
        """
        lock_key = (exchange, strategy)
        if lock_key in self._soft_locks:
            self._soft_locks[lock_key] -= notional
            if self._soft_locks[lock_key] <= 0.001:  # Use a small threshold for float comparison
                del self._soft_locks[lock_key]
