from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Tuple

from .exposure_model import ExposureModel


@dataclass
class GlobalExposureSnapshot:
    symbol_exposures: Dict[str, ExposureModel]
    exchange_exposures: Dict[str, ExposureModel]
    global_exposure: ExposureModel
    timestamp: float = field(default_factory=time.time)

    def merge(self, other: "GlobalExposureSnapshot") -> "GlobalExposureSnapshot":
        merged_symbols = {**self.symbol_exposures}
        merged_symbols.update(other.symbol_exposures)
        merged_exchanges = {**self.exchange_exposures}
        merged_exchanges.update(other.exchange_exposures)
        merged_global = ExposureModel.empty()
        merged_global.net_exposure = self.global_exposure.net_exposure + other.global_exposure.net_exposure
        merged_global.gross_exposure = self.global_exposure.gross_exposure + other.global_exposure.gross_exposure
        merged_global.long_exposure = self.global_exposure.long_exposure + other.global_exposure.long_exposure
        merged_global.short_exposure = self.global_exposure.short_exposure + other.global_exposure.short_exposure
        merged_global.per_exchange_exposure = {
            **self.global_exposure.per_exchange_exposure,
            **other.global_exposure.per_exchange_exposure,
        }
        merged_global.timestamp = max(self.global_exposure.timestamp, other.global_exposure.timestamp)
        return GlobalExposureSnapshot(
            symbol_exposures=merged_symbols,
            exchange_exposures=merged_exchanges,
            global_exposure=merged_global,
            timestamp=max(self.timestamp, other.timestamp),
        )

    def to_pre_trade_exposure(self, symbol: str, exchange: str) -> Tuple[ExposureModel, ExposureModel, ExposureModel]:
        symbol_exposure = self.symbol_exposures.get(symbol, ExposureModel.empty())
        exchange_exposure = self.exchange_exposures.get(exchange, ExposureModel.empty())
        return symbol_exposure, exchange_exposure, self.global_exposure
