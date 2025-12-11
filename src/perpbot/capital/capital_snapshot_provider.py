from __future__ import annotations
from typing import Dict

from .capital_snapshot import (
    ExchangeCapitalSnapshot,
    GlobalCapitalSnapshot,
)
from .providers.base_provider import CapitalSnapshotProvider


class MockCapitalSnapshotProvider(CapitalSnapshotProvider):
    """
    Mock provider: 返回固定 snapshot，
    后面 TOP8 再替换为真实交易所 API。
    """

    def get_snapshot(self) -> GlobalCapitalSnapshot:
        snapshots: Dict[str, ExchangeCapitalSnapshot] = {
            "PARADEX": ExchangeCapitalSnapshot(
                exchange="PARADEX",
                equity=10000.0,
                available_balance=8000.0,
                open_notional=0.0,
                used_margin=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                leverage=10.0,
                timestamp=0.0,
            ),
            "EXTENDED": ExchangeCapitalSnapshot(
                exchange="EXTENDED",
                equity=10000.0,
                available_balance=8000.0,
                open_notional=0.0,
                used_margin=0.0,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                leverage=10.0,
                timestamp=0.0,
            ),
        }
        return GlobalCapitalSnapshot.from_per_exchange(snapshots)
