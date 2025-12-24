#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TfPreset:
    pattern_pivot_len: int
    pattern_tol_pct: float
    w_min_bounce_pct: float
    hs_min_shoulder_drop_pct: float


TF_PRESETS: dict[str, TfPreset] = {
    "5m": TfPreset(pattern_pivot_len=3, pattern_tol_pct=0.006, w_min_bounce_pct=0.004, hs_min_shoulder_drop_pct=0.004),
    "15m": TfPreset(pattern_pivot_len=4, pattern_tol_pct=0.006, w_min_bounce_pct=0.005, hs_min_shoulder_drop_pct=0.005),
    "30m": TfPreset(pattern_pivot_len=5, pattern_tol_pct=0.006, w_min_bounce_pct=0.006, hs_min_shoulder_drop_pct=0.006),
}


def parse_env(text: str) -> tuple[dict[str, str], list[str]]:
    kv: dict[str, str] = {}
    lines = text.splitlines(True)
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        kv[key.strip()] = value.strip().strip("\n")
    return kv, lines


def set_env(lines: list[str], key: str, value: str) -> list[str]:
    out: list[str] = []
    found = False
    for line in lines:
        if line.strip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        k, _ = line.split("=", 1)
        if k.strip() == key:
            out.append(f"{key}={value}\n")
            found = True
        else:
            out.append(line)
    if not found:
        if out and not out[-1].endswith("\n"):
            out[-1] = out[-1] + "\n"
        out.append(f"{key}={value}\n")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Edit .env quickly (timeframe presets, patterns, long/short toggles).")
    p.add_argument("--env", default=".env", help="Path to env file (default: .env)")

    p.add_argument("--tf", choices=sorted(TF_PRESETS.keys()), help="Apply timeframe preset for pattern params")

    p.add_argument("--enable-long", action="store_true", help="Set ENABLE_LONG=true")
    p.add_argument("--disable-long", action="store_true", help="Set ENABLE_LONG=false")
    p.add_argument("--enable-short", action="store_true", help="Set ENABLE_SHORT=true")
    p.add_argument("--disable-short", action="store_true", help="Set ENABLE_SHORT=false")

    p.add_argument("--w", action="store_true", help="Enable W-bottom filter for longs (PATTERN_LONG=w_bottom)")
    p.add_argument("--hs", action="store_true", help="Enable Head&Shoulders-top filter for shorts (PATTERN_SHORT=hs_top)")
    p.add_argument("--no-patterns", action="store_true", help="Disable both pattern filters")

    p.add_argument("--require-breakout", action="store_true", help="Require neckline breakout/breakdown for patterns")
    p.add_argument("--no-require-breakout", action="store_true", help="Do not require neckline breakout/breakdown")

    args = p.parse_args()

    if args.enable_long and args.disable_long:
        raise SystemExit("--enable-long and --disable-long are mutually exclusive")
    if args.enable_short and args.disable_short:
        raise SystemExit("--enable-short and --disable-short are mutually exclusive")
    if args.require_breakout and args.no_require_breakout:
        raise SystemExit("--require-breakout and --no-require-breakout are mutually exclusive")

    env_path = Path(args.env)
    if env_path.exists():
        raw = env_path.read_text(encoding="utf-8")
    else:
        raw = ""
    _, lines = parse_env(raw)

    changed = False

    if args.tf:
        preset = TF_PRESETS[args.tf]
        for k, v in {
            "PATTERN_PIVOT_LEN": str(preset.pattern_pivot_len),
            "PATTERN_TOL_PCT": str(preset.pattern_tol_pct),
            "W_MIN_BOUNCE_PCT": str(preset.w_min_bounce_pct),
            "HS_MIN_SHOULDER_DROP_PCT": str(preset.hs_min_shoulder_drop_pct),
        }.items():
            lines = set_env(lines, k, v)
        changed = True

    if args.enable_long:
        lines = set_env(lines, "ENABLE_LONG", "true")
        changed = True
    if args.disable_long:
        lines = set_env(lines, "ENABLE_LONG", "false")
        changed = True
    if args.enable_short:
        lines = set_env(lines, "ENABLE_SHORT", "true")
        changed = True
    if args.disable_short:
        lines = set_env(lines, "ENABLE_SHORT", "false")
        changed = True

    if args.no_patterns:
        lines = set_env(lines, "PATTERN_LONG", "none")
        lines = set_env(lines, "PATTERN_SHORT", "none")
        changed = True
    else:
        if args.w:
            lines = set_env(lines, "PATTERN_LONG", "w_bottom")
            changed = True
        if args.hs:
            lines = set_env(lines, "PATTERN_SHORT", "hs_top")
            changed = True

    if args.require_breakout:
        lines = set_env(lines, "W_REQUIRE_BREAKOUT", "true")
        lines = set_env(lines, "HS_REQUIRE_BREAKDOWN", "true")
        changed = True
    if args.no_require_breakout:
        lines = set_env(lines, "W_REQUIRE_BREAKOUT", "false")
        lines = set_env(lines, "HS_REQUIRE_BREAKDOWN", "false")
        changed = True

    if not changed:
        print("No changes requested.")
        return 0

    env_path.write_text("".join(lines), encoding="utf-8")
    print(f"Updated {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

