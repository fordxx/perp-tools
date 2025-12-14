#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass(frozen=True)
class SoakRun:
    exchange_a: str
    exchange_b: str
    symbol_a: str
    symbol_b: str
    skip_account: bool = False


def load_profile(path: Path) -> List[SoakRun]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    runs_raw = data.get("runs") if isinstance(data, dict) else None
    if not isinstance(runs_raw, list) or not runs_raw:
        raise ValueError(f"Invalid profile: {path}")
    runs: List[SoakRun] = []
    for item in runs_raw:
        if not isinstance(item, dict):
            raise ValueError(f"Invalid run entry in {path}: {item!r}")
        runs.append(
            SoakRun(
                exchange_a=str(item["exchange_a"]),
                exchange_b=str(item["exchange_b"]),
                symbol_a=str(item.get("symbol_a", "BTC/USDT")),
                symbol_b=str(item.get("symbol_b", "BTC/USDT")),
                skip_account=bool(item.get("skip_account", False)),
            )
        )
    return runs


def main() -> int:
    parser = argparse.ArgumentParser(description="Run sequential dual-exchange soak profiles.")
    parser.add_argument("--profile", required=True, help="Profile name under config/soak_profiles (e.g. cex_core)")
    parser.add_argument("--duration-sec", type=int, default=3600, help="Per-run duration seconds (default: 3600)")
    parser.add_argument("--interval-sec", type=int, default=60, help="Per-run interval seconds (default: 60)")
    parser.add_argument("--jitter-sec", type=float, default=0.5, help="Per-run jitter seconds (default: 0.5)")
    parser.add_argument("--auto-confirm", action="store_true", help="Pass AUTO_CONFIRM=true to avoid prompts")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    profile_path = root / "config" / "soak_profiles" / f"{args.profile}.yaml"
    if not profile_path.exists():
        raise SystemExit(f"Profile not found: {profile_path}")

    runs = load_profile(profile_path)

    start_dual = root / "START_DUAL_EXCHANGE_TEST.sh"
    if not start_dual.exists():
        raise SystemExit(f"Missing: {start_dual}")

    for idx, run in enumerate(runs, 1):
        env = os.environ.copy()
        if args.auto_confirm:
            env["AUTO_CONFIRM"] = "true"
        env["USE_SOAK"] = "true"
        env["ENABLE_GUARDIAN"] = "true"
        env["RUN_DURATION_SEC"] = str(args.duration_sec)
        env["MONITOR_INTERVAL"] = str(args.interval_sec)
        env["SOAK_JITTER_SEC"] = str(args.jitter_sec)
        env["EXCHANGE_A"] = run.exchange_a
        env["EXCHANGE_B"] = run.exchange_b
        env["SYMBOL_A"] = run.symbol_a
        env["SYMBOL_B"] = run.symbol_b
        env["SKIP_ACCOUNT_CHECKS"] = "true" if run.skip_account else "false"

        print(f"\n=== [{idx}/{len(runs)}] {run.exchange_a}+{run.exchange_b} ===")
        started_at = time.time()
        subprocess.check_call([str(start_dual)], cwd=str(root), env=env)

        # Wait for watchdog completion + summary generation.
        # START_DUAL_EXCHANGE_TEST.sh returns immediately after launching; watchdog generates summary at end.
        time.sleep(args.duration_sec + 20)

        # Print the latest summary path (best-effort).
        summaries = sorted((root / "logs").glob("dual_exchange_summary_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if summaries:
            latest = summaries[0]
            print(f"[profile] latest summary: {latest}")
        elapsed = time.time() - started_at
        print(f"[profile] run elapsed: {elapsed:.0f}s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
