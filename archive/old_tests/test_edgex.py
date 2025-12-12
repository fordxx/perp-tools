#!/usr/bin/env python3
"""EdgeX smoke test"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, "src")

from perpbot.exchanges.edgex import EdgeXClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")
logger = logging.getLogger("edgex-test")


def main() -> None:
    parser = argparse.ArgumentParser(description="EdgeX 行情/订单簿检测")
    parser.add_argument("--symbol", default="BTC/USDT", help="交易对")
    parser.add_argument("--depth", type=int, default=5, help="订单簿深度")
    parser.add_argument("--testnet", action="store_true", help="启用测试网")
    args = parser.parse_args()

    client = EdgeXClient(use_testnet=args.testnet)
    client.connect()

    quote = client.get_current_price(args.symbol)
    logger.info("Price %s bid=%s ask=%s", args.symbol, quote.bid, quote.ask)

    depth = client.get_orderbook(args.symbol, depth=args.depth)
    if depth.bids:
        logger.info("Best bid %s", depth.bids[0])
    if depth.asks:
        logger.info("Best ask %s", depth.asks[0])


if __name__ == "__main__":
    main()
