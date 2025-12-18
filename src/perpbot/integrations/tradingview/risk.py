from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx


Side = Literal["buy", "sell"]


@dataclass(frozen=True)
class Candle:
    ts_ms: int
    o: float
    h: float
    l: float
    c: float


def fetch_okx_candles(base_url: str, inst_id: str, bar: str, limit: int = 300) -> list[Candle]:
    base = base_url.rstrip("/")
    url = f"{base}/api/v5/market/candles"
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, params={"instId": inst_id, "bar": bar, "limit": str(limit)})
        resp.raise_for_status()
        payload = resp.json()

    data = payload.get("data", [])
    candles: list[Candle] = []
    for row in reversed(data):
        candles.append(
            Candle(
                ts_ms=int(row[0]),
                o=float(row[1]),
                h=float(row[2]),
                l=float(row[3]),
                c=float(row[4]),
            )
        )
    return candles


def true_range(prev_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(candles: list[Candle], length: int) -> float | None:
    if len(candles) < length + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(candles)):
        prev_close = candles[i - 1].c
        trs.append(true_range(prev_close, candles[i].h, candles[i].l))
    window = trs[-length:]
    return sum(window) / float(length)


def last_pivot_low(candles: list[Candle], pivot_len: int) -> float | None:
    n = len(candles)
    if n < (pivot_len * 2 + 3):
        return None
    for i in range(n - pivot_len - 2, pivot_len, -1):
        center = candles[i].l
        left = [candles[j].l for j in range(i - pivot_len, i)]
        right = [candles[j].l for j in range(i + 1, i + 1 + pivot_len)]
        if center <= min(left) and center < min(right):
            return center
    return None


def last_pivot_high(candles: list[Candle], pivot_len: int) -> float | None:
    n = len(candles)
    if n < (pivot_len * 2 + 3):
        return None
    for i in range(n - pivot_len - 2, pivot_len, -1):
        center = candles[i].h
        left = [candles[j].h for j in range(i - pivot_len, i)]
        right = [candles[j].h for j in range(i + 1, i + 1 + pivot_len)]
        if center >= max(left) and center > max(right):
            return center
    return None


def stop_loss_price(
    *,
    side: Side,
    entry_price: float,
    candles: list[Candle],
    pivot_len: int,
    atr_len: int,
    atr_buffer_mult: float,
    min_buffer_bps: float,
) -> float | None:
    atr_value = atr(candles, atr_len)
    if atr_value is None:
        return None
    buffer_by_atr = atr_value * atr_buffer_mult
    buffer_by_bps = entry_price * (min_buffer_bps / 10_000.0)
    buffer = max(buffer_by_atr, buffer_by_bps)
    if side == "buy":
        pl = last_pivot_low(candles, pivot_len)
        if pl is None:
            return None
        return pl - buffer
    ph = last_pivot_high(candles, pivot_len)
    if ph is None:
        return None
    return ph + buffer


def stop_loss_price_lookback(
    *,
    side: Side,
    entry_price: float,
    candles: list[Candle],
    lookback_bars: int,
    atr_len: int,
    atr_buffer_mult: float,
    min_buffer_bps: float,
) -> float | None:
    if lookback_bars <= 1:
        return None
    if len(candles) < max(atr_len + 1, lookback_bars):
        return None
    atr_value = atr(candles, atr_len)
    if atr_value is None:
        return None
    window = candles[-lookback_bars:]
    base = min(c.l for c in window) if side == "buy" else max(c.h for c in window)
    buffer_by_atr = atr_value * atr_buffer_mult
    buffer_by_bps = entry_price * (min_buffer_bps / 10_000.0)
    buffer = max(buffer_by_atr, buffer_by_bps)
    return (base - buffer) if side == "buy" else (base + buffer)


def take_profit_price(*, side: Side, entry_price: float, stop_loss: float, rr: float) -> float | None:
    if rr <= 0:
        return None
    if side == "buy":
        risk = entry_price - stop_loss
        if risk <= 0:
            return None
        return entry_price + (risk * rr)
    risk = stop_loss - entry_price
    if risk <= 0:
        return None
    return entry_price - (risk * rr)

