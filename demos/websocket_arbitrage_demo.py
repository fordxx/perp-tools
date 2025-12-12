"""WebSocket-powered Real-time Arbitrage Scanner Demo.

This demo showcases the complete arbitrage scanning pipeline using
real-time WebSocket market data:

1. Connect to multiple exchanges via WebSocket
2. Receive real-time bid/ask updates
3. Scan for cross-exchange arbitrage opportunities
4. Display profitable spreads with execution details

Key Features:
- Real-time data (< 100ms latency)
- Multi-exchange support (OKX, Hyperliquid)
- Automatic spread detection
- Risk-adjusted profit calculation
"""
import asyncio
import logging
import sys
import time
from datetime import datetime
from typing import List

# Add project root to path
sys.path.insert(0, "/home/fordxx/perp-tools")

from src.perpbot.scanner.websocket_quote_engine import WebSocketQuoteEngine
from src.perpbot.scanner.scanner_config import ScannerConfig
from src.perpbot.scanner.pair_scanner import PairScanner, SpreadResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# Suppress verbose logs
logging.getLogger("websockets").setLevel(logging.WARNING)


def print_header():
    """Print demo header."""
    print("\n" + "=" * 100)
    print(" WebSocket Real-Time Arbitrage Scanner Demo".center(100))
    print("=" * 100)
    print()
    print("This demo connects to live WebSocket feeds and scans for arbitrage opportunities")
    print("across multiple exchanges in real-time.")
    print()


def print_arbitrage_opportunity(spread: SpreadResult):
    """Print arbitrage opportunity in a nice format."""
    print("\n" + "🎯 " + "=" * 95)
    print(f"  ARBITRAGE OPPORTUNITY DETECTED")
    print("=" * 100)
    print()
    print(f"  Symbol:          {spread.symbol}")
    print(f"  Exchange A:      {spread.exchange_a.upper():15s} | Bid: ${spread.bid_a:>10.2f} | Ask: ${spread.ask_a:>10.2f}")
    print(f"  Exchange B:      {spread.exchange_b.upper():15s} | Bid: ${spread.bid_b:>10.2f} | Ask: ${spread.ask_b:>10.2f}")
    print()
    print(f"  📊 Spread:        {spread.spread_bps:>8.2f} bps ({spread.spread_pct:>6.3f}%)")
    print(f"  💰 Net Profit:    {spread.net_profit_bps:>8.2f} bps ({spread.net_profit_pct:>6.3f}%)")
    print(f"  📈 Gross Profit:  {spread.gross_profit_bps:>8.2f} bps")
    print(f"  💸 Total Fees:    {spread.total_fee_bps:>8.2f} bps")
    print()
    print(f"  ⚡ Strategy:      {spread.direction.upper()}")
    print(f"  🎲 Score:         {spread.arb_score:>8.2f}")
    print(f"  ⏱️  Timestamp:     {spread.timestamp.strftime('%H:%M:%S.%f')[:-3]}")
    print()

    # Execution details
    if spread.direction == "a_to_b":
        print(f"  📋 Execution Plan:")
        print(f"     1. BUY  on {spread.exchange_a.upper()} @ ${spread.ask_a:.2f}")
        print(f"     2. SELL on {spread.exchange_b.upper()} @ ${spread.bid_b:.2f}")
    else:
        print(f"  📋 Execution Plan:")
        print(f"     1. BUY  on {spread.exchange_b.upper()} @ ${spread.ask_b:.2f}")
        print(f"     2. SELL on {spread.exchange_a.upper()} @ ${spread.bid_a:.2f}")

    print()
    print("=" * 100)


class ArbitrageScanner:
    """Real-time arbitrage scanner using WebSocket quotes."""

    def __init__(self, config: ScannerConfig):
        self.config = config
        self.quote_engine = WebSocketQuoteEngine()
        self.pair_scanner = PairScanner(config)

        self.opportunities_found = 0
        self.scans_completed = 0
        self.start_time = time.time()

    def start(self, exchanges: List[str], symbols: List[str]):
        """Start the quote engine and WebSocket feeds."""
        logger.info(f"🚀 Starting WebSocket Quote Engine...")
        logger.info(f"   Exchanges: {exchanges}")
        logger.info(f"   Symbols: {symbols}")

        self.quote_engine.start(exchanges, symbols)

        # Wait for initial quotes
        logger.info("⏳ Waiting for initial quotes...")
        time.sleep(3)

        # Check health
        if not self.quote_engine.is_healthy():
            logger.error("❌ Quote engine is not healthy")
            return False

        logger.info("✅ Quote engine ready")
        return True

    def stop(self):
        """Stop the quote engine."""
        logger.info("🛑 Stopping scanner...")
        self.quote_engine.stop()

    def scan_once(self, symbols: List[str]) -> List[SpreadResult]:
        """Scan for arbitrage opportunities across all symbols."""
        results: List[SpreadResult] = []

        for symbol in symbols:
            # Get quotes from all exchanges
            quotes = self.quote_engine.get_all_quotes(symbol)

            if len(quotes) < 2:
                continue

            # Scan all exchange pairs
            exchange_list = list(quotes.keys())

            for i, exchange_a in enumerate(exchange_list):
                for exchange_b in exchange_list[i + 1:]:
                    bid_a, ask_a = quotes[exchange_a]
                    bid_b, ask_b = quotes[exchange_b]

                    # Scan this pair
                    spread = self.pair_scanner.scan(
                        symbol=symbol,
                        bbo_a=(bid_a, ask_a),
                        bbo_b=(bid_b, ask_b),
                        latency_a=0.0,
                        latency_b=0.0,
                        quality_a=1.0,
                        quality_b=1.0,
                        exchange_a=exchange_a,
                        exchange_b=exchange_b,
                    )

                    if spread:
                        results.append(spread)

        self.scans_completed += 1
        return results

    def print_statistics(self):
        """Print scanner statistics."""
        runtime = time.time() - self.start_time

        print("\n" + "=" * 100)
        print(" Scanner Statistics".center(100))
        print("=" * 100)
        print()
        print(f"  Runtime:              {runtime:.1f} seconds")
        print(f"  Scans completed:      {self.scans_completed}")
        print(f"  Opportunities found:  {self.opportunities_found}")
        print(f"  Scan rate:            {self.scans_completed / runtime:.2f} scans/sec")
        print()

        # Quote engine statistics
        stats = self.quote_engine.get_statistics()

        print("  Quote Statistics:")
        for key, data in sorted(stats.items()):
            print(f"    {key:25s}: {data['updates']:>5d} updates | "
                  f"avg latency: {data['avg_latency_ms']:>6.2f}ms | "
                  f"age: {data['quote_age_s']:>5.2f}s")

        print()

        # Connection status
        status = self.quote_engine.get_connection_status()

        print("  Connection Status:")
        for exchange, info in sorted(status.items()):
            print(f"    {exchange:15s}: connected={info['connected']}, "
                  f"symbols={info['subscribed_symbols']}, "
                  f"heartbeat_age={info['heartbeat_age']:.1f}s")

        print()
        print("=" * 100)
        print()


def main():
    """Main demo function."""
    print_header()

    # Configuration
    config = ScannerConfig(
        min_spread_bps=5.0,  # Minimum 5 bps spread
        fee_bps=2.5,  # 2.5 bps fee per side (total 5 bps)
    )

    # Exchanges and symbols to monitor
    exchanges = ["okx", "hyperliquid"]
    symbols = ["BTC/USDT", "ETH/USDT"]

    # Create scanner
    scanner = ArbitrageScanner(config)

    try:
        # Start scanner
        if not scanner.start(exchanges, symbols):
            logger.error("❌ Failed to start scanner")
            return

        print("\n" + "-" * 100)
        print(" Live Arbitrage Scanning".center(100))
        print("-" * 100)
        print()
        print("Monitoring for arbitrage opportunities... (Ctrl+C to stop)")
        print()

        # Scan loop
        scan_interval = 1.0  # Scan every 1 second
        last_scan = time.time()

        while True:
            now = time.time()

            # Time to scan?
            if now - last_scan >= scan_interval:
                # Scan for opportunities
                opportunities = scanner.scan_once(symbols)

                # Display opportunities
                for spread in opportunities:
                    scanner.opportunities_found += 1
                    print_arbitrage_opportunity(spread)

                last_scan = now

            # Sleep briefly to avoid busy loop
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")

    finally:
        # Stop scanner
        scanner.stop()

        # Print statistics
        scanner.print_statistics()

        print("👋 Demo completed!")
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception(f"❌ Fatal error: {e}")
        sys.exit(1)
