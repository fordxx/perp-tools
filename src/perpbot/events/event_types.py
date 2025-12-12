from __future__ import annotations

from dataclasses import dataclass
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
