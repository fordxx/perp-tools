from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UnifiedPosition:
    exchange: str
    symbol: str
    side: str  # "LONG" / "SHORT"
    size: float  # raw quantity
    notional: float  # normalized USD notional
    entry_price: float
    mark_price: float
    unrealized_pnl: float

__all__ = ["UnifiedPosition"]
