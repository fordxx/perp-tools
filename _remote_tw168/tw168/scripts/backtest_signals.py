#!/usr/bin/env python3
"""Simple backtest of signals recorded by `app.signal_audit.append_event`.

Usage:
  python scripts/backtest_signals.py --date 20260103

What it does:
 - Reads SIGNAL_AUDIT_DIR/tv_signals_<DATE>.jsonl (default DATE=UTC today)
 - Filters DIV signals (type=="DIV" / event contains signal fields)
 - For each signal: fetches candles via app.risk.fetch_candles and finds the candle
   at/after the signal timestamp, treats that as entry, computes stop-loss using
   stop_loss_price_lookback (configurable lookback), computes TP (tp4), then scans
   forward up to N bars to see whether SL or TP hits first.
 - Prints a summary: total signals, wins/losses, winrate, avg R.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

# Ensure repo package imports work when running from repo root
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.signal_audit import _audit_dir
from app.config import SETTINGS, get_lookback_bars
from app.risk import fetch_candles, Candle, stop_loss_price_lookback, take_profit_price


def parse_iso(ts: str) -> Optional[float]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.timestamp() * 1000.0
    except Exception:
        return None


def load_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Audit file not found: {path}")
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            out.append(obj)
    return out


def find_signal_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sigs: List[Dict[str, Any]] = []
    for e in events:
        typ = e.get("type") or e.get("data", {}).get("type")
        if typ and str(typ).upper() == "DIV":
            sigs.append(e)
        else:
            if e.get("event") in {"tv_webhook_received", "tv_webhook_validated", "tv_webhook_decision"} and e.get("type", "").upper() == "DIV":
                sigs.append(e)
    return sigs


def simulate_signal(sig: Dict[str, Any], future_bars: int = 200) -> Optional[Dict[str, Any]]:
    inst = sig.get("instId") or sig.get("instid") or sig.get("instrument")
    if not inst:
        return None
    tf = sig.get("tf") or "1h"

    ts_iso = sig.get("t") or sig.get("ts") or sig.get("ts_iso")
    ts_ms = parse_iso(ts_iso) if isinstance(ts_iso, str) else None

    entry_close = None
    if "close" in sig and sig.get("close") is not None:
        try:
            entry_close = float(sig.get("close"))
        except Exception:
            entry_close = None

    try:
        candles: List[Candle] = fetch_candles(SETTINGS.okx_base_url, inst, tf, limit=1000)
    except Exception as exc:
        return {"instId": inst, "tf": tf, "error": f"fetch_candles_failed: {exc}"}

    if not candles:
        return {"instId": inst, "tf": tf, "error": "no_candles"}

    entry_idx = len(candles) - 1
    if ts_ms is not None:
        for i, c in enumerate(candles):
            if c.ts_ms >= ts_ms:
                entry_idx = i
                break

    entry_price = entry_close if entry_close is not None else candles[entry_idx].c

    lookback = get_lookback_bars(tf)
    try:
        sl = stop_loss_price_lookback(
            side=("buy" if (sig.get("side", "").lower() in {"buy","long"}) else "sell"),
            entry_price=float(entry_price),
            candles=candles,
            lookback_bars=lookback,
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    except Exception:
        sl = None

    if sl is None:
        return {"instId": inst, "tf": tf, "entry": entry_price, "error": "no_sl_computed"}

    side = "buy" if (sig.get("side", "").lower() in {"buy","long"}) else "sell"
    tp = take_profit_price(side=side, entry_price=float(entry_price), stop_loss=float(sl), rr=SETTINGS.tp4_r)
    if tp is None:
        return {"instId": inst, "tf": tf, "entry": entry_price, "sl": sl, "error": "no_tp"}

    hit = None
    hit_bar = None
    for j in range(entry_idx + 1, min(len(candles), entry_idx + 1 + future_bars)):
        c = candles[j]
        high = c.h
        low = c.l
        if side == "buy":
            if low <= sl:
                hit = "sl"
                hit_bar = j
                break
            if high >= tp:
                hit = "tp"
                hit_bar = j
                break
        else:
            if high >= sl:
                hit = "sl"
                hit_bar = j
                break
            if low <= tp:
                hit = "tp"
                hit_bar = j
                break

    r = None
    if hit is not None:
        if hit == "tp":
            profit = (tp - entry_price) if side == "buy" else (entry_price - tp)
        else:
            profit = (entry_price - sl) if side == "buy" else (sl - entry_price)
        r = profit / abs(entry_price - sl) if abs(entry_price - sl) > 0 else None

    return {
        "instId": inst,
        "tf": tf,
        "side": side,
        "entry": float(entry_price),
        "sl": float(sl),
        "tp": float(tp),
        "hit": hit,
        "hit_bar": hit_bar,
        "r": float(r) if r is not None else None,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="YYYYMMDD (UTC). Defaults to today UTC")
    p.add_argument("--future_bars", default=200, type=int)
    args = p.parse_args()

    date = args.date
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y%m%d")

    audit_dir = _audit_dir()
    path = Path(audit_dir) / f"tv_signals_{date}.jsonl"
    print(f"Using audit file: {path}")
    try:
        events = load_events(path)
    except Exception as e:
        print(f"Failed to load events: {e}")
        return

    sigs = find_signal_events(events)
    print(f"Found {len(sigs)} DIV signals in file")

    results = []
    for s in sigs:
        res = simulate_signal(s, future_bars=args.future_bars)
        if res:
            results.append(res)

    wins = [r for r in results if r.get("hit") == "tp"]
    losses = [r for r in results if r.get("hit") == "sl"]
    others = [r for r in results if r.get("hit") not in {"tp", "sl"}]

    print("--- Backtest Summary ---")
    print(f"Total signals: {len(results)}")
    print(f"TP hits: {len(wins)}")
    print(f"SL hits: {len(losses)}")
    print(f"No hit within window: {len(others)}")
    winrate = (len(wins) / len(results) * 100.0) if results else 0.0
    avg_r = (sum(r.get("r", 0.0) or 0.0 for r in wins) / len(wins)) if wins else 0.0
    print(f"Winrate: {winrate:.1f}%  Avg R (wins only): {avg_r:.3f}")

    print("--- Sample results ---")
    for r in results[:20]:
        print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
