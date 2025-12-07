#!/usr/bin/env python3
"""
OKX Demo Trading 验证脚本

用途：验证 OKX Demo Trading 完整交易闭环

验证流程：
1. 连接 OKX Demo Trading
2. 获取 BTC/USDT 价格
3. 检查现有持仓
4. (可选) 开仓测试
5. (可选) 平仓测试

环境变量要求：
- OKX_API_KEY
- OKX_API_SECRET
- OKX_PASSPHRASE
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import logging
from perpbot.exchanges.okx import OKXClient
from perpbot.models import OrderRequest

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_connection():
    """测试连接"""
    logger.info("=" * 60)
    logger.info("Step 1: Testing OKX Demo Trading Connection")
    logger.info("=" * 60)

    client = OKXClient(use_testnet=True)
    client.connect()

    logger.info("✅ Connection successful")
    return client


def test_price_fetch(client):
    """测试价格获取"""
    logger.info("\n" + "=" * 60)
    logger.info("Step 2: Testing Price Fetch")
    logger.info("=" * 60)

    symbol = "BTC/USDT"
    quote = client.get_current_price(symbol)

    logger.info(f"✅ {symbol} Price:")
    logger.info(f"   Bid: ${quote.bid:,.2f}")
    logger.info(f"   Ask: ${quote.ask:,.2f}")
    logger.info(f"   Mid: ${quote.mid:,.2f}")

    return quote


def test_positions(client):
    """测试持仓查询"""
    logger.info("\n" + "=" * 60)
    logger.info("Step 3: Testing Positions Query")
    logger.info("=" * 60)

    positions = client.get_account_positions()

    if not positions:
        logger.info("✅ No open positions")
    else:
        logger.info(f"✅ Found {len(positions)} open position(s):")
        for pos in positions:
            logger.info(f"   - {pos.order.symbol}: {pos.order.side} {pos.order.size} @ ${pos.order.price:.2f}")

    return positions


def test_order_placement(client, symbol="BTC/USDT", size=0.001):
    """测试下单（需要手动启用）"""
    logger.info("\n" + "=" * 60)
    logger.info("Step 4: Testing Order Placement (OPTIONAL - MANUAL ENABLE)")
    logger.info("=" * 60)

    logger.warning("⚠️ Order placement test is DISABLED by default")
    logger.warning("⚠️ To enable, uncomment the code in test_okx_demo.py")

    # UNCOMMENT THE FOLLOWING TO ENABLE REAL ORDER TESTING
    # WARNING: This will place a REAL order on OKX Demo Trading

    # request = OrderRequest(
    #     symbol=symbol,
    #     side="buy",
    #     size=size,
    #     limit_price=None  # MARKET order
    # )

    # logger.info(f"Placing MARKET {request.side} order: {size} {symbol}")
    # order = client.place_open_order(request)

    # if order.id.startswith("rejected"):
    #     logger.error(f"❌ Order rejected: {order.id}")
    # else:
    #     logger.info(f"✅ Order placed successfully:")
    #     logger.info(f"   Order ID: {order.id}")
    #     logger.info(f"   Filled: {order.size} @ ${order.price:.2f}")

    # return order

    return None


def main():
    """主测试流程"""
    logger.info("\n")
    logger.info("🧪" * 30)
    logger.info("OKX Demo Trading Verification Script")
    logger.info("🧪" * 30)

    try:
        # Step 1: Connect
        client = test_connection()

        # Step 2: Fetch price
        quote = test_price_fetch(client)

        # Step 3: Check positions
        positions = test_positions(client)

        # Step 4: (Optional) Place order
        test_order_placement(client)

        logger.info("\n" + "=" * 60)
        logger.info("✅ ALL TESTS PASSED")
        logger.info("=" * 60)
        logger.info("\n✅ OKX Demo Trading integration is ready!")
        logger.info("✅ You can now run: python run_bootstrap_hedge.py")

    except Exception as e:
        logger.exception("❌ Test failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
