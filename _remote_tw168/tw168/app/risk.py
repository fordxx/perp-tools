from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import requests


Side = Literal["buy", "sell"]
PosSide = Literal["long", "short"]


@dataclass(frozen=True)
class Candle:
    ts_ms: int
    o: float
    h: float
    l: float
    c: float


def fetch_candles(base_url: str, inst_id: str, bar: str, limit: int = 300) -> list[Candle]:
    url = f"{base_url}/api/v5/market/candles"
    resp = requests.get(url, params={"instId": inst_id, "bar": bar, "limit": str(limit)}, timeout=10)
    resp.raise_for_status()
    payload = resp.json()
    data = payload.get("data", [])
    # OKX returns newest-first; convert to oldest-first.
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


def fetch_candles_paged(base_url: str, inst_id: str, bar: str, limit: int = 3000) -> list[Candle]:
    if limit <= 300:
        return fetch_candles(base_url, inst_id, bar, limit=limit)
    all_rows: list[list[str]] = []
    before: str | None = None
    last_before: str | None = None
    remaining = limit
    while remaining > 0:
        page_limit = min(300, remaining)
        params = {"instId": inst_id, "bar": bar, "limit": str(page_limit)}
        if before:
            params["before"] = before
        resp = requests.get(f"{base_url}/api/v5/market/candles", params=params, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data", [])
        if not data:
            break
        all_rows.extend(data)
        last_ts = data[-1][0]
        if last_ts == last_before:
            break
        last_before = last_ts
        before = last_ts
        remaining -= len(data)
    # OKX returns newest-first; convert to oldest-first.
    candles: list[Candle] = []
    for row in reversed(all_rows):
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
    # Find the most recent confirmed pivot low (needs pivot_len bars on both sides).
    n = len(candles)
    min_required = pivot_len * 2 + 3
    if n < min_required:
        return None
    start_idx = n - pivot_len - 2
    end_idx = pivot_len
    if start_idx < end_idx:
        return None
    for i in range(start_idx, end_idx, -1):
        center = candles[i].l
        left = [candles[j].l for j in range(i - pivot_len, i)]
        right = [candles[j].l for j in range(i + 1, i + 1 + pivot_len)]
        if center <= min(left) and center < min(right):
            return center
    return None


def last_pivot_high(candles: list[Candle], pivot_len: int) -> float | None:
    n = len(candles)
    min_required = pivot_len * 2 + 3
    if n < min_required:
        return None
    start_idx = n - pivot_len - 2
    end_idx = pivot_len
    if start_idx < end_idx:
        return None
    for i in range(start_idx, end_idx, -1):
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


PivotType = Literal["H", "L"]


@dataclass(frozen=True)
class Pivot:
    idx: int
    kind: PivotType
    price: float


def _extract_pivots(candles: list[Candle], pivot_len: int, max_pivots: int = 12) -> list[Pivot]:
    if pivot_len <= 0:
        return []
    n = len(candles)
    if n < pivot_len * 2 + 3:
        return []

    pivots: list[Pivot] = []
    # Exclude the most recent bar to reduce "still forming" artifacts.
    end = n - 2
    for i in range(pivot_len, end - pivot_len):
        h = candles[i].h
        l = candles[i].l
        left_h = max(candles[j].h for j in range(i - pivot_len, i))
        right_h = max(candles[j].h for j in range(i + 1, i + 1 + pivot_len))
        left_l = min(candles[j].l for j in range(i - pivot_len, i))
        right_l = min(candles[j].l for j in range(i + 1, i + 1 + pivot_len))

        is_h = h >= left_h and h > right_h
        is_l = l <= left_l and l < right_l
        if not (is_h or is_l):
            continue
        if is_h and is_l:
            # Rare, but prefer the more extreme move.
            is_h = (h - min(left_l, right_l)) >= (max(left_h, right_h) - l)
            is_l = not is_h
        pivots.append(Pivot(idx=i, kind="H" if is_h else "L", price=h if is_h else l))

    # Keep only the most recent alternating pivots.
    pivots = sorted(pivots, key=lambda p: p.idx)
    compressed: list[Pivot] = []
    for p in pivots:
        if not compressed:
            compressed.append(p)
            continue
        last = compressed[-1]
        if p.kind != last.kind:
            compressed.append(p)
            continue
        # Same kind: keep the more extreme pivot.
        if p.kind == "H" and p.price >= last.price:
            compressed[-1] = p
        elif p.kind == "L" and p.price <= last.price:
            compressed[-1] = p

    return compressed[-max_pivots:]


def _near(a: float, b: float, tol_pct: float) -> bool:
    if a <= 0 or b <= 0:
        return False
    return abs(a - b) / ((a + b) / 2.0) <= tol_pct


@dataclass(frozen=True)
class PatternMatch:
    ok: bool
    name: str
    detail: str


def detect_w_bottom(
    candles: list[Candle],
    *,
    pivot_len: int,
    tol_pct: float,
    min_bounce_pct: float,
    require_breakout: bool,
) -> PatternMatch:
    pivots = _extract_pivots(candles, pivot_len=pivot_len, max_pivots=10)
    if len(pivots) < 3:
        return PatternMatch(False, "w_bottom", "not_enough_pivots")
    # Look for last L-H-L sequence.
    last3 = pivots[-3:]
    if [p.kind for p in last3] != ["L", "H", "L"]:
        return PatternMatch(False, "w_bottom", "no_LHL")

    l1, h1, l2 = last3
    if not _near(l1.price, l2.price, tol_pct=tol_pct):
        return PatternMatch(False, "w_bottom", "lows_not_similar")
    if h1.price <= max(l1.price, l2.price) * (1 + min_bounce_pct):
        return PatternMatch(False, "w_bottom", "bounce_too_small")

    last_close = candles[-1].c
    if require_breakout and last_close <= h1.price:
        return PatternMatch(False, "w_bottom", "no_neckline_break")
    return PatternMatch(True, "w_bottom", "LHL_ok")


def detect_head_shoulders_top(
    candles: list[Candle],
    *,
    pivot_len: int,
    tol_pct: float,
    min_shoulder_drop_pct: float,
    require_breakdown: bool,
) -> PatternMatch:
    pivots = _extract_pivots(candles, pivot_len=pivot_len, max_pivots=12)
    if len(pivots) < 5:
        return PatternMatch(False, "head_shoulders_top", "not_enough_pivots")
    # Look for last H-L-H-L-H sequence.
    last5 = pivots[-5:]
    if [p.kind for p in last5] != ["H", "L", "H", "L", "H"]:
        return PatternMatch(False, "head_shoulders_top", "no_HLHLH")

    h1, l1, h2, l2, h3 = last5
    if not (h2.price > h1.price and h2.price > h3.price):
        return PatternMatch(False, "head_shoulders_top", "head_not_highest")
    if not _near(h1.price, h3.price, tol_pct=tol_pct):
        return PatternMatch(False, "head_shoulders_top", "shoulders_not_similar")
    if (h2.price - max(h1.price, h3.price)) / h2.price < min_shoulder_drop_pct:
        return PatternMatch(False, "head_shoulders_top", "head_not_distinct")

    neckline = (l1.price + l2.price) / 2.0
    last_close = candles[-1].c
    if require_breakdown and last_close >= neckline:
        return PatternMatch(False, "head_shoulders_top", "no_neckline_break")
    return PatternMatch(True, "head_shoulders_top", "HLHLH_ok")
