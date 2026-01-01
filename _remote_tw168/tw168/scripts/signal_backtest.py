#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.risk import Candle, fetch_candles_paged


_RE_RECEIVED = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*tv_webhook received "
    r"type=(?P<type>\w+)\s+instId=(?P<instId>[A-Z0-9\-]+)\s+tf=(?P<tf>[\w]+)\s+"
    r"zone=(?P<zone>[^ ]+)\s+t=(?P<t>[^ ]+)\s+close=(?P<close>[^ ]+)"
)

_RE_ORDER_PLACED = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*tv_webhook decision "
    r"instId=(?P<instId>[A-Z0-9\-]+)\s+tf=(?P<tf>[\w]+)\s+action=order_placed\s+"
    r"side=(?P<side>buy|sell)\s+posSide=(?P<posSide>long|short)\b"
)


@dataclass(frozen=True)
class ReceivedEvent:
    log_ts: datetime
    typ: str
    inst_id: str
    tf: str
    t_raw: str
    close_raw: str

    @property
    def signal_ts_utc(self) -> datetime | None:
        raw = self.t_raw
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)

    @property
    def close(self) -> float | None:
        try:
            if self.close_raw == "None":
                return None
            return float(self.close_raw)
        except ValueError:
            return None


@dataclass(frozen=True)
class OrderPlacedEvent:
    log_ts: datetime
    inst_id: str
    tf: str
    side: str
    pos_side: str


def _parse_log_ts(ts: str) -> datetime:
    # These logs are local-time formatted without timezone; treat as UTC for relative matching only.
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def parse_events(log_text: str) -> tuple[list[ReceivedEvent], list[OrderPlacedEvent]]:
    received: list[ReceivedEvent] = []
    placed: list[OrderPlacedEvent] = []
    for line in log_text.splitlines():
        m = _RE_RECEIVED.match(line)
        if m:
            received.append(
                ReceivedEvent(
                    log_ts=_parse_log_ts(m.group("ts")),
                    typ=m.group("type"),
                    inst_id=m.group("instId"),
                    tf=m.group("tf"),
                    t_raw=m.group("t"),
                    close_raw=m.group("close"),
                )
            )
            continue
        m = _RE_ORDER_PLACED.match(line)
        if m:
            placed.append(
                OrderPlacedEvent(
                    log_ts=_parse_log_ts(m.group("ts")),
                    inst_id=m.group("instId"),
                    tf=m.group("tf"),
                    side=m.group("side"),
                    pos_side=m.group("posSide"),
                )
            )
    received.sort(key=lambda e: e.log_ts)
    placed.sort(key=lambda e: e.log_ts)
    return received, placed


def _find_matching_received(
    received: list[ReceivedEvent],
    placed: OrderPlacedEvent,
    *,
    max_seconds: int = 180,
) -> ReceivedEvent | None:
    best: ReceivedEvent | None = None
    best_dt_s: float | None = None
    for r in reversed(received):
        if r.log_ts > placed.log_ts:
            continue
        if r.typ.upper() != "DIV":
            continue
        if r.inst_id != placed.inst_id or r.tf != placed.tf:
            continue
        dt_s = (placed.log_ts - r.log_ts).total_seconds()
        if dt_s < 0 or dt_s > max_seconds:
            continue
        if best is None or dt_s < (best_dt_s or math.inf):
            best = r
            best_dt_s = dt_s
            if dt_s <= 2:
                break
    return best


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    xs = sorted(values)
    k = (len(xs) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return d0 + d1


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


def recommend_two_layer_offsets(
    maes_bps: list[float],
    *,
    l1_hit_rate_target: float = 0.7,
    l2_hit_rate_target: float = 0.4,
) -> dict[str, Any]:
    # Use hit-rate targets to avoid overfitting to a single extreme.
    if not maes_bps:
        return {}
    maes_sorted = sorted(maes_bps)

    def bps_for_hit_rate(target: float) -> float:
        # Need bps such that fraction(mae >= bps) ~= target
        # i.e. bps near percentile (1-target).
        pct = max(0.0, min(100.0, (1.0 - target) * 100.0))
        val = _percentile(maes_sorted, pct)
        return float(val) if val is not None else float(maes_sorted[0])

    l1_bps = bps_for_hit_rate(l1_hit_rate_target)
    l2_bps = bps_for_hit_rate(l2_hit_rate_target)
    # Ensure L2 deeper than L1
    if l2_bps <= l1_bps:
        l2_bps = max(l1_bps + 5.0, float(_percentile(maes_sorted, 80) or (l1_bps + 5.0)))

    def hit_rate(bps: float) -> float:
        return sum(1 for x in maes_bps if x >= bps) / float(len(maes_bps))

    return {
        "count": len(maes_bps),
        "mae_p50_bps": round(float(_percentile(maes_bps, 50) or 0.0), 2),
        "mae_p80_bps": round(float(_percentile(maes_bps, 80) or 0.0), 2),
        "l1_bps": round(l1_bps, 2),
        "l1_hit_rate": round(hit_rate(l1_bps), 3),
        "l2_bps": round(l2_bps, 2),
        "l2_hit_rate": round(hit_rate(l2_bps), 3),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze tv_webhook order_placed events and derive 2-layer entry offsets.")
    ap.add_argument("--log", default="tw168.log", help="Path to log file (default: tw168.log)")
    ap.add_argument("--okx-base-url", default="https://www.okx.com", help="OKX base URL")
    ap.add_argument("--horizon-by-tf", default="1m:180,15m:24,30m:16,1h:10,4h:6", help="Future window size in candles, e.g. '30m:16,1h:10'")
    ap.add_argument("--json-out", default="", help="Write full results to JSON file")
    args = ap.parse_args()

    horizon_by_tf: dict[str, int] = {}
    for part in args.horizon_by_tf.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        k, v = part.split(":", 1)
        try:
            horizon_by_tf[k.strip()] = int(v.strip())
        except ValueError:
            continue

    log_path = Path(args.log)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    received, placed = parse_events(log_text)

    # Group for candle fetching.
    groups: dict[tuple[str, str], list[datetime]] = {}
    matches: list[dict[str, Any]] = []
    for p in placed:
        r = _find_matching_received(received, p)
        sig_ts = r.signal_ts_utc if r else None
        if sig_ts is None:
            sig_ts = p.log_ts
        matches.append(
            {
                "log_ts_utc": p.log_ts.isoformat(),
                "signal_ts_utc": sig_ts.isoformat(),
                "inst_id": p.inst_id,
                "tf": p.tf,
                "side": p.side,
                "pos_side": p.pos_side,
                "payload_close": (r.close if r else None),
                "payload_t": (r.t_raw if r else None),
            }
        )
        groups.setdefault((p.inst_id, p.tf), []).append(sig_ts)

    candles_cache: dict[tuple[str, str], list[Candle]] = {}
    for (inst_id, tf) in groups.keys():
        # Fetch enough bars to cover the recent history; keep it simple and robust.
        candles_cache[(inst_id, tf)] = fetch_candles_paged(args.okx_base_url, inst_id, tf, limit=3000)

    # Enrich with inferred entry and MAE.
    mae_by_tf_side: dict[tuple[str, str], list[float]] = {}
    for row in matches:
        inst_id = row["inst_id"]
        tf = row["tf"]
        side = row["side"]
        sig_ts = datetime.fromisoformat(row["signal_ts_utc"])
        candles = candles_cache.get((inst_id, tf)) or []
        idx = _locate_candle_index(candles, sig_ts)
        # Some historical logs have no parseable payload t=...; try common timezone shifts.
        if idx is None and row.get("payload_t") is None:
            for hours in (8, -8):
                alt = sig_ts + timedelta(hours=hours)
                idx = _locate_candle_index(candles, alt)
                if idx is not None:
                    row["signal_ts_utc"] = alt.isoformat()
                    sig_ts = alt
                    break
        if idx is None:
            row["entry_px"] = None
            row["mae_bps"] = None
            row["mae_window"] = None
            continue
        entry_px = candles[idx].c
        horizon = horizon_by_tf.get(tf, 16)
        future = candles[idx + 1 : idx + 1 + horizon]
        if not future:
            row["entry_px"] = entry_px
            row["mae_bps"] = None
            row["mae_window"] = horizon
            continue
        if side == "buy":
            worst = min(c.l for c in future)
            mae_bps = (entry_px - worst) / entry_px * 10000.0
        else:
            worst = max(c.h for c in future)
            mae_bps = (worst - entry_px) / entry_px * 10000.0
        row["entry_px"] = round(entry_px, 8)
        row["mae_bps"] = round(mae_bps, 2)
        row["mae_window"] = horizon
        mae_by_tf_side.setdefault((tf, side), []).append(mae_bps)

    recommendations: dict[str, Any] = {}
    for (tf, side), maes in sorted(mae_by_tf_side.items()):
        recommendations[f"{tf}:{side}"] = recommend_two_layer_offsets(maes)

    out = {"events": matches, "recommendations": recommendations, "horizon_by_tf": horizon_by_tf}
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # Human-readable summary
    print(f"order_placed_events={len(matches)}")
    print("")
    print("== order_placed (signal_ts_utc, instId, tf, side, entry_px, mae_bps) ==")
    for row in matches:
        print(
            row["signal_ts_utc"],
            row["inst_id"],
            row["tf"],
            row["side"],
            f"entry={row.get('entry_px')}",
            f"mae_bps={row.get('mae_bps')}",
        )
    print("")
    print("== recommended 2-layer offsets (bps from signal close) ==")
    for k, v in recommendations.items():
        if not v:
            continue
        print(
            k,
            f"n={v['count']}",
            f"L1={v['l1_bps']}bps(hit={v['l1_hit_rate']})",
            f"L2={v['l2_bps']}bps(hit={v['l2_hit_rate']})",
            f"p50={v['mae_p50_bps']} p80={v['mae_p80_bps']}",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
