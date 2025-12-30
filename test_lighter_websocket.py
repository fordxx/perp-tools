#!/usr/bin/env python3
"""Test Lighter WebSocket integration.

This script tests the WebSocket functionality integrated into LighterClient:
1. Connect to Lighter REST API
2. Enable WebSocket streaming
3. Subscribe to orderbook updates
4. Subscribe to trade executions
5. Subscribe to account updates (if trading enabled)

Usage:
    # Test WebSocket functionality
    python test_lighter_websocket.py

Environment Variables:
    LIGHTER_API_KEY_PRIVATE_KEY: Your Lighter API key private key (0x...)
    LIGHTER_ACCOUNT_INDEX: Your account index (decimal)
    LIGHTER_API_KEY_INDEX: Your API key index (decimal, usually 0)
    LIGHTER_ENV: mainnet or testnet (default: mainnet)
"""
import asyncio
import logging
import sys
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from perpbot.exchanges.lighter import LighterClient
except ImportError as e:
    logger.error("Failed to import perpbot modules: %s", e)
    logger.error("Make sure you're in the perp-tools directory")
    sys.exit(1)


# Track updates
orderbook_updates = []
trade_updates = []
position_updates = []
order_updates = []


def on_orderbook_update(data: dict) -> None:
    """Handle orderbook update."""
    try:
        orderbook_updates.append(data)
        channel = data.get("channel", "")
        msg_type = data.get("type", "")

        # Extract orderbook data
        asks = data.get("asks", [])
        bids = data.get("bids", [])

        logger.info("📖 Orderbook update [%s]: %d asks, %d bids",
                   channel, len(asks), len(bids))

        if bids and asks:
            best_bid = bids[0] if bids else None
            best_ask = asks[0] if asks else None
            if best_bid and best_ask:
                logger.info("   Best bid: %.2f | Best ask: %.2f | Spread: %.2f",
                           float(best_bid.get("price", 0)),
                           float(best_ask.get("price", 0)),
                           float(best_ask.get("price", 0)) - float(best_bid.get("price", 0)))
    except Exception as e:
        logger.error("Error handling orderbook update: %s", e)


def on_trade_update(data: dict) -> None:
    """Handle trade execution."""
    try:
        trade_updates.append(data)

        # Extract trade data
        trade = data.get("trade", {})
        price = trade.get("price", 0)
        size = trade.get("size", 0)
        side = trade.get("side", "")

        logger.info("💹 Trade executed: %s %.4f @ %.2f",
                   side.upper(), float(size), float(price))
    except Exception as e:
        logger.error("Error handling trade update: %s", e)


def on_position_update(data: dict) -> None:
    """Handle position update."""
    try:
        position_updates.append(data)
        logger.info("📊 Position update: %s", data.get("type", "unknown"))
    except Exception as e:
        logger.error("Error handling position update: %s", e)


def on_order_update(data: dict) -> None:
    """Handle order update."""
    try:
        order_updates.append(data)
        logger.info("📝 Order update: %s", data.get("type", "unknown"))
    except Exception as e:
        logger.error("Error handling order update: %s", e)


def test_websocket_integration():
    """Test WebSocket integration in LighterClient."""
    logger.info("=" * 60)
    logger.info("Testing Lighter WebSocket Integration")
    logger.info("=" * 60)

    # Step 1: Connect to Lighter
    logger.info("\n[1/5] Connecting to Lighter REST API...")
    client = LighterClient()
    client.connect()

    logger.info("✅ Connected successfully")
    logger.info("   Trading enabled: %s", client._trading_enabled)
    logger.info("   Markets loaded: %d", len(client._markets))

    # Step 2: Enable WebSocket
    logger.info("\n[2/5] Enabling WebSocket...")
    client.enable_websocket(auto_subscribe_account=True)

    logger.info("✅ WebSocket enabled")
    logger.info("   WS enabled: %s", client._ws_enabled)
    logger.info("   WS client: %s", "active" if client._ws_client else "none")

    # Step 3: Subscribe to orderbook
    symbol = "ETH/USDT"
    logger.info("\n[3/5] Subscribing to orderbook for %s...", symbol)
    client.subscribe_orderbook_stream(symbol, on_orderbook_update)

    # Step 4: Subscribe to trades
    logger.info("\n[4/5] Subscribing to trades for %s...", symbol)
    client.subscribe_trades_stream(symbol, on_trade_update)

    # Step 5: Setup position/order handlers if trading enabled
    if client._trading_enabled:
        logger.info("\n[5/5] Setting up account update handlers...")
        client.setup_position_update_handler(on_position_update)
        client.setup_order_update_handler(on_order_update)
    else:
        logger.info("\n[5/5] Skipping account handlers (trading not enabled)")

    # Wait and collect updates
    logger.info("\n" + "=" * 60)
    logger.info("Collecting WebSocket updates for 30 seconds...")
    logger.info("=" * 60)

    try:
        for i in range(30):
            time.sleep(1)
            if (i + 1) % 10 == 0:
                logger.info("⏱️  %d seconds elapsed...", i + 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrupted by user")

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("WebSocket Test Summary")
    logger.info("=" * 60)
    logger.info("Orderbook updates received: %d", len(orderbook_updates))
    logger.info("Trade updates received: %d", len(trade_updates))
    logger.info("Position updates received: %d", len(position_updates))
    logger.info("Order updates received: %d", len(order_updates))

    # Cleanup
    logger.info("\n" + "=" * 60)
    logger.info("Cleaning up...")
    logger.info("=" * 60)

    client.disable_websocket()
    client.disconnect()

    logger.info("✅ Test completed successfully!")

    # Validate results
    success = True
    if len(orderbook_updates) == 0:
        logger.warning("⚠️  No orderbook updates received (expected at least 1)")
        success = False

    logger.info("\n" + "=" * 60)
    if success:
        logger.info("✅ ALL TESTS PASSED")
    else:
        logger.warning("⚠️  SOME TESTS HAD ISSUES")
    logger.info("=" * 60)

    return success


def main():
    """Run WebSocket integration tests."""
    try:
        success = test_websocket_integration()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.exception("❌ Test failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
