"""Hyperliquid WebSocket market data feed implementation.

Hyperliquid WebSocket API Documentation:
https://hyperliquid.gitbook.io/hyperliquid-docs/api/websocket

Public WebSocket Endpoint:
- Mainnet: wss://api.hyperliquid.xyz/ws
- Testnet: wss://testnet.api.hyperliquid.xyz/ws
"""
from __future__ import annotations

import logging
from typing import List, Optional

from perpbot.exchanges.websocket_manager import MarketDataUpdate, WebSocketMarketDataFeed

logger = logging.getLogger(__name__)


class HyperliquidWebSocketFeed(WebSocketMarketDataFeed):
    """Hyperliquid WebSocket market data feed.

    Subscribes to the 'l2Book' channel which provides:
    - Top-of-book bid/ask prices
    - Order book depth
    - Real-time updates

    Message format:
    {
        "channel": "l2Book",
        "data": {
            "coin": "BTC",
            "levels": [
                [{"px": "43250.0", "sz": "1.5", "n": 1}],  // Bids
                [{"px": "43251.0", "sz": "2.3", "n": 1}]   // Asks
            ],
            "time": 1638360000000
        }
    }
    """

    # Hyperliquid WebSocket URLs
    MAINNET_WS_URL = "wss://api.hyperliquid.xyz/ws"
    TESTNET_WS_URL = "wss://testnet.api.hyperliquid.xyz/ws"

    def __init__(self, use_testnet: bool = True):
        """Initialize Hyperliquid WebSocket feed.

        Args:
            use_testnet: If True, use testnet endpoint
        """
        ws_url = self.TESTNET_WS_URL if use_testnet else self.MAINNET_WS_URL

        super().__init__(exchange_name="hyperliquid", ws_url=ws_url)

        self.use_testnet = use_testnet

        logger.info(f"✅ Hyperliquid WebSocket feed initialized (url={ws_url}, testnet={use_testnet})")

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC (Hyperliquid format).

        Hyperliquid uses simple coin names like "BTC", "ETH".

        Args:
            symbol: Standard format like "BTC/USDT" or "BTC/USD"

        Returns:
            Hyperliquid format like "BTC"
        """
        # Remove /USDT, /USD, /USDC suffixes
        if "/" in symbol:
            return symbol.split("/")[0].upper()

        return symbol.upper()

    def _denormalize_symbol(self, hl_symbol: str) -> str:
        """Convert BTC back to BTC/USDT.

        Args:
            hl_symbol: Hyperliquid format like "BTC"

        Returns:
            Standard format like "BTC/USDT"
        """
        # Hyperliquid uses USDC as quote currency
        return f"{hl_symbol}/USDC"

    async def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to l2Book channel for given symbols.

        Args:
            symbols: List of symbols in standard format (e.g., ["BTC/USDT", "ETH/USDT"])
        """
        if not self._ws:
            logger.warning("⚠️ Hyperliquid WebSocket not connected, cannot subscribe")
            return

        # Convert symbols to Hyperliquid format
        hl_symbols = [self._normalize_symbol(symbol) for symbol in symbols]

        # Build subscription message
        # Hyperliquid subscription format:
        # {"method": "subscribe", "subscription": {"type": "l2Book", "coin": "BTC"}}
        for coin in hl_symbols:
            subscribe_message = {
                "method": "subscribe",
                "subscription": {"type": "l2Book", "coin": coin},
            }

            await self._ws.send(self._json_dumps(subscribe_message))

        logger.info(f"📡 Hyperliquid subscribed to l2Book: {hl_symbols}")

    async def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from l2Book channel for given symbols.

        Args:
            symbols: List of symbols in standard format
        """
        if not self._ws:
            logger.warning("⚠️ Hyperliquid WebSocket not connected, cannot unsubscribe")
            return

        # Convert symbols to Hyperliquid format
        hl_symbols = [self._normalize_symbol(symbol) for symbol in symbols]

        # Build unsubscription message
        for coin in hl_symbols:
            unsubscribe_message = {
                "method": "unsubscribe",
                "subscription": {"type": "l2Book", "coin": coin},
            }

            await self._ws.send(self._json_dumps(unsubscribe_message))

        logger.info(f"📡 Hyperliquid unsubscribed from l2Book: {hl_symbols}")

    def parse_message(self, message: dict) -> Optional[MarketDataUpdate]:
        """Parse Hyperliquid WebSocket message into normalized market data.

        Args:
            message: Raw WebSocket message from Hyperliquid

        Returns:
            MarketDataUpdate if valid l2Book data, None otherwise
        """
        try:
            # Check if this is an l2Book update
            channel = message.get("channel")

            if channel != "l2Book":
                # Not an l2Book message (might be subscription confirmation, etc.)
                return None

            # Extract data
            data = message.get("data", {})

            if not data:
                return None

            # Extract fields
            coin = data.get("coin", "")
            levels = data.get("levels", [])
            timestamp_ms = data.get("time")

            # Validate levels structure
            if not levels or len(levels) < 2:
                logger.debug(f"⚠️ Hyperliquid l2Book missing levels: {data}")
                return None

            bids = levels[0]  # List of bid levels
            asks = levels[1]  # List of ask levels

            if not bids or not asks:
                logger.debug(f"⚠️ Hyperliquid l2Book empty bids/asks: {data}")
                return None

            # Get best bid/ask (top of book)
            best_bid = bids[0]
            best_ask = asks[0]

            bid_px = best_bid.get("px")
            ask_px = best_ask.get("px")
            bid_sz = best_bid.get("sz", "0")
            ask_sz = best_ask.get("sz", "0")

            # Validate required fields
            if not bid_px or not ask_px:
                logger.debug(f"⚠️ Hyperliquid l2Book missing bid/ask: {data}")
                return None

            # Convert to standard symbol format
            symbol = self._denormalize_symbol(coin)

            # Parse timestamp
            import datetime

            if timestamp_ms:
                timestamp = datetime.datetime.utcfromtimestamp(int(timestamp_ms) / 1000)
            else:
                timestamp = datetime.datetime.utcnow()

            # Create normalized update
            update = MarketDataUpdate(
                exchange=self.exchange_name,
                symbol=symbol,
                bid=float(bid_px),
                ask=float(ask_px),
                bid_size=float(bid_sz),
                ask_size=float(ask_sz),
                timestamp=timestamp,
            )

            logger.debug(
                f"📊 Hyperliquid {symbol}: bid={update.bid:.2f} ask={update.ask:.2f} "
                f"spread={update.spread_bps:.2f}bps"
            )

            return update

        except Exception as e:
            logger.error(f"❌ Hyperliquid message parse error: {e} - Message: {message}")
            return None

    @staticmethod
    def _json_dumps(obj: dict) -> str:
        """Convert dict to JSON string."""
        import json

        return json.dumps(obj)


# Example usage
async def example_usage():
    """Example of using Hyperliquid WebSocket feed."""
    from perpbot.exchanges.websocket_manager import WebSocketMarketDataManager

    # Create manager
    manager = WebSocketMarketDataManager()

    # Create Hyperliquid feed
    hl_feed = HyperliquidWebSocketFeed(use_testnet=True)

    # Register feed with manager
    manager.register_feed(hl_feed)

    # Subscribe to symbols
    await manager.subscribe("hyperliquid", ["BTC/USDC", "ETH/USDC"])

    # Add callback for updates
    def on_update(update: MarketDataUpdate):
        print(
            f"[{update.exchange}] {update.symbol}: "
            f"bid={update.bid:.2f} ask={update.ask:.2f} "
            f"spread={update.spread_bps:.2f}bps latency={update.latency_ms:.1f}ms"
        )

    manager.add_update_callback(on_update)

    # Start all feeds
    await manager.start_all()

    # Run for 30 seconds
    import asyncio

    await asyncio.sleep(30)

    # Stop all feeds
    await manager.stop_all()


if __name__ == "__main__":
    import asyncio

    asyncio.run(example_usage())
