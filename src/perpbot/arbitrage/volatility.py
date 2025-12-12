from __future__ import annotations

import math
from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict, Tuple


class SpreadVolatilityTracker:
    """Tracks rolling cross-exchange spread volatility for dynamic profit floors."""

    def __init__(self, window_minutes: int = 5, max_points: int = 500) -> None:
        self.window = timedelta(minutes=window_minutes)
        self.max_points = max_points
        self.history: Dict[str, Deque[Tuple[datetime, float]]] = {}

    def record(self, symbol: str, spread_pct: float) -> None:
        now = datetime.utcnow()
        buf = self.history.setdefault(symbol, deque())
        buf.append((now, spread_pct))
        while len(buf) > self.max_points:
            buf.popleft()
        self._prune(buf)

    def _prune(self, buf: Deque[Tuple[datetime, float]]) -> None:
        cutoff = datetime.utcnow() - self.window
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def volatility(self, symbol: str) -> float:
        buf = self.history.get(symbol)
        if not buf or len(buf) < 2:
            return 0.0
        self._prune(buf)
        values = [p[1] for p in buf]
        mean = sum(values) / len(values)
        var = sum((v - mean) ** 2 for v in values) / max(len(values) - 1, 1)
        return math.sqrt(max(var, 0.0))

    def dynamic_min_profit(
        self,
        symbol: str,
        low_vol_min: float,
        high_vol_min: float,
        high_vol_threshold: float,
    ) -> float:
        vol = self.volatility(symbol)
        if vol >= high_vol_threshold:
            return high_vol_min
        return low_vol_min

