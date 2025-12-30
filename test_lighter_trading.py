#!/usr/bin/env python3
"""Test Lighter DEX trading functionality.

This script tests the complete Lighter trading workflow:
1. Connect to Lighter
2. Place a market order
3. Place a limit order
4. Place stop-loss order
5. Place take-profit order
6. Close position

Usage:
    # Test on mainnet (requires real credentials)
    python test_lighter_trading.py

    # Test on testnet
    LIGHTER_ENV=testnet python test_lighter_trading.py

Environment Variables:
    LIGHTER_API_KEY_PRIVATE_KEY: Your Lighter API key private key (0x...)
    LIGHTER_ACCOUNT_INDEX: Your account index (decimal)
    LIGHTER_API_KEY_INDEX: Your API key index (decimal, usually 0)
    LIGHTER_ENV: mainnet or testnet (default: mainnet)
"""
import logging
import sys
from decimal import Decimal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from perpbot.exchanges.lighter import LighterClient
    from perpbot.models import OrderRequest, Position, Order
except ImportError as e:
    logger.error("Failed to import perpbot modules: %s", e)
    logger.error("Make sure you're in the perp-tools directory")
    sys.exit(1)


def test_connection():
    """Test 1: Connect to Lighter"""
    logger.info("=" * 60)
    logger.info("TEST 1: Connecting to Lighter")
    logger.info("=" * 60)

    client = LighterClient()
    client.connect()

    logger.info("✅ Connected successfully")
    logger.info("   Trading enabled: %s", client._trading_enabled)
    logger.info("   Markets loaded: %d", len(client._markets))

    return client


def test_get_price(client: LighterClient, symbol: str = "ETH/USDT"):
    """Test 2: Get current price"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Getting current price for %s", symbol)
    logger.info("=" * 60)

    quote = client.get_current_price(symbol)

    logger.info("✅ Price fetched")
    logger.info("   Bid: %.2f", quote.bid)
    logger.info("   Ask: %.2f", quote.ask)
    logger.info("   Spread: %.2f", quote.ask - quote.bid)

    return quote


def test_get_orderbook(client: LighterClient, symbol: str = "ETH/USDT"):
    """Test 3: Get orderbook"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Getting orderbook for %s", symbol)
    logger.info("=" * 60)

    orderbook = client.get_orderbook(symbol, depth=5)

    logger.info("✅ Orderbook fetched")
    logger.info("   Top 5 bids:")
    for i, (price, size) in enumerate(orderbook.bids[:5], 1):
        logger.info("     %d. %.2f @ %.4f", i, price, size)

    logger.info("   Top 5 asks:")
    for i, (price, size) in enumerate(orderbook.asks[:5], 1):
        logger.info("     %d. %.2f @ %.4f", i, price, size)

    return orderbook


def test_market_order(client: LighterClient, symbol: str = "ETH/USDT", size: float = 0.01):
    """Test 4: Place a market order (WARNING: Real trading!)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Placing MARKET order")
    logger.info("=" * 60)
    logger.warning("⚠️  This will place a REAL market order!")
    logger.warning("⚠️  Symbol: %s, Size: %.4f", symbol, size)

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        logger.info("❌ Market order test skipped")
        return None

    request = OrderRequest(
        symbol=symbol,
        side="buy",
        size=size,
        limit_price=None,  # Market order
    )

    order = client.place_open_order(request)

    if order.id.startswith("error") or order.id == "rejected":
        logger.error("❌ Market order failed: %s", order.id)
        return None

    logger.info("✅ Market order placed")
    logger.info("   Order ID: %s", order.id)
    logger.info("   Symbol: %s", order.symbol)
    logger.info("   Side: %s", order.side)
    logger.info("   Size: %.4f", order.size)
    logger.info("   Price: %.2f", order.price)

    return order


def test_limit_order(client: LighterClient, symbol: str = "ETH/USDT", size: float = 0.01, price: float = 3000.0):
    """Test 5: Place a limit order (WARNING: Real trading!)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Placing LIMIT order")
    logger.info("=" * 60)
    logger.warning("⚠️  This will place a REAL limit order!")
    logger.warning("⚠️  Symbol: %s, Size: %.4f, Price: %.2f", symbol, size, price)

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        logger.info("❌ Limit order test skipped")
        return None

    request = OrderRequest(
        symbol=symbol,
        side="buy",
        size=size,
        limit_price=price,
    )

    order = client.place_open_order(request)

    if order.id.startswith("error") or order.id == "rejected":
        logger.error("❌ Limit order failed: %s", order.id)
        return None

    logger.info("✅ Limit order placed")
    logger.info("   Order ID: %s", order.id)
    logger.info("   Symbol: %s", order.symbol)
    logger.info("   Side: %s", order.side)
    logger.info("   Size: %.4f", order.size)
    logger.info("   Limit Price: %.2f", order.price)

    return order


def test_stop_loss(client: LighterClient, symbol: str = "ETH/USDT", size: float = 0.01, trigger: float = 2900.0):
    """Test 6: Place a stop-loss order (WARNING: Real trading!)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 6: Placing STOP-LOSS order")
    logger.info("=" * 60)
    logger.warning("⚠️  This will place a REAL stop-loss order!")
    logger.warning("⚠️  Symbol: %s, Size: %.4f, Trigger: %.2f", symbol, size, trigger)

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        logger.info("❌ Stop-loss test skipped")
        return None

    order = client.place_stop_loss(
        symbol=symbol,
        side="sell",  # Close a long position
        size=size,
        trigger_price=trigger,
        limit_price=None,  # Market order after trigger
    )

    if order.id.startswith("error") or order.id == "rejected":
        logger.error("❌ Stop-loss failed: %s", order.id)
        return None

    logger.info("✅ Stop-loss placed")
    logger.info("   Order ID: %s", order.id)
    logger.info("   Symbol: %s", order.symbol)
    logger.info("   Side: %s", order.side)
    logger.info("   Size: %.4f", order.size)
    logger.info("   Trigger Price: %.2f", order.price)

    return order


def test_take_profit(client: LighterClient, symbol: str = "ETH/USDT", size: float = 0.01, trigger: float = 3200.0):
    """Test 7: Place a take-profit order (WARNING: Real trading!)"""
    logger.info("\n" + "=" * 60)
    logger.info("TEST 7: Placing TAKE-PROFIT order")
    logger.info("=" * 60)
    logger.warning("⚠️  This will place a REAL take-profit order!")
    logger.warning("⚠️  Symbol: %s, Size: %.4f, Trigger: %.2f", symbol, size, trigger)

    response = input("Continue? (yes/no): ")
    if response.lower() != "yes":
        logger.info("❌ Take-profit test skipped")
        return None

    order = client.place_take_profit(
        symbol=symbol,
        side="sell",  # Close a long position
        size=size,
        trigger_price=trigger,
        limit_price=None,  # Market order after trigger
    )

    if order.id.startswith("error") or order.id == "rejected":
        logger.error("❌ Take-profit failed: %s", order.id)
        return None

    logger.info("✅ Take-profit placed")
    logger.info("   Order ID: %s", order.id)
    logger.info("   Symbol: %s", order.symbol)
    logger.info("   Side: %s", order.side)
    logger.info("   Size: %.4f", order.size)
    logger.info("   Trigger Price: %.2f", order.price)

    return order


def main():
    """Run all tests"""
    logger.info("🚀 Starting Lighter DEX Trading Tests")
    logger.info("=" * 60)

    try:
        # Test 1: Connection
        client = test_connection()

        # Test 2: Get price
        symbol = "ETH/USDT"
        quote = test_get_price(client, symbol)

        # Test 3: Get orderbook
        orderbook = test_get_orderbook(client, symbol)

        # Test 4-7: Trading tests (skipped by default, require user confirmation)
        logger.info("\n" + "=" * 60)
        logger.info("TRADING TESTS (require confirmation)")
        logger.info("=" * 60)

        # Uncomment to enable trading tests
        # test_market_order(client, symbol, size=0.01)
        # test_limit_order(client, symbol, size=0.01, price=quote.bid * 0.95)
        # test_stop_loss(client, symbol, size=0.01, trigger=quote.bid * 0.99)
        # test_take_profit(client, symbol, size=0.01, trigger=quote.ask * 1.01)

        logger.info("\n" + "=" * 60)
        logger.info("✅ All tests completed successfully!")
        logger.info("=" * 60)

        # Cleanup
        client.disconnect()

    except Exception as e:
        logger.exception("❌ Test failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
