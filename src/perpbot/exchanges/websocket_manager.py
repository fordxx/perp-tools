"""Unified WebSocket market data manager for real-time price feeds.

This module provides a centralized WebSocket connection manager that:
- Subscribes to real-time orderbook/ticker updates from multiple exchanges
- Normalizes market data into a unified format
- Provides async callbacks for price updates
- Handles reconnection and error recovery
- Tracks connection latency and data freshness
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set

import websockets

from perpbot.models import PriceQuote

logger = logging.getLogger(__name__)


@dataclass
class MarketDataUpdate:
    """Normalized market data update from WebSocket."""

    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    latency_ms: float = 0.0  # Network + processing latency

    @property
    def mid(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        """Calculate spread in price units."""
        return self.ask - self.bid

    @property
    def spread_bps(self) -> float:
        """Calculate spread in basis points."""
        if self.mid == 0:
            return 0.0
        return (self.spread / self.mid) * 10000

    def to_price_quote(self) -> PriceQuote:
        """Convert to PriceQuote format."""
        return PriceQuote(
            exchange=self.exchange,
            symbol=self.symbol,
            bid=self.bid,
            ask=self.ask,
            venue_type="dex",  # Most exchanges are DEX
        )


class WebSocketMarketDataFeed(ABC):
    """Abstract base class for exchange-specific WebSocket feeds."""

    def __init__(self, exchange_name: str, ws_url: str):
        self.exchange_name = exchange_name
        self.ws_url = ws_url
        self.subscribed_symbols: Set[str] = set()
        self.callbacks: List[Callable[[MarketDataUpdate], None]] = []

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._last_heartbeat = time.time()

    @abstractmethod
    async def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to market data for given symbols."""
        pass

    @abstractmethod
    async def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from market data for given symbols."""
        pass

    @abstractmethod
    def parse_message(self, message: dict) -> Optional[MarketDataUpdate]:
        """Parse exchange-specific WebSocket message into normalized format."""
        pass

    def add_callback(self, callback: Callable[[MarketDataUpdate], None]) -> None:
        """Register a callback for market data updates."""
        if callback not in self.callbacks:
            self.callbacks.append(callback)

    def remove_callback(self, callback: Callable[[MarketDataUpdate], None]) -> None:
        """Remove a registered callback."""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

    async def connect(self) -> None:
        """Connect to WebSocket and start message loop."""
        self._running = True

        while self._running:
            try:
                logger.info(f"🔌 Connecting to {self.exchange_name} WebSocket: {self.ws_url}")

                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10,
                ) as ws:
                    self._ws = ws
                    self._last_heartbeat = time.time()

                    logger.info(f"✅ {self.exchange_name} WebSocket connected")

                    # Subscribe to symbols
                    if self.subscribed_symbols:
                        await self.subscribe(list(self.subscribed_symbols))

                    # Message processing loop
                    async for message in ws:
                        await self._process_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ {self.exchange_name} WebSocket disconnected: {e}")
                if self._running:
                    await asyncio.sleep(5)  # Wait before reconnecting

            except Exception as e:
                logger.error(f"❌ {self.exchange_name} WebSocket error: {e}")
                if self._running:
                    await asyncio.sleep(5)

    async def _process_message(self, raw_message: str) -> None:
        """Process incoming WebSocket message."""
        try:
            receive_time = time.time()
            message = json.loads(raw_message)

            # Parse into normalized format
            update = self.parse_message(message)

            if update:
                # Calculate latency
                process_time = time.time()
                update.latency_ms = (process_time - receive_time) * 1000

                # Dispatch to callbacks
                for callback in self.callbacks:
                    try:
                        callback(update)
                    except Exception as e:
                        logger.error(f"❌ Callback error for {self.exchange_name}: {e}")

                self._last_heartbeat = time.time()

        except json.JSONDecodeError:
            logger.debug(f"Non-JSON message from {self.exchange_name}: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"❌ Message processing error for {self.exchange_name}: {e}")

    async def disconnect(self) -> None:
        """Disconnect from WebSocket."""
        self._running = False

        if self._ws:
            await self._ws.close()
            self._ws = None

        logger.info(f"🔌 {self.exchange_name} WebSocket disconnected")

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._ws is not None and not self._ws.closed

    @property
    def heartbeat_age(self) -> float:
        """Seconds since last message received."""
        return time.time() - self._last_heartbeat


class WebSocketMarketDataManager:
    """Central manager for all exchange WebSocket connections."""

    def __init__(self):
        self.feeds: Dict[str, WebSocketMarketDataFeed] = {}
        self.latest_quotes: Dict[str, MarketDataUpdate] = {}  # Key: "exchange:symbol"
        self.update_callbacks: List[Callable[[MarketDataUpdate], None]] = []

        self._tasks: List[asyncio.Task] = []

    def register_feed(self, feed: WebSocketMarketDataFeed) -> None:
        """Register a new exchange feed."""
        self.feeds[feed.exchange_name] = feed

        # Add manager's callback to feed
        feed.add_callback(self._on_market_data_update)

        logger.info(f"✅ Registered {feed.exchange_name} market data feed")

    def _on_market_data_update(self, update: MarketDataUpdate) -> None:
        """Internal callback for market data updates."""
        # Store latest quote
        key = f"{update.exchange}:{update.symbol}"
        self.latest_quotes[key] = update

        # Dispatch to registered callbacks
        for callback in self.update_callbacks:
            try:
                callback(update)
            except Exception as e:
                logger.error(f"❌ Manager callback error: {e}")

    def add_update_callback(self, callback: Callable[[MarketDataUpdate], None]) -> None:
        """Register a callback for all market data updates."""
        if callback not in self.update_callbacks:
            self.update_callbacks.append(callback)

    async def subscribe(self, exchange: str, symbols: List[str]) -> None:
        """Subscribe to market data for specific symbols on an exchange."""
        feed = self.feeds.get(exchange)

        if not feed:
            logger.error(f"❌ Exchange {exchange} not registered")
            return

        feed.subscribed_symbols.update(symbols)

        if feed.is_connected:
            await feed.subscribe(symbols)

        logger.info(f"📡 Subscribed to {exchange} {symbols}")

    async def start_all(self) -> None:
        """Start all registered WebSocket feeds."""
        for exchange, feed in self.feeds.items():
            task = asyncio.create_task(feed.connect())
            self._tasks.append(task)
            logger.info(f"🚀 Started {exchange} WebSocket feed")

    async def stop_all(self) -> None:
        """Stop all WebSocket feeds."""
        # Disconnect all feeds
        for feed in self.feeds.values():
            await feed.disconnect()

        # Cancel all tasks
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)

        self._tasks.clear()
        logger.info("⏹️ All WebSocket feeds stopped")

    def get_latest_quote(self, exchange: str, symbol: str) -> Optional[MarketDataUpdate]:
        """Get the latest market data update for a symbol."""
        key = f"{exchange}:{symbol}"
        return self.latest_quotes.get(key)

    def get_all_quotes(self) -> Dict[str, MarketDataUpdate]:
        """Get all latest quotes."""
        return self.latest_quotes.copy()

    def get_status(self) -> Dict[str, dict]:
        """Get connection status for all feeds."""
        status = {}

        for exchange, feed in self.feeds.items():
            status[exchange] = {
                "connected": feed.is_connected,
                "subscribed_symbols": len(feed.subscribed_symbols),
                "heartbeat_age": feed.heartbeat_age,
                "latest_quotes": sum(
                    1 for key in self.latest_quotes.keys() if key.startswith(f"{exchange}:")
                ),
            }

        return status
