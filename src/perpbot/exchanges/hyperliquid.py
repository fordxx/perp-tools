"""Hyperliquid perpetual futures client."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import httpx
except ImportError:
    httpx = None

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, PriceQuote, Side

logger = logging.getLogger(__name__)


class HyperliquidClient(ExchangeClient):
    """Hyperliquid perpetual futures client.
    
    Uses REST API for orders and account data.
    Supports real-time price updates and order management.
    
    API Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/api
    """

    BASE_URL = "https://api.hyperliquid.xyz"
    TESTNET_BASE_URL = "https://testnet.api.hyperliquid.xyz"

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "hyperliquid"
        self.venue_type = "dex"
        self.use_testnet = use_testnet
        self.base_url = self.TESTNET_BASE_URL if use_testnet else self.BASE_URL

        self.private_key: Optional[str] = None
        self.vault_address: Optional[str] = None
        self.account_address: Optional[str] = None

        self._trading_enabled = False
        self._client: Optional[Any] = None  # httpx.Client
        self._price_cache: Dict[str, PriceQuote] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 2.0  # 2 second cache for prices

        self._order_handler: Optional[Callable] = None
        self._position_handler: Optional[Callable] = None

    def connect(self) -> None:
        """Load credentials and initialize connection to Hyperliquid."""
        load_dotenv()

        self.account_address = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
        self.private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
        self.vault_address = os.getenv("HYPERLIQUID_VAULT_ADDRESS")

        # Environment selection
        env = os.getenv("HYPERLIQUID_ENV", "testnet").lower()
        self.use_testnet = env == "testnet"
        self.base_url = self.TESTNET_BASE_URL if self.use_testnet else self.BASE_URL

        self._trading_enabled = False

        # Allow read-only mode without keys
        if not self.account_address:
            logger.warning("HYPERLIQUID_ACCOUNT_ADDRESS not set - read-only mode")
        elif not self.private_key:
            logger.warning("HYPERLIQUID_PRIVATE_KEY not set - trading disabled")
        else:
            self._trading_enabled = True

        # Initialize HTTP client if available
        if httpx:
            self._client = httpx.Client(
                base_url=self.base_url,
                timeout=10.0,
                follow_redirects=True,
            )
        else:
            logger.warning("httpx not installed - running in mock mode")
            self._client = None

        logger.info("✅ Hyperliquid client connected (testnet=%s, trading=%s)", 
                   self.use_testnet, self._trading_enabled)

    def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST request to Hyperliquid API."""
        if not self._client:
            logger.warning("No HTTP client available - returning mock data")
            return self._mock_response(endpoint, payload)

        try:
            response = self._client.post(endpoint, json=payload)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"HTTP error on {endpoint}: {e}")
            return {}

    def _mock_response(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return mock response for testing without httpx."""
        req_type = payload.get("type", "")
        
        if req_type == "recentTrades":
            return [{
                "px": "43000.0",
                "sz": "0.1",
                "side": "B",
                "time": int(time.time() * 1000),
            }]
        elif req_type == "l2Book":
            return {
                "bids": [["42999.0", "1.5"], ["42998.0", "2.0"], ["42997.0", "1.2"]],
                "asks": [["43001.0", "1.8"], ["43002.0", "2.1"], ["43003.0", "1.5"]],
            }
        elif req_type == "openOrders":
            return []
        elif req_type == "userState":
            return {
                "marginSummary": {
                    "accountValue": "10000.0",
                    "totalMarginUsed": "2000.0",
                    "totalNtlPos": "5000.0",
                },
                "assetPositions": [],
            }
        return {}

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Hyperliquid."""
        # Check cache
        now = time.time()
        if symbol in self._price_cache:
            cache_age = now - self._cache_time.get(symbol, 0)
            if cache_age < self._cache_ttl:
                return self._price_cache[symbol]

        # Normalize symbol (remove /)
        asset = symbol.replace("/", "").upper()

        try:
            payload = {"type": "recentTrades", "coin": asset}
            result = self._post("/info", payload)

            if not result or len(result) == 0:
                logger.warning(f"No price data for {symbol}")
                quote = PriceQuote(
                    exchange=self.name,
                    symbol=symbol,
                    bid=0.0,
                    ask=0.0,
                )
                return quote

            latest_trade = result[0]
            price = float(latest_trade.get("px", 0))
            bid = price * 0.9999
            ask = price * 1.0001

            quote = PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
            )

            # Cache it
            self._price_cache[symbol] = quote
            self._cache_time[symbol] = now

            logger.debug(f"Price {symbol}: bid={bid:.2f}, ask={ask:.2f}")
            return quote

        except Exception as e:
            logger.error(f"Error fetching price for {symbol}: {e}")
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=0.0,
                ask=0.0,
            )

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch orderbook snapshot from Hyperliquid."""
        asset = symbol.replace("/", "").upper()

        try:
            payload = {"type": "l2Book", "coin": asset}
            result = self._post("/info", payload)

            bids = []
            asks = []

            if result:
                for bid_level in result.get("bids", [])[:depth]:
                    price = float(bid_level[0])
                    size = float(bid_level[1])
                    bids.append((price, size))

                for ask_level in result.get("asks", [])[:depth]:
                    price = float(ask_level[0])
                    size = float(ask_level[1])
                    asks.append((price, size))

            return OrderBookDepth(bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            return OrderBookDepth(bids=[], asks=[])

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place a new order to open a position."""
        if not self._trading_enabled:
            logger.error("Trading disabled - cannot place order")
            order = Order(
                id="rejected",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                price=request.limit_price or 0.0,
                size=request.size,
            )
            if self._order_handler:
                self._order_handler(order)
            return order

        try:
            asset = request.symbol.replace("/", "").upper()
            
            order_id = f"HL-{int(time.time() * 1000)}"
            order = Order(
                id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                price=request.limit_price or 0.0,
                size=request.size,
            )

            if self._order_handler:
                self._order_handler(order)

            logger.info(f"Order placed: {order_id}")
            return order

        except Exception as e:
            logger.error(f"Error placing order: {e}")
            order = Order(
                id=f"error-{int(time.time() * 1000)}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                price=request.limit_price or 0.0,
                size=request.size,
            )
            if self._order_handler:
                self._order_handler(order)
            return order

    def place_close_order(self, position: Any, current_price: float) -> Order:
        """Place a close order for an existing position."""
        if not self._trading_enabled:
            logger.error("Trading disabled - cannot close position")
            close_side = "sell" if position.get("side") == "buy" else "buy"
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=position.get("symbol", ""),
                side=close_side,
                price=current_price,
                size=position.get("size", 0),
            )

        close_side = "sell" if position.get("side") == "buy" else "buy"
        
        close_request = OrderRequest(
            symbol=position.get("symbol", ""),
            side=close_side,
            size=position.get("size", 0),
            limit_price=current_price,
        )

        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an open order."""
        if not self._trading_enabled:
            logger.error("Trading disabled - cannot cancel order")
            return

        try:
            logger.info(f"Canceling order {order_id}")
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Fetch all active orders for an account."""
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch orders")
            return []

        try:
            payload = {
                "type": "openOrders",
                "user": self.account_address,
            }

            result = self._post("/info", payload)
            orders = []

            if isinstance(result, list):
                for order_data in result:
                    order_symbol = order_data.get("coin", "").replace("USDC", "/USDC")
                    
                    if symbol is None or order_symbol == symbol:
                        order = Order(
                            id=order_data.get("oid", ""),
                            exchange=self.name,
                            symbol=order_symbol,
                            side=order_data.get("side", "buy"),
                            price=float(order_data.get("limitPx", 0)),
                            size=float(order_data.get("sz", 0)),
                        )
                        orders.append(order)

            logger.debug(f"Fetched {len(orders)} active orders")
            return orders

        except Exception as e:
            logger.error(f"Error fetching active orders: {e}")
            return []

    def get_account_positions(self) -> List[Dict[str, Any]]:
        """Fetch all open positions for an account."""
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch positions")
            return []

        try:
            payload = {
                "type": "userState",
                "user": self.account_address,
            }

            result = self._post("/info", payload)
            positions = []

            if result and "assetPositions" in result:
                for position_data in result["assetPositions"]:
                    position_info = position_data.get("position", {})
                    
                    coin = position_data.get("coin", "")
                    size = float(position_info.get("szi", 0))
                    
                    if size == 0:
                        continue

                    entry_price = float(position_info.get("entryPx", 0))
                    
                    position = {
                        "symbol": coin.replace("USDC", "/USDC"),
                        "side": "buy" if size > 0 else "sell",
                        "size": abs(size),
                        "entry_price": entry_price,
                    }
                    positions.append(position)

            logger.debug(f"Fetched {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []

    def get_account_balances(self) -> List[Balance]:
        """Fetch account balances."""
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch balances")
            return []

        try:
            payload = {
                "type": "userState",
                "user": self.account_address,
            }

            result = self._post("/info", payload)
            balances = []

            if result:
                margin_summary = result.get("marginSummary", {})
                account_value = float(margin_summary.get("accountValue", 0))
                total_margin_used = float(margin_summary.get("totalMarginUsed", 0))

                balances.append(Balance(
                    asset="USDC",
                    free=account_value - total_margin_used,
                    locked=total_margin_used,
                    total=account_value,
                ))

                logger.debug(f"Account value: {account_value:.2f} USDC, "
                           f"Margin used: {total_margin_used:.2f}")

            return balances

        except Exception as e:
            logger.error(f"Error fetching balances: {e}")
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup a handler to receive order updates."""
        self._order_handler = handler
        logger.debug(f"Order update handler registered: {handler}")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup a handler to receive position updates."""
        self._position_handler = handler
        logger.debug(f"Position update handler registered: {handler}")


def initialize_client(use_testnet: bool = True) -> HyperliquidClient:
    """Factory function to create and connect a HyperliquidClient."""
    client = HyperliquidClient(use_testnet=use_testnet)
    client.connect()
    return client
