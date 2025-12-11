from __future__ import annotations

from typing import Optional

from ..capital_snapshot import ExchangeCapitalSnapshot, GlobalCapitalSnapshot
from .base_provider import CapitalSnapshotProvider


class ExtendedCapitalSnapshotProvider(CapitalSnapshotProvider):
    def __init__(self, client: Optional[object] = None):
        self.client = client

    def get_snapshot(self) -> Optional[GlobalCapitalSnapshot]:
        try:
            # TODO: Replace with real Extended client fetch when available
            exchange_snapshot = ExchangeCapitalSnapshot(
                exchange="EXTENDED",
                equity=15000.0,
                available_balance=9000.0,
                open_notional=0.0,
                used_margin=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                leverage=10.0,
                timestamp=0.0,
            )
            return GlobalCapitalSnapshot.from_per_exchange({"EXTENDED": exchange_snapshot})
        except Exception:
            return None
