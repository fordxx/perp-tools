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


@dataclass
class EntryState:
    side: str
    entry_price: float
    stop_loss: float
    ts: float


class InMemoryState:
    def __init__(self) -> None:
        self.zone_by_key: dict[str, ZoneState] = {}
        self.last_trade_ts_by_key: dict[str, float] = {}
        self.processed: dict[str, float] = {}
        self.entry_by_inst: dict[str, EntryState] = {}
        # Track pending ladder orders per position key (inst_id:tf)
        # Format: {key: [{"order_id": "123", "symbol": "EIGEN/USDT", "level": "L1"}, ...]}
        self.pending_orders_by_key: dict[str, list[dict[str, str]]] = {}
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
            entries = data.get("entry_by_inst") or {}
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
            for key, payload in entries.items():
                if not isinstance(payload, dict):
                    continue
                side = payload.get("side")
                entry_price = payload.get("entry_price")
                stop_loss = payload.get("stop_loss")
                ts_val = payload.get("ts")
                if isinstance(side, str) and isinstance(entry_price, (int, float)) and isinstance(stop_loss, (int, float)) and isinstance(ts_val, (int, float)):
                    self.entry_by_inst[key] = EntryState(
                        side=side,
                        entry_price=float(entry_price),
                        stop_loss=float(stop_loss),
                        ts=float(ts_val),
                    )
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
                "entry_by_inst": {
                    key: {
                        "side": value.side,
                        "entry_price": value.entry_price,
                        "stop_loss": value.stop_loss,
                        "ts": value.ts,
                    }
                    for key, value in self.entry_by_inst.items()
                },
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

    def set_entry(self, inst_id: str, side: str, entry_price: float, stop_loss: float) -> None:
        self.entry_by_inst[inst_id] = EntryState(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            ts=time(),
        )
        self._persist()

    def get_entry(self, inst_id: str, *, ttl_seconds: int) -> EntryState | None:
        entry = self.entry_by_inst.get(inst_id)
        if entry is None:
            return None
        if (time() - entry.ts) > ttl_seconds:
            self.entry_by_inst.pop(inst_id, None)
            self._persist()
            return None
        return entry

    def clear_entry(self, inst_id: str) -> None:
        if inst_id in self.entry_by_inst:
            self.entry_by_inst.pop(inst_id, None)
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

    def add_pending_order(self, key: str, order_id: str, symbol: str, level: str = "") -> None:
        """Record a pending ladder order for a position."""
        if key not in self.pending_orders_by_key:
            self.pending_orders_by_key[key] = []
        self.pending_orders_by_key[key].append({
            "order_id": order_id,
            "symbol": symbol,
            "level": level,
        })
        self._logger.info("state added_pending_order key=%s order_id=%s level=%s", key, order_id, level)

    def get_pending_orders(self, key: str) -> list[dict[str, str]]:
        """Get all pending orders for a position."""
        return self.pending_orders_by_key.get(key, [])

    def clear_pending_orders(self, key: str) -> None:
        """Clear all pending orders for a position after cancellation."""
        count = len(self.pending_orders_by_key.get(key, []))
        self.pending_orders_by_key.pop(key, None)
        if count > 0:
            self._logger.info("state cleared_pending_orders key=%s count=%d", key, count)
