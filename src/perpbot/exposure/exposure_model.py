from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ExposureModel:
    net_exposure: float
    gross_exposure: float
    long_exposure: float
    short_exposure: float
    per_exchange_exposure: Dict[str, float]
    timestamp: float = field(default_factory=time.time)

    @staticmethod
    def empty() -> "ExposureModel":
        return ExposureModel(
            net_exposure=0.0,
            gross_exposure=0.0,
            long_exposure=0.0,
            short_exposure=0.0,
            per_exchange_exposure={},
        )

    def copy(self) -> "ExposureModel":
        return ExposureModel(
            net_exposure=self.net_exposure,
            gross_exposure=self.gross_exposure,
            long_exposure=self.long_exposure,
            short_exposure=self.short_exposure,
            per_exchange_exposure=dict(self.per_exchange_exposure),
            timestamp=self.timestamp,
        )
