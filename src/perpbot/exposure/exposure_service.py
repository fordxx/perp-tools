from __future__ import annotations

from typing import List

from .exposure_aggregator import ExposureAggregator
from .exposure_model import ExposureModel


class ExposureService:
    def __init__(self, aggregator: ExposureAggregator):
        self._aggregator = aggregator

    def get_symbol_exposure(self, symbol: str) -> ExposureModel:
        snapshot = self._aggregator.latest_snapshot()
        return snapshot.symbol_exposures.get(symbol, ExposureModel.empty())

    def get_exchange_exposure(self, exchange: str) -> ExposureModel:
        snapshot = self._aggregator.latest_snapshot()
        return snapshot.exchange_exposures.get(exchange, ExposureModel.empty())

    def get_global_exposure(self) -> ExposureModel:
        snapshot = self._aggregator.latest_snapshot()
        return snapshot.global_exposure

    def get_all_symbol_exposures(self) -> List[ExposureModel]:
        snapshot = self._aggregator.latest_snapshot()
        return list(snapshot.symbol_exposures.values())
