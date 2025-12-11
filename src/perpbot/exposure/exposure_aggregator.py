from __future__ import annotations

import threading
import time
from typing import Dict

from .exposure_model import ExposureModel
from .exposure_snapshot import GlobalExposureSnapshot
from ..models.order import Order


class ExposureAggregator:
    def __init__(self):
        self._lock = threading.Lock()
        self._symbol_exposures: Dict[str, ExposureModel] = {}
        self._exchange_exposures: Dict[str, ExposureModel] = {}
        self._global_exposure = ExposureModel.empty()
        self._latest_snapshot = GlobalExposureSnapshot({}, {}, self._global_exposure.copy())

    def update_after_fill(self, order: Order, fill_price: float, fill_size: float) -> GlobalExposureSnapshot:
        signed_notional = fill_size * fill_price * (1 if order.side.upper() == "BUY" else -1)
        with self._lock:
            self._apply_delta(self._symbol_exposures, order.symbol, signed_notional, order.exchange)
            self._apply_delta(self._exchange_exposures, order.exchange, signed_notional, order.symbol)
            self._apply_delta({"global": self._global_exposure}, "global", signed_notional, order.exchange)
            self._latest_snapshot = GlobalExposureSnapshot(
                symbol_exposures={k: v.copy() for k, v in self._symbol_exposures.items()},
                exchange_exposures={k: v.copy() for k, v in self._exchange_exposures.items()},
                global_exposure=self._global_exposure.copy(),
                timestamp=time.time(),
            )
            return self._latest_snapshot

    def latest_snapshot(self) -> GlobalExposureSnapshot:
        with self._lock:
            return GlobalExposureSnapshot(
                symbol_exposures={k: v.copy() for k, v in self._symbol_exposures.items()},
                exchange_exposures={k: v.copy() for k, v in self._exchange_exposures.items()},
                global_exposure=self._global_exposure.copy(),
                timestamp=self._latest_snapshot.timestamp,
            )

    def _apply_delta(self, store: Dict[str, ExposureModel], key: str, delta: float, sub_key: str) -> None:
        model = store.get(key)
        if not model:
            model = ExposureModel.empty()
            store[key] = model
        model.net_exposure += delta
        model.gross_exposure += abs(delta)
        if delta >= 0:
            model.long_exposure += delta
        else:
            model.short_exposure += abs(delta)
        per_exchange = model.per_exchange_exposure
        per_exchange[sub_key] = per_exchange.get(sub_key, 0.0) + delta
        model.timestamp = time.time()
