from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
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
        self._logger = logging.getLogger("uvicorn.error")
        self._store_path = os.getenv("STATE_STORE_PATH", "").strip()
        if self._store_path:
            self._load()

    def _load(self) -> None:
        path = Path(self._store_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            zone = data.get("zone_by_key") or {}
            last_trade = data.get("last_trade_ts_by_key") or {}
            for key, payload in zone.items():
                if not isinstance(payload, dict):
                    continue
                zone_val = payload.get("zone")
                ts_val = payload.get("ts")
                close_val = payload.get("close")
                if isinstance(zone_val, str) and isinstance(ts_val, (int, float)):
                    self.zone_by_key[key] = ZoneState(
                        zone=zone_val,
                        ts=float(ts_val),
                        close=float(close_val) if close_val is not None else None,
                    )
            for key, ts_val in last_trade.items():
                if isinstance(ts_val, (int, float)):
                    self.last_trade_ts_by_key[key] = float(ts_val)
        except Exception:
            self._logger.exception("state store load failed path=%s", self._store_path)

    def _persist(self) -> None:
        if not self._store_path:
            return
        try:
            path = Path(self._store_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "zone_by_key": {
                    key: {"zone": value.zone, "ts": value.ts, "close": value.close}
                    for key, value in self.zone_by_key.items()
                },
                "last_trade_ts_by_key": dict(self.last_trade_ts_by_key),
            }
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False))
            tmp.replace(path)
        except Exception:
            self._logger.exception("state store persist failed path=%s", self._store_path)

    def set_zone(self, key: str, zone: str, close: float | None) -> None:
        self.zone_by_key[key] = ZoneState(zone=zone, ts=time(), close=close)
        self._persist()

    def clear_zone(self, key: str) -> None:
        """Clear zone state after it has been used for trading."""
        self.zone_by_key.pop(key, None)
        self._persist()

    def get_zone(self, key: str) -> ZoneState | None:
        return self.zone_by_key.get(key)

    def can_trade(self, key: str, cooldown_seconds: int) -> bool:
        last_ts = self.last_trade_ts_by_key.get(key)
        if last_ts is None:
            return True
        return (time() - last_ts) >= cooldown_seconds

    def mark_traded(self, key: str) -> None:
        self.last_trade_ts_by_key[key] = time()
        self._persist()

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
