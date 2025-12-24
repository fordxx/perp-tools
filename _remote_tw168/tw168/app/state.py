from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass
class ZoneState:
    zone: str
    ts: float
    close: float | None = None


class InMemoryState:
    def __init__(self) -> None:
        self.zone_by_key: dict[str, ZoneState] = {}
        self.last_trade_ts_by_key: dict[str, float] = {}
        self.processed: dict[str, float] = {}

    def set_zone(self, key: str, zone: str, close: float | None) -> None:
        self.zone_by_key[key] = ZoneState(zone=zone, ts=time(), close=close)

    def clear_zone(self, key: str) -> None:
        """Clear zone state after it has been used for trading."""
        self.zone_by_key.pop(key, None)

    def get_zone(self, key: str) -> ZoneState | None:
        return self.zone_by_key.get(key)

    def can_trade(self, key: str, cooldown_seconds: int) -> bool:
        last_ts = self.last_trade_ts_by_key.get(key)
        if last_ts is None:
            return True
        return (time() - last_ts) >= cooldown_seconds

    def mark_traded(self, key: str) -> None:
        self.last_trade_ts_by_key[key] = time()

    def seen(self, dedupe_key: str, ttl_seconds: int) -> bool:
        now = time()
        # cleanup opportunistically
        for k, ts in list(self.processed.items()):
            if (now - ts) > ttl_seconds:
                self.processed.pop(k, None)
        if dedupe_key in self.processed:
            return True
        self.processed[dedupe_key] = now
        return False

