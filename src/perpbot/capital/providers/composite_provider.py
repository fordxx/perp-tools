from __future__ import annotations

import time
from typing import Dict, Optional

from .base_provider import CapitalSnapshotProvider
from ..capital_snapshot import ExchangeCapitalSnapshot, GlobalCapitalSnapshot


class CompositeCapitalSnapshotProvider(CapitalSnapshotProvider):
    def __init__(self, providers: Dict[str, CapitalSnapshotProvider]):
        self._providers = providers

    def get_snapshot(self) -> Optional[GlobalCapitalSnapshot]:
        collected: Dict[str, ExchangeCapitalSnapshot] = {}
        total_unrealized = 0.0
        total_realized = 0.0
        total_open_notional = 0.0
        latest_timestamp = 0.0

        for provider in self._providers.values():
            try:
                snapshot = provider.get_snapshot()
                if not snapshot:
                    continue
                for name, exchange_snapshot in snapshot.per_exchange.items():
                    collected[name] = exchange_snapshot
                    total_unrealized += exchange_snapshot.unrealized_pnl
                    total_realized += exchange_snapshot.realized_pnl
                    total_open_notional += exchange_snapshot.open_notional
                    latest_timestamp = max(latest_timestamp, exchange_snapshot.timestamp)
            except Exception:
                continue

        if not collected:
            return None

        return GlobalCapitalSnapshot(
            per_exchange=collected,
            total_equity=sum(s.equity for s in collected.values()),
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
            total_open_notional=total_open_notional,
            timestamp=latest_timestamp or time.time(),
        )
