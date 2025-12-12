#!/usr/bin/env python3
"""Binance 公共行情快速验活脚本"""
from __future__ import annotations

import argparse
import logging
import os
from typing import Dict

from binance.client import Client

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-5s | %(message)s")
logger = logging.getLogger("binance-test")


def build_client() -> Client:
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if api_key and api_secret:
        logger.info("使用配置的 Binance API Key")
    return Client(api_key or None, api_secret or None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance 行情健康检查")
    parser.add_argument("--symbol", default="BTCUSDT", help="交易对 (默认 BTCUSDT)")
    parser.add_argument("--depth", type=int, default=5, help="订单簿深度")
    args = parser.parse_args()

    client = build_client()
    ticker: Dict = client.get_symbol_ticker(symbol=args.symbol)
    logger.info("Ticker %s: %s", args.symbol, ticker)

    order_book: Dict = client.get_order_book(symbol=args.symbol, limit=args.depth)
    best_bid = order_book["bids"][0] if order_book["bids"] else ["N/A", "0"]
    best_ask = order_book["asks"][0] if order_book["asks"] else ["N/A", "0"]
    logger.info("Best bid=%s size=%s | Best ask=%s size=%s", best_bid[0], best_bid[1], best_ask[0], best_ask[1])


if __name__ == "__main__":
    main()
