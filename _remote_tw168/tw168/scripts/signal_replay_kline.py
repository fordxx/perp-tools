#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.risk import Candle, fetch_candles_paged


@dataclass(frozen=True)
class Signal:
    inst_id: str
    tf: str
    ts: datetime  # tz-aware


def _parse_ts(ts_raw: str) -> datetime:
    # Accept "2026-01-01 05:54:02+08:00" or ISO "2026-01-01T05:54:02+08:00"
    ts_raw = ts_raw.strip().replace(" ", "T")
    if ts_raw.endswith("Z"):
        ts_raw = ts_raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts_raw)
    if dt.tzinfo is None:
        raise ValueError("timestamp must include timezone offset, e.g. +08:00")
    return dt


def _locate_candle_index(candles: list[Candle], ts_utc: datetime) -> int | None:
    t_ms = int(ts_utc.timestamp() * 1000)
    lo, hi = 0, len(candles) - 1
    best: int | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        if candles[mid].ts_ms <= t_ms:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    xs = sorted(values)
    if pct <= 0:
        return xs[0]
    if pct >= 100:
        return xs[-1]
    k = (len(xs) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return d0 + d1


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay signals: infer 1m price at signal time and analyze subsequent path.")
    ap.add_argument("--okx-base-url", default="https://www.okx.com", help="OKX base URL")
    ap.add_argument(
        "--signal",
        action="append",
        default=[],
        help="Signal spec: INST_ID,TF,TS (TS must include timezone, e.g. 'LTC-USDT-SWAP,1h,2026-01-01 05:54:02+08:00')",
    )
    ap.add_argument("--window-minutes", type=int, default=360, help="Look-ahead window in minutes for 1m MAE/MFE (default: 360)")
    ap.add_argument("--json-out", default="", help="Write full results to JSON file")
    args = ap.parse_args()

    if not args.signal:
        ap.error("at least one --signal is required")

    signals: list[Signal] = []
    for spec in args.signal:
        parts = [p.strip() for p in spec.split(",")]
        if len(parts) != 3:
            raise SystemExit(f"Bad --signal: {spec} (expected 3 comma-separated fields)")
        inst_id, tf, ts_raw = parts
        signals.append(Signal(inst_id=inst_id, tf=tf, ts=_parse_ts(ts_raw)))

    now_utc = datetime.now(timezone.utc)

    results: list[dict[str, Any]] = []
    dd_bps_long: list[float] = []
    dd_bps_short: list[float] = []

    for s in signals:
        ts_utc = s.ts.astimezone(timezone.utc)

        candles_1m = fetch_candles_paged(args.okx_base_url, s.inst_id, "1m", limit=3000)
        idx_1m = _locate_candle_index(candles_1m, ts_utc)
        if idx_1m is None:
            results.append({"inst_id": s.inst_id, "tf": s.tf, "signal_ts_utc": ts_utc.isoformat(), "error": "no_1m_candle"})
            continue

        entry_1m = candles_1m[idx_1m].c
        entry_1m_ts = datetime.fromtimestamp(candles_1m[idx_1m].ts_ms / 1000, tz=timezone.utc)

        # 1m window analysis
        end_utc = min(now_utc, ts_utc + timedelta(minutes=args.window_minutes))
        end_idx_1m = _locate_candle_index(candles_1m, end_utc) or (len(candles_1m) - 1)
        future_1m = candles_1m[idx_1m + 1 : end_idx_1m + 1]
        min_low_1m = min((c.l for c in future_1m), default=entry_1m)
        max_high_1m = max((c.h for c in future_1m), default=entry_1m)
        mae_long_1m_bps = (entry_1m - min_low_1m) / entry_1m * 10000.0
        mae_short_1m_bps = (max_high_1m - entry_1m) / entry_1m * 10000.0

        dd_bps_long.append(mae_long_1m_bps)
        dd_bps_short.append(mae_short_1m_bps)

        # TF candles from around signal to now (coarser context)
        candles_tf = fetch_candles_paged(args.okx_base_url, s.inst_id, s.tf, limit=300)
        idx_tf = _locate_candle_index(candles_tf, ts_utc)
        entry_tf = candles_tf[idx_tf].c if idx_tf is not None else None
        future_tf = candles_tf[idx_tf + 1 :] if idx_tf is not None else []
        min_low_tf = min((c.l for c in future_tf), default=entry_tf) if entry_tf is not None else None
        max_high_tf = max((c.h for c in future_tf), default=entry_tf) if entry_tf is not None else None

        results.append(
            {
                "inst_id": s.inst_id,
                "tf": s.tf,
                "signal_ts_local": s.ts.isoformat(),
                "signal_ts_utc": ts_utc.isoformat(),
                "entry_1m": round(entry_1m, 8),
                "entry_1m_candle_ts_utc": entry_1m_ts.isoformat(),
                "window_minutes": args.window_minutes,
                "min_low_1m": round(min_low_1m, 8),
                "max_high_1m": round(max_high_1m, 8),
                "mae_long_1m_bps": round(mae_long_1m_bps, 2),
                "mae_short_1m_bps": round(mae_short_1m_bps, 2),
                "entry_tf_close": round(entry_tf, 8) if entry_tf is not None else None,
                "min_low_tf": round(min_low_tf, 8) if min_low_tf is not None else None,
                "max_high_tf": round(max_high_tf, 8) if max_high_tf is not None else None,
            }
        )

    rec = {
        "long": {
            "n": len(dd_bps_long),
            "p50_bps": round(float(_percentile(dd_bps_long, 50) or 0.0), 2),
            "p80_bps": round(float(_percentile(dd_bps_long, 80) or 0.0), 2),
            "L1_bps": round(float(_percentile(dd_bps_long, 30) or 0.0), 2),
            "L2_bps": round(float(_percentile(dd_bps_long, 70) or 0.0), 2),
        },
        "short": {
            "n": len(dd_bps_short),
            "p50_bps": round(float(_percentile(dd_bps_short, 50) or 0.0), 2),
            "p80_bps": round(float(_percentile(dd_bps_short, 80) or 0.0), 2),
            "L1_bps": round(float(_percentile(dd_bps_short, 30) or 0.0), 2),
            "L2_bps": round(float(_percentile(dd_bps_short, 70) or 0.0), 2),
        },
    }

    out = {"results": results, "recommendation_bps": rec}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"signals={len(results)} window_minutes={args.window_minutes}")
    for r in results:
        if "error" in r:
            print(r["inst_id"], r["tf"], r["signal_ts_utc"], "ERROR", r["error"])
            continue
        print(
            r["signal_ts_local"],
            r["inst_id"],
            r["tf"],
            f"entry_1m={r['entry_1m']}",
            f"MAE_long_1m={r['mae_long_1m_bps']}bps",
            f"MAE_short_1m={r['mae_short_1m_bps']}bps",
        )
    print("")
    print("recommendation (bps from signal price):")
    print("  long:", rec["long"])
    print("  short:", rec["short"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

