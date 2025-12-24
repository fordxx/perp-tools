from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class EntryInfo:
    side: str
    entry_price: float
    stop_loss: float
    ts: float


class FillTracker:
    def __init__(self, *, ttl_seconds: float = 6 * 60 * 60) -> None:
        self._ttl_seconds = ttl_seconds
        self._entries: dict[str, EntryInfo] = {}
        self._order_labels: dict[str, tuple[str, float]] = {}
        self._algo_labels: dict[str, tuple[str, float]] = {}

    def register_entry(self, *, inst_id: str, side: str, entry_price: float, stop_loss: float) -> None:
        self._entries[inst_id] = EntryInfo(
            side=side,
            entry_price=entry_price,
            stop_loss=stop_loss,
            ts=time.time(),
        )

    def register_order_label(self, *, key: str, label: str) -> None:
        self._order_labels[key] = (label, time.time())

    def register_algo_label(self, *, algo_id: str, label: str) -> None:
        self._algo_labels[algo_id] = (label, time.time())

    def get_order_label(self, *, key: str) -> Optional[str]:
        value = self._order_labels.get(key)
        if not value:
            return None
        label, ts = value
        if time.time() - ts > self._ttl_seconds:
            self._order_labels.pop(key, None)
            return None
        return label

    def get_algo_label(self, *, algo_id: str) -> Optional[str]:
        value = self._algo_labels.get(algo_id)
        if not value:
            return None
        label, ts = value
        if time.time() - ts > self._ttl_seconds:
            self._algo_labels.pop(algo_id, None)
            return None
        return label

    def classify_exit(self, *, inst_id: str, trade_side: str, price: float) -> Optional[str]:
        info = self._entries.get(inst_id)
        if info is None:
            return None
        if time.time() - info.ts > self._ttl_seconds:
            self._entries.pop(inst_id, None)
            return None

        entry_side = info.side.lower()
        trade_side = trade_side.lower()
        # Only consider opposite-side trades as exits.
        if entry_side == "buy" and trade_side != "sell":
            return None
        if entry_side == "sell" and trade_side != "buy":
            return None

        if entry_side == "buy":
            return "tp" if price >= info.entry_price else "sl"
        return "tp" if price <= info.entry_price else "sl"
