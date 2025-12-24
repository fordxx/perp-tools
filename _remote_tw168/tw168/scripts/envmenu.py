#!/usr/bin/env python3
from __future__ import annotations

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


def parse_env(text: str) -> list[str]:
    return text.splitlines(True)


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


def ask_choice(title: str, options: list[str]) -> int:
    while True:
        print(title)
        for i, opt in enumerate(options, start=1):
            print(f"{i}) {opt}")
        raw = input("请输入数字选择: ").strip()
        if raw.isdigit():
            n = int(raw)
            if 1 <= n <= len(options):
                return n
        print("无效选择，请重试。\n")


def main() -> int:
    env_path = Path(".env")
    lines = parse_env(env_path.read_text(encoding="utf-8")) if env_path.exists() else []

    tf_n = ask_choice("选择周期预设:", ["5m", "15m", "30m"])
    tf = ["5m", "15m", "30m"][tf_n - 1]
    preset = TF_PRESETS[tf]

    pat_n = ask_choice("选择图形过滤:", ["不开", "只开 W底(做多)", "只开 头肩顶(做空)", "W底+头肩顶(全开)"])
    dir_n = ask_choice("选择交易方向:", ["多空都做", "只做多", "只做空"])
    strict_n = ask_choice("是否要求突破/跌破颈线(更严格、信号更少):", ["否", "是"])

    # Apply preset
    lines = set_env(lines, "PATTERN_PIVOT_LEN", str(preset.pattern_pivot_len))
    lines = set_env(lines, "PATTERN_TOL_PCT", str(preset.pattern_tol_pct))
    lines = set_env(lines, "W_MIN_BOUNCE_PCT", str(preset.w_min_bounce_pct))
    lines = set_env(lines, "HS_MIN_SHOULDER_DROP_PCT", str(preset.hs_min_shoulder_drop_pct))

    # Patterns
    if pat_n == 1:
        lines = set_env(lines, "PATTERN_LONG", "none")
        lines = set_env(lines, "PATTERN_SHORT", "none")
    elif pat_n == 2:
        lines = set_env(lines, "PATTERN_LONG", "w_bottom")
        lines = set_env(lines, "PATTERN_SHORT", "none")
    elif pat_n == 3:
        lines = set_env(lines, "PATTERN_LONG", "none")
        lines = set_env(lines, "PATTERN_SHORT", "hs_top")
    else:
        lines = set_env(lines, "PATTERN_LONG", "w_bottom")
        lines = set_env(lines, "PATTERN_SHORT", "hs_top")

    # Direction toggles
    if dir_n == 1:
        lines = set_env(lines, "ENABLE_LONG", "true")
        lines = set_env(lines, "ENABLE_SHORT", "true")
    elif dir_n == 2:
        lines = set_env(lines, "ENABLE_LONG", "true")
        lines = set_env(lines, "ENABLE_SHORT", "false")
    else:
        lines = set_env(lines, "ENABLE_LONG", "false")
        lines = set_env(lines, "ENABLE_SHORT", "true")

    # Strict neckline requirement
    if strict_n == 2:
        lines = set_env(lines, "W_REQUIRE_BREAKOUT", "true")
        lines = set_env(lines, "HS_REQUIRE_BREAKDOWN", "true")
    else:
        lines = set_env(lines, "W_REQUIRE_BREAKOUT", "false")
        lines = set_env(lines, "HS_REQUIRE_BREAKDOWN", "false")

    env_path.write_text("".join(lines), encoding="utf-8")
    print(f"\n已更新 {env_path}（周期={tf}）")
    print("改完记得重启 uvicorn 才生效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

