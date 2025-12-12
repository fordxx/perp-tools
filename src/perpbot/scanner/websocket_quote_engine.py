"""WebSocket-powered Quote Engine for Scanner V3.

This Quote Engine uses real-time WebSocket market data feeds instead of
REST API polling, providing:
- Lower latency (< 100ms vs 200-500ms for REST)
- Higher update frequency (real-time vs 1-5s polling)
- Better accuracy (instant updates vs stale snapshots)
- Lower API rate limit usage
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from perpbot.exchanges.websocket_manager import MarketDataUpdate, WebSocketMarketDataManager

logger = logging.getLogger(__name__)


class WebSocketQuoteEngine:
    """Real-time quote engine powered by WebSocket market data feeds.

    Thread-safe design:
    - WebSocket feeds run in a background asyncio event loop
    - Quote data is stored in thread-safe data structures
    - Main thread can query latest quotes without blocking
    """

    def __init__(self):
        self.ws_manager = WebSocketMarketDataManager()

        # Latest quotes: {(exchange, symbol): (bid, ask, timestamp)}
        self.quotes: Dict[Tuple[str, str], Tuple[float, float, float]] = {}

        # Quote statistics: {(exchange, symbol): {"count": int, "latency_avg": float}}
        self.stats: Dict[Tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "latency_sum": 0.0, "latency_avg": 0.0}
        )

        # Background event loop
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Register callback
        self.ws_manager.add_update_callback(self._on_market_data_update)

    def _on_market_data_update(self, update: MarketDataUpdate) -> None:
        """Callback for market data updates (thread-safe)."""
        try:
            key = (update.exchange, update.symbol)

            # Update quote
            self.quotes[key] = (update.bid, update.ask, time.time())

            # Update statistics
            stats = self.stats[key]
            stats["count"] += 1
            stats["latency_sum"] += update.latency_ms
            stats["latency_avg"] = stats["latency_sum"] / stats["count"]

        except Exception as e:
            logger.error(f"Error processing market data update: {e}")

    def start(self, exchanges: List[str], symbols: List[str]) -> None:
        """Start WebSocket feeds in background thread.

        Args:
            exchanges: List of exchange names (e.g., ["okx", "hyperliquid"])
            symbols: List of symbols (e.g., ["BTC/USDT", "ETH/USDT"])
        """
        if self._running:
            logger.warning("Quote engine already running")
            return

        self._running = True

        # Start background thread
        self._thread = threading.Thread(
            target=self._run_event_loop,
            args=(exchanges, symbols),
            daemon=True,
            name="WebSocketQuoteEngine"
        )
        self._thread.start()

        # Wait for feeds to connect
        time.sleep(2)

        logger.info(f"✅ WebSocket Quote Engine started for {len(exchanges)} exchanges, {len(symbols)} symbols")

    def _run_event_loop(self, exchanges: List[str], symbols: List[str]) -> None:
        """Run asyncio event loop in background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            self._loop.run_until_complete(self._start_feeds(exchanges, symbols))
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Event loop error: {e}")
        finally:
            self._loop.close()

    async def _start_feeds(self, exchanges: List[str], symbols: List[str]) -> None:
        """Initialize and start WebSocket feeds."""
        # Register feeds
        if "okx" in exchanges:
            from perpbot.exchanges.okx_websocket import OKXWebSocketFeed
            okx_feed = OKXWebSocketFeed()
            self.ws_manager.register_feed(okx_feed)
            await self.ws_manager.subscribe("okx", symbols)

        if "hyperliquid" in exchanges:
            from perpbot.exchanges.hyperliquid_websocket import HyperliquidWebSocketFeed
            # Hyperliquid uses USDC, convert symbols
            hl_symbols = [s.replace("/USDT", "/USDC") for s in symbols]
            hl_feed = HyperliquidWebSocketFeed(use_testnet=True)
            self.ws_manager.register_feed(hl_feed)
            await self.ws_manager.subscribe("hyperliquid", hl_symbols)

        # Start all feeds
        await self.ws_manager.start_all()

    def stop(self) -> None:
        """Stop WebSocket feeds and background thread."""
        if not self._running:
            return

        self._running = False

        # Stop event loop
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                self.ws_manager.stop_all(),
                self._loop
            )
            self._loop.call_soon_threadsafe(self._loop.stop)

        # Wait for thread to finish
        if self._thread:
            self._thread.join(timeout=5)

        logger.info("⏹️ WebSocket Quote Engine stopped")

    def get_bbo(self, symbol: str, exchange: Optional[str] = None) -> Optional[Tuple[float, float]]:
        """Get best bid/offer for a symbol.

        Args:
            symbol: Symbol (e.g., "BTC/USDT")
            exchange: Optional exchange filter

        Returns:
            Tuple of (bid, ask) or None if not available
        """
        if exchange:
            # Get quote from specific exchange
            key = (exchange, symbol)
            if key in self.quotes:
                bid, ask, _ = self.quotes[key]
                return (bid, ask)
            return None

        # Get best quote across all exchanges
        best_bid = 0.0
        best_ask = float('inf')

        for (exch, sym), (bid, ask, _) in self.quotes.items():
            if sym == symbol:
                best_bid = max(best_bid, bid)
                best_ask = min(best_ask, ask)

        if best_bid > 0 and best_ask < float('inf'):
            return (best_bid, best_ask)

        return None

    def get_quote(self, exchange: str, symbol: str) -> Optional[Tuple[float, float, float]]:
        """Get quote for specific exchange and symbol.

        Args:
            exchange: Exchange name
            symbol: Symbol

        Returns:
            Tuple of (bid, ask, age_seconds) or None
        """
        key = (exchange, symbol)
        if key not in self.quotes:
            return None

        bid, ask, timestamp = self.quotes[key]
        age = time.time() - timestamp

        return (bid, ask, age)

    def get_all_quotes(self, symbol: str) -> Dict[str, Tuple[float, float]]:
        """Get quotes from all exchanges for a symbol.

        Args:
            symbol: Symbol

        Returns:
            Dict of {exchange: (bid, ask)}
        """
        result = {}

        for (exchange, sym), (bid, ask, _) in self.quotes.items():
            if sym == symbol:
                result[exchange] = (bid, ask)

        return result

    def get_statistics(self) -> Dict[str, dict]:
        """Get quote engine statistics.

        Returns:
            Dict of statistics per exchange-symbol pair
        """
        stats = {}

        for (exchange, symbol), data in self.stats.items():
            key = f"{exchange}:{symbol}"

            # Get quote age
            quote_key = (exchange, symbol)
            age = 0.0
            if quote_key in self.quotes:
                _, _, timestamp = self.quotes[quote_key]
                age = time.time() - timestamp

            stats[key] = {
                "updates": data["count"],
                "avg_latency_ms": data["latency_avg"],
                "quote_age_s": age,
            }

        return stats

    def get_connection_status(self) -> Dict[str, dict]:
        """Get WebSocket connection status.

        Returns:
            Dict of connection status per exchange
        """
        return self.ws_manager.get_status()

    def is_healthy(self) -> bool:
        """Check if quote engine is healthy.

        Returns:
            True if all feeds are connected and quotes are fresh
        """
        status = self.get_connection_status()

        for exchange, info in status.items():
            # Check if connected
            if not info["connected"]:
                logger.warning(f"❌ {exchange} not connected")
                return False

            # Check if heartbeat is recent (< 30s)
            if info["heartbeat_age"] > 30:
                logger.warning(f"❌ {exchange} heartbeat stale ({info['heartbeat_age']:.1f}s)")
                return False

        return True
