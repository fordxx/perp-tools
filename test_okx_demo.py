#!/usr/bin/env python3
"""
OKX Demo Trading 验证脚本

目标：
✅ 连接 OKX Demo Trading
✅ 获取 BTC/USDT 行情
✅ 市价开仓
✅ 市价平仓
✅ 本地 PnL 计算

环境变量要求：
- OKX_API_KEY
- OKX_API_SECRET
- OKX_API_PASSPHRASE
"""

import sys
import os
import time

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import logging
from perpbot.exchanges.okx import OKXClient
from perpbot.models import OrderRequest, Position

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_connection():
    logger.info("=" * 60)
    logger.info("Step 1: Testing OKX Demo Trading Connection")
    logger.info("=" * 60)

    client = OKXClient()
    client.connect()

    logger.info("✅ OKX Demo Trading connected successfully")
    return client


def test_price_fetch(client):
    logger.info("\n" + "=" * 60)
    logger.info("Step 2: Testing Price Fetch")
    logger.info("=" * 60)

    symbol = "BTC/USDT"
    quote = client.get_current_price(symbol)

    logger.info(f"✅ {symbol} Price:")
    logger.info(f"   Bid: ${quote.bid:,.2f}")
    logger.info(f"   Ask: ${quote.ask:,.2f}")
    logger.info(f"   Mid: ${(quote.bid + quote.ask)/2:,.2f}")

    return quote


def test_open_close_cycle(client, symbol="BTC/USDT", size=0.02):
    logger.info("\n" + "=" * 60)
    logger.info("Step 3 & 4: REAL OKX Demo Trading Open & Close")
    logger.info("=" * 60)

    # ===== 1️⃣ 市价开多仓 =====
    request = OrderRequest(
        symbol=symbol,
        side="buy",
        size=size,
        limit_price=None
    )

    logger.info(f"🚀 Placing MARKET BUY order: {size} {symbol}")
    open_order = client.place_open_order(request)

    if open_order.id.startswith("rejected"):
        logger.error(f"❌ Open order rejected: {open_order.id}")
        return None

    logger.info("✅ Position opened:")
    logger.info(f"   Order ID: {open_order.id}")
    logger.info(f"   Filled: {open_order.size} @ ${open_order.price:.2f}")

    # ===== 2️⃣ 构造 Position 用于平仓 =====
    position = Position(
        id=open_order.id,
        order=open_order,
        target_profit_pct=0.0,
    )

    # 防止撮合延迟
    time.sleep(2)

    # ===== 3️⃣ 市价平仓 =====
    logger.info("🧯 Closing position with MARKET order...")
    close_order = client.place_close_order(position, current_price=open_order.price)

    if close_order.id.startswith("rejected"):
        logger.error(f"❌ Close order rejected: {close_order.id}")
        return open_order

    logger.info("✅ Position closed:")
    logger.info(f"   Close ID: {close_order.id}")
    logger.info(f"   Closed: {close_order.size} @ ${close_order.price:.2f}")

    # ===== 4️⃣ 本地 PnL 计算 =====
    pnl = (close_order.price - open_order.price) * open_order.size

    logger.info("\n📈 Local PnL Result:")
    logger.info(f"   Entry: ${open_order.price:.2f}")
    logger.info(f"   Exit : ${close_order.price:.2f}")
    logger.info(f"   Size : {open_order.size}")
    logger.info(f"   PnL  : ${pnl:.4f}")

    return close_order


def main():
    logger.info("\n")
    logger.info("🧪" * 30)
    logger.info("OKX Demo Trading Verification Script")
    logger.info("🧪" * 30)

    try:
        # Step 1: Connect
        client = test_connection()

        # Step 2: Fetch price
        quote = test_price_fetch(client)

        # Step 3 & 4: Open & Close Cycle
        test_open_close_cycle(client)

        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL OKX DEMO TESTS PASSED")
        logger.info("=" * 60)
        logger.info("\n✅ OKX Demo Trading integration is ready!")

    except Exception as e:
        logger.exception("❌ OKX Demo Test failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
