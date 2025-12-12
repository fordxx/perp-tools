#!/usr/bin/env python3
"""Bybit 行情验证脚本"""
from __future__ import annotations

import argparse
import logging

from pybit import HTTP

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")
logger = logging.getLogger("bybit-test")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bybit 简易行情检查")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对")
    parser.add_argument("--interval", default="1", help="K线间隔，例如 1")
    args = parser.parse_args()

    client = HTTP(endpoint="https://api.bybit.com")
    time_info = client.server_time()
    logger.info("Server time: %s", time_info)

    kline = client.kline(symbol=args.symbol, interval=args.interval, limit=5)
    logger.info("Kline (%s): %s", args.symbol, kline.get("result"))


if __name__ == "__main__":
    main()
