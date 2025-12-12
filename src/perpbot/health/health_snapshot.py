from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class HealthSnapshot:
    timestamp: float = field(default_factory=time.time)
    overall_score: float = 0.0

    capital_health: float = 0.0
    exposure_health: float = 0.0
    execution_health: float = 0.0
    quote_health: float = 0.0
    scanner_health: float = 0.0
    risk_health: float = 0.0
    latency_health: float = 0.0

    exchange_latency_ms: Dict[str, float] = field(default_factory=dict)
    exchange_health: Dict[str, float] = field(default_factory=dict)
