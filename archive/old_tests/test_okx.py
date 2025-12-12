#!/usr/bin/env python3
"""OKX 市场数据验证脚本"""
from __future__ import annotations

import argparse
import logging
import os
from typing import Dict

from okx.v5 import Market

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")
logger = logging.getLogger("okx-test")


def build_market_client() -> Market:
    api_key = os.getenv("OKX_API_KEY", "")
    secret_key = os.getenv("OKX_API_SECRET", "")
    passphrase = os.getenv("OKX_PASSPHRASE", "")
    return Market(api_key, secret_key, passphrase, False)


def main() -> None:
    parser = argparse.ArgumentParser(description="OKX 行情接口健康检查")
    parser.add_argument("--inst", default="BTC-USDT", help="合约或交易对，例如 BTC-USDT")
    args = parser.parse_args()

    client = build_market_client()
    ticker: Dict = client.get_ticker(instId=args.inst)
    logger.info("Ticker %s: %s", args.inst, ticker)

    depth: Dict = client.get_orderbook(instId=args.inst, sz=5)
    bids = depth.get("bids", [])[:1]
    asks = depth.get("asks", [])[:1]
    logger.info("Best bid=%s ask=%s", bids[0] if bids else "N/A", asks[0] if asks else "N/A")


if __name__ == "__main__":
    main()
