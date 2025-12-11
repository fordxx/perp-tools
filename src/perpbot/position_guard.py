from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from perpbot.models import Position


class PositionGuard:
    """Applies per-trade risk caps and failure cooldowns."""

    def __init__(self, max_risk_pct: float = 0.05, assumed_equity: float = 10_000.0, cooldown_seconds: int = 30):
        self.max_risk_pct = max_risk_pct
        self.assumed_equity = assumed_equity
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self._last_failure: datetime | None = None

    def update_equity_from_positions(self, positions: Iterable[Position]) -> None:
        equity = self.assumed_equity
        for pos in positions:
            equity += pos.order.price * pos.order.size
        self.assumed_equity = max(equity, 1.0)

    def allow_trade(self, notional: float) -> bool:
        if self._in_cooldown():
            return False
        return notional <= self.assumed_equity * self.max_risk_pct

    def mark_failure(self) -> None:
        self._last_failure = datetime.utcnow()

    def mark_success(self) -> None:
        self._last_failure = None

    def _in_cooldown(self) -> bool:
        if not self._last_failure:
            return False
        return datetime.utcnow() - self._last_failure < self.cooldown
