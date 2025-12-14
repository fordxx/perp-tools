from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import time


class EventKind(str, Enum):
    QUOTE = "QUOTE"
    SCANNER_SIGNAL = "SCANNER_SIGNAL"
    EXECUTION_SUBMITTED = "EXECUTION_SUBMITTED"
    EXECUTION_FILLED = "EXECUTION_FILLED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RISK_REJECT = "RISK_REJECT"
    CAPITAL_REJECT = "CAPITAL_REJECT"
    EXPOSURE_UPDATE = "EXPOSURE_UPDATE"
    CAPITAL_SNAPSHOT_UPDATE = "CAPITAL_SNAPSHOT_UPDATE"
    HEALTH_SNAPSHOT_UPDATE = "HEALTH_SNAPSHOT_UPDATE"
    CUSTOM = "CUSTOM"


@dataclass
class Event:
    kind: EventKind
    timestamp: float
    payload: Dict[str, Any]
    source: str
    correlation_id: Optional[str] = None

    @staticmethod
    def now(
        kind: EventKind,
        source: str,
        payload: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> "Event":
        return Event(
            kind=kind,
            timestamp=time.time(),
            payload=payload,
            source=source,
            correlation_id=correlation_id,
        )


@dataclass
class MarketDataUpdate:
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp: datetime
    kind: EventKind = field(init=False, default=EventKind.QUOTE)


@dataclass
class ArbitrageOpportunityFound:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_bps: float
    size: float
    timestamp: datetime
    kind: EventKind = field(init=False, default=EventKind.SCANNER_SIGNAL)


@dataclass
class OrderExecuted:
    order_id: str
    exchange: str
    symbol: str
    side: str
    size: float
    price: float
    timestamp: datetime
    kind: EventKind = field(init=False, default=EventKind.EXECUTION_FILLED)


@dataclass
class PositionOpened:
    exchange: str
    symbol: str
    size: float
    entry_price: float
    timestamp: datetime
    kind: EventKind = field(init=False, default=EventKind.EXECUTION_SUBMITTED)


@dataclass
class PositionClosed:
    exchange: str
    symbol: str
    size: float
    exit_price: float
    timestamp: datetime
    kind: EventKind = field(init=False, default=EventKind.EXECUTION_FAILED)
