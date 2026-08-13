#!/usr/bin/env python3
"""算财报突破的双向挂单价位。

用法:
    python3 levels.py                  # AMAT, 盘尾30分钟, 0.8%缓冲
    python3 levels.py TSLA             # 换标的
    python3 levels.py AMAT 60 1.0      # 盘尾60分钟, 1.0%缓冲
"""
import json
import sys
import urllib.request

API = "https://api.bitget.com/api/v2/mix/market/candles"


def klines(symbol, bars):
    url = f"{API}?symbol={symbol}&productType=USDT-FUTURES&granularity=5m&limit={bars}"
    with urllib.request.urlopen(url, timeout=10) as r:
        body = json.load(r)
    if body.get("code") != "00000":
        sys.exit(f"接口报错: {body.get('msg')}")
    if not body.get("data"):
        sys.exit(f"{symbol} 没有 K 线数据，确认合约存在且已上线")
    return body["data"]


def main():
    asset = (sys.argv[1] if len(sys.argv) > 1 else "AMAT").upper()
    minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    buf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8

    symbol = asset if asset.endswith("USDT") else asset + "USDT"
    rows = klines(symbol, max(1, minutes // 5))

    high = max(float(k[2]) for k in rows)
    low = min(float(k[3]) for k in rows)
    last = float(rows[-1][4])
    mid = (high + low) / 2

    buy = high * (1 + buf / 100)
    sell = low * (1 - buf / 100)

    print(f"\n{symbol}  最后{minutes}分钟  现价 {last:.2f}")
    print(f"区间  {low:.2f} — {high:.2f}   (幅度 {(high - low) / mid * 100:.2f}%)")
    print(f"缓冲  {buf}%\n")
    print(f"  多单触发  {buy:.2f}    止损 {mid:.2f}   ({(buy - mid) / buy * 100:.2f}% 风险)")
    print(f"  空单触发  {sell:.2f}    止损 {mid:.2f}   ({(mid - sell) / sell * 100:.2f}% 风险)")
    print(f"\n  止损都放区间中轴 {mid:.2f}")
    print("  一单成交后立刻手动删掉另一单\n")


if __name__ == "__main__":
    main()
