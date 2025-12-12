"""OKX WebSocket market data feed implementation.

OKX WebSocket API Documentation:
https://www.okx.com/docs-v5/en/#websocket-api-public-channel-tickers-channel

Public WebSocket Endpoint:
- Mainnet: wss://ws.okx.com:8443/ws/v5/public
- AWS: wss://wsaws.okx.com:8443/ws/v5/public
"""
from __future__ import annotations

import logging
from typing import List, Optional

from perpbot.exchanges.websocket_manager import MarketDataUpdate, WebSocketMarketDataFeed

logger = logging.getLogger(__name__)


class OKXWebSocketFeed(WebSocketMarketDataFeed):
    """OKX WebSocket market data feed.

    Subscribes to the 'tickers' channel which provides:
    - Best bid/ask prices
    - 24h volume
    - Price change percentage
    - Timestamp

    Message format:
    {
        "arg": {
            "channel": "tickers",
            "instId": "BTC-USDT-SWAP"
        },
        "data": [{
            "instId": "BTC-USDT-SWAP",
            "last": "43250.5",
            "bidPx": "43250.0",
            "askPx": "43251.0",
            "bidSz": "1.5",
            "askSz": "2.3",
            "ts": "1638360000000"
        }]
    }
    """

    # OKX WebSocket URLs
    MAINNET_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"
    AWS_WS_URL = "wss://wsaws.okx.com:8443/ws/v5/public"

    def __init__(self, use_testnet: bool = False, use_aws: bool = False):
        """Initialize OKX WebSocket feed.

        Args:
            use_testnet: If True, use demo trading (Note: OKX doesn't have a separate testnet WS)
            use_aws: If True, use AWS endpoint for better latency in some regions
        """
        ws_url = self.AWS_WS_URL if use_aws else self.MAINNET_WS_URL

        super().__init__(exchange_name="okx", ws_url=ws_url)

        self.use_testnet = use_testnet

        logger.info(f"✅ OKX WebSocket feed initialized (url={ws_url}, testnet={use_testnet})")

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC-USDT-SWAP (OKX format).

        Args:
            symbol: Standard format like "BTC/USDT"

        Returns:
            OKX format like "BTC-USDT-SWAP"
        """
        if "-SWAP" in symbol:
            return symbol

        # BTC/USDT -> BTC-USDT-SWAP
        symbol = symbol.replace("/", "-").upper()
        return f"{symbol}-SWAP"

    def _denormalize_symbol(self, okx_symbol: str) -> str:
        """Convert BTC-USDT-SWAP back to BTC/USDT.

        Args:
            okx_symbol: OKX format like "BTC-USDT-SWAP"

        Returns:
            Standard format like "BTC/USDT"
        """
        # BTC-USDT-SWAP -> BTC/USDT
        symbol = okx_symbol.replace("-SWAP", "").replace("-", "/")
        return symbol

    async def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to tickers channel for given symbols.

        Args:
            symbols: List of symbols in standard format (e.g., ["BTC/USDT", "ETH/USDT"])
        """
        if not self._ws:
            logger.warning("⚠️ OKX WebSocket not connected, cannot subscribe")
            return

        # Convert symbols to OKX format
        okx_symbols = [self._normalize_symbol(symbol) for symbol in symbols]

        # Build subscription message
        subscribe_message = {
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": inst_id} for inst_id in okx_symbols],
        }

        # Send subscription
        await self._ws.send(self._json_dumps(subscribe_message))

        logger.info(f"📡 OKX subscribed to tickers: {okx_symbols}")

    async def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from tickers channel for given symbols.

        Args:
            symbols: List of symbols in standard format
        """
        if not self._ws:
            logger.warning("⚠️ OKX WebSocket not connected, cannot unsubscribe")
            return

        # Convert symbols to OKX format
        okx_symbols = [self._normalize_symbol(symbol) for symbol in symbols]

        # Build unsubscription message
        unsubscribe_message = {
            "op": "unsubscribe",
            "args": [{"channel": "tickers", "instId": inst_id} for inst_id in okx_symbols],
        }

        # Send unsubscription
        await self._ws.send(self._json_dumps(unsubscribe_message))

        logger.info(f"📡 OKX unsubscribed from tickers: {okx_symbols}")

    def parse_message(self, message: dict) -> Optional[MarketDataUpdate]:
        """Parse OKX WebSocket message into normalized market data.

        Args:
            message: Raw WebSocket message from OKX

        Returns:
            MarketDataUpdate if valid ticker data, None otherwise
        """
        try:
            # Check if this is a ticker update
            arg = message.get("arg", {})
            channel = arg.get("channel")

            if channel != "tickers":
                # Not a ticker message (might be subscription confirmation, ping, etc.)
                return None

            # Extract data
            data_list = message.get("data", [])

            if not data_list:
                return None

            # OKX sends an array, but for tickers it's usually just one item
            ticker_data = data_list[0]

            # Extract fields
            inst_id = ticker_data.get("instId", "")
            bid_px = ticker_data.get("bidPx")
            ask_px = ticker_data.get("askPx")
            bid_sz = ticker_data.get("bidSz", "0")
            ask_sz = ticker_data.get("askSz", "0")
            timestamp_ms = ticker_data.get("ts")

            # Validate required fields
            if not bid_px or not ask_px:
                logger.debug(f"⚠️ OKX ticker missing bid/ask: {ticker_data}")
                return None

            # Convert to standard symbol format
            symbol = self._denormalize_symbol(inst_id)

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
                f"📊 OKX {symbol}: bid={update.bid:.2f} ask={update.ask:.2f} "
                f"spread={update.spread_bps:.2f}bps"
            )

            return update

        except Exception as e:
            logger.error(f"❌ OKX message parse error: {e} - Message: {message}")
            return None

    @staticmethod
    def _json_dumps(obj: dict) -> str:
        """Convert dict to JSON string."""
        import json

        return json.dumps(obj)


# Example usage
async def example_usage():
    """Example of using OKX WebSocket feed."""
    from perpbot.exchanges.websocket_manager import WebSocketMarketDataManager

    # Create manager
    manager = WebSocketMarketDataManager()

    # Create OKX feed
    okx_feed = OKXWebSocketFeed(use_aws=False)

    # Register feed with manager
    manager.register_feed(okx_feed)

    # Subscribe to symbols
    await manager.subscribe("okx", ["BTC/USDT", "ETH/USDT"])

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
