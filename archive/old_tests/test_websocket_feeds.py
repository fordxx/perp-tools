"""Test script for WebSocket market data feeds.

This script tests real-time WebSocket connections to:
- OKX (CEX)
- Hyperliquid (DEX)
- Paradex (DEX) - if SDK available

It subscribes to BTC and ETH perpetual contracts and displays:
- Real-time bid/ask prices
- Spread in basis points
- Network latency
- Update frequency
"""
import asyncio
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# Suppress verbose WebSocket logs
logging.getLogger("websockets").setLevel(logging.WARNING)


def print_header():
    """Print test header."""
    print("\n" + "=" * 80)
    print(" WebSocket Market Data Feed Test".center(80))
    print("=" * 80)
    print()


class MarketDataMonitor:
    """Monitor and display market data updates."""

    def __init__(self):
        self.update_counts: Dict[str, int] = defaultdict(int)
        self.last_update_time: Dict[str, float] = {}
        self.start_time = time.time()
        self.total_updates = 0

    def on_update(self, update):
        """Handle market data update."""
        from src.perpbot.exchanges.websocket_manager import MarketDataUpdate

        if not isinstance(update, MarketDataUpdate):
            return

        # Track update counts
        key = f"{update.exchange}:{update.symbol}"
        self.update_counts[key] += 1
        self.total_updates += 1

        # Calculate update frequency
        now = time.time()
        last_time = self.last_update_time.get(key, now)
        update_interval = now - last_time
        self.last_update_time[key] = now

        # Display update
        print(
            f"[{update.timestamp.strftime('%H:%M:%S')}] "
            f"{update.exchange.upper():12s} {update.symbol:10s} | "
            f"Bid: {update.bid:>10.2f} | Ask: {update.ask:>10.2f} | "
            f"Spread: {update.spread_bps:>6.2f}bps | "
            f"Latency: {update.latency_ms:>5.1f}ms | "
            f"Interval: {update_interval:>4.1f}s | "
            f"Count: {self.update_counts[key]:>3d}"
        )

    def print_summary(self):
        """Print summary statistics."""
        runtime = time.time() - self.start_time

        print("\n" + "=" * 80)
        print(" Summary".center(80))
        print("=" * 80)
        print(f"Runtime: {runtime:.1f} seconds")
        print(f"Total updates: {self.total_updates}")
        print(f"Average rate: {self.total_updates / runtime:.2f} updates/sec")
        print()
        print("Updates per feed:")

        for key, count in sorted(self.update_counts.items()):
            print(f"  {key:30s}: {count:>4d} updates ({count / runtime:>5.2f}/sec)")

        print("=" * 80)
        print()


async def test_okx_feed(manager, symbols):
    """Test OKX WebSocket feed."""
    try:
        from src.perpbot.exchanges.okx_websocket import OKXWebSocketFeed

        logger.info("🚀 Testing OKX WebSocket feed...")

        okx_feed = OKXWebSocketFeed(use_aws=False)
        manager.register_feed(okx_feed)
        await manager.subscribe("okx", symbols)

        logger.info("✅ OKX feed configured")
        return True

    except Exception as e:
        logger.error(f"❌ OKX feed failed: {e}")
        return False


async def test_hyperliquid_feed(manager, symbols):
    """Test Hyperliquid WebSocket feed."""
    try:
        from src.perpbot.exchanges.hyperliquid_websocket import HyperliquidWebSocketFeed

        logger.info("🚀 Testing Hyperliquid WebSocket feed...")

        hl_feed = HyperliquidWebSocketFeed(use_testnet=True)
        manager.register_feed(hl_feed)

        # Hyperliquid uses USDC as quote, convert symbols
        hl_symbols = [s.replace("/USDT", "/USDC") for s in symbols]
        await manager.subscribe("hyperliquid", hl_symbols)

        logger.info("✅ Hyperliquid feed configured")
        return True

    except Exception as e:
        logger.error(f"❌ Hyperliquid feed failed: {e}")
        return False


async def test_paradex_feed(manager, symbols):
    """Test Paradex WebSocket feed (if available)."""
    try:
        # Check if Paradex SDK is available
        import paradex_py

        logger.info("🚀 Testing Paradex WebSocket feed...")
        logger.info("ℹ️  Paradex WebSocket requires authentication (skipping for now)")

        # TODO: Implement Paradex WebSocket feed when credentials available
        return False

    except ImportError:
        logger.info("ℹ️  Paradex SDK not installed (skipping)")
        return False
    except Exception as e:
        logger.error(f"❌ Paradex feed failed: {e}")
        return False


async def main():
    """Main test function."""
    print_header()

    # Import WebSocket manager
    try:
        from src.perpbot.exchanges.websocket_manager import WebSocketMarketDataManager
    except ImportError:
        logger.error("❌ Failed to import WebSocketMarketDataManager")
        logger.error("Make sure you're running from the project root directory")
        sys.exit(1)

    # Create manager and monitor
    manager = WebSocketMarketDataManager()
    monitor = MarketDataMonitor()

    # Register monitor callback
    manager.add_update_callback(monitor.on_update)

    # Test symbols
    symbols = ["BTC/USDT", "ETH/USDT"]

    logger.info(f"📊 Testing symbols: {symbols}")
    print()

    # Configure feeds
    feeds_configured = []

    if await test_okx_feed(manager, symbols):
        feeds_configured.append("OKX")

    if await test_hyperliquid_feed(manager, symbols):
        feeds_configured.append("Hyperliquid")

    if await test_paradex_feed(manager, symbols):
        feeds_configured.append("Paradex")

    if not feeds_configured:
        logger.error("❌ No feeds configured successfully")
        sys.exit(1)

    logger.info(f"✅ Configured feeds: {', '.join(feeds_configured)}")
    print()

    # Start all feeds
    logger.info("🚀 Starting WebSocket feeds...")
    await manager.start_all()

    print("\n" + "-" * 80)
    print(" Live Market Data".center(80))
    print("-" * 80)
    print()

    try:
        # Run for specified duration
        duration = 30  # seconds
        logger.info(f"⏱️  Running for {duration} seconds... (Ctrl+C to stop early)")
        print()

        await asyncio.sleep(duration)

    except KeyboardInterrupt:
        logger.info("\n⏹️  Interrupted by user")

    finally:
        # Stop all feeds
        logger.info("🛑 Stopping WebSocket feeds...")
        await manager.stop_all()

        # Print summary
        monitor.print_summary()

        # Print connection status
        status = manager.get_status()
        print("Connection Status:")
        for exchange, info in status.items():
            print(f"  {exchange:15s}: connected={info['connected']}, "
                  f"symbols={info['subscribed_symbols']}, "
                  f"quotes={info['latest_quotes']}, "
                  f"heartbeat_age={info['heartbeat_age']:.1f}s")
        print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
        sys.exit(1)
