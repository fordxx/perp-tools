from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RsiThresholds:
    rsi: float
    long_threshold: float
    short_threshold: float


def _sma(values: list[float], length: int) -> list[float]:
    if length <= 1:
        return values[:]
    out: list[float] = []
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= length:
            window_sum -= values[i - length]
        if i + 1 >= length:
            out.append(window_sum / length)
        else:
            out.append(v)
    return out


def _ema(values: list[float], length: int) -> list[float]:
    if length <= 1 or not values:
        return values[:]
    alpha = 2.0 / (length + 1.0)
    out: list[float] = []
    ema_val = values[0]
    for v in values:
        ema_val = (v - ema_val) * alpha + ema_val
        out.append(ema_val)
    return out


def _rma(values: list[float], length: int) -> list[float]:
    if length <= 1 or not values:
        return values[:]
    alpha = 1.0 / length
    out: list[float] = []
    rma_val = values[0]
    for v in values:
        rma_val = (v - rma_val) * alpha + rma_val
        out.append(rma_val)
    return out


def _apply_ma(values: list[float], length: int, ma_type: str) -> list[float]:
    t = ma_type.strip().lower()
    if t == "sma":
        return _sma(values, length)
    if t == "rma":
        return _rma(values, length)
    # default to EMA (matches script default)
    return _ema(values, length)


def _rsi(values: list[float], length: int) -> list[float]:
    if length <= 1 or len(values) < length + 1:
        return []
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[:length]) / length
    avg_loss = sum(losses[:length]) / length
    rsis: list[float] = []
    if avg_loss == 0:
        rsis.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsis.append(100.0 - (100.0 / (1.0 + rs)))
    for i in range(length, len(gains)):
        avg_gain = (avg_gain * (length - 1) + gains[i]) / length
        avg_loss = (avg_loss * (length - 1) + losses[i]) / length
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(100.0 - (100.0 / (1.0 + rs)))
    return rsis


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    sorted_vals = sorted(values)
    idx = (len(sorted_vals) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    if lo == hi:
        return sorted_vals[lo]
    weight = idx - lo
    return sorted_vals[lo] * (1.0 - weight) + sorted_vals[hi] * weight


def _kmeans_1d(values: list[float], max_iter: int) -> list[float] | None:
    if len(values) < 3:
        return None
    centroids = [
        _percentile(values, 25.0),
        _percentile(values, 50.0),
        _percentile(values, 75.0),
    ]
    for _ in range(max_iter):
        clusters = [[], [], []]
        for v in values:
            distances = [abs(v - c) for c in centroids]
            idx = distances.index(min(distances))
            clusters[idx].append(v)
        new_centroids = []
        for i, cluster in enumerate(clusters):
            if cluster:
                new_centroids.append(sum(cluster) / len(cluster))
            else:
                new_centroids.append(centroids[i])
        if new_centroids == centroids:
            break
        centroids = new_centroids
    return centroids


def compute_rsi_thresholds(
    closes: Iterable[float],
    *,
    rsi_length: int,
    smooth: bool,
    smooth_period: int,
    ma_type: str,
    max_data: int,
    max_iter: int,
) -> RsiThresholds | None:
    values = list(closes)
    if len(values) < rsi_length + 1:
        return None
    rsi_series = _rsi(values, rsi_length)
    if not rsi_series:
        return None
    if smooth:
        rsi_series = _apply_ma(rsi_series, smooth_period, ma_type)
    tail = rsi_series[-max_data:] if max_data > 0 else rsi_series
    centroids = _kmeans_1d(tail, max_iter)
    if not centroids:
        return None
    long_s = max(centroids)
    short_s = min(centroids)
    return RsiThresholds(rsi=rsi_series[-1], long_threshold=long_s, short_threshold=short_s)


def compute_rsi_thresholds_percentile(
    closes: Iterable[float],
    *,
    rsi_length: int,
    smooth: bool,
    smooth_period: int,
    ma_type: str,
    max_data: int,
    low_pct: float = 25.0,
    high_pct: float = 75.0,
) -> RsiThresholds | None:
    values = list(closes)
    if len(values) < rsi_length + 1:
        return None
    rsi_series = _rsi(values, rsi_length)
    if not rsi_series:
        return None
    if smooth:
        rsi_series = _apply_ma(rsi_series, smooth_period, ma_type)
    tail = rsi_series[-max_data:] if max_data > 0 else rsi_series
    long_s = _percentile(tail, high_pct)
    short_s = _percentile(tail, low_pct)
    return RsiThresholds(rsi=rsi_series[-1], long_threshold=long_s, short_threshold=short_s)
