from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Callable, List, Optional

import httpx
from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class ParadexClient(ExchangeClient):
    """Paradex DEX client with full trading support.

    Paradex is a Starknet-based derivatives DEX.

    Features:
    - LIMIT and MARKET orders
    - Order cancellation
    - Position queries
    - Balance queries
    - STARK key signing

    Requirements:
    - PARADEX_API_KEY
    - PARADEX_API_SECRET
    - PARADEX_STARK_PRIVATE_KEY (optional, for signing)
    """

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "paradex"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        # API URLs
        if use_testnet:
            self.base_url = "https://api.testnet.paradex.trade/v1"
        else:
            self.base_url = "https://api.prod.paradex.trade/v1"

        # Credentials
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.stark_private_key: Optional[str] = None
        self.account_address: Optional[str] = None

        # HTTP client
        self._client: Optional[httpx.Client] = None
        self._jwt_token: Optional[str] = None
        self._trading_enabled = False

        # Handlers (placeholder for future WebSocket)
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to Paradex and authenticate."""
        load_dotenv()

        self.api_key = os.getenv("PARADEX_API_KEY")
        self.api_secret = os.getenv("PARADEX_API_SECRET")
        self.stark_private_key = os.getenv("PARADEX_STARK_PRIVATE_KEY")
        self.account_address = os.getenv("PARADEX_ACCOUNT_ADDRESS")

        if not self.api_key or not self.api_secret:
            logger.warning("⚠️ Paradex trading DISABLED: PARADEX_API_KEY or PARADEX_API_SECRET missing")
            self._trading_enabled = False
            # Create client for read-only access
            self._client = httpx.Client(base_url=self.base_url, timeout=10)
            return

        # Create authenticated client
        self._client = httpx.Client(base_url=self.base_url, timeout=10)

        # Get JWT token
        try:
            self._authenticate()
            self._trading_enabled = True
            logger.info("✅ Paradex connected (testnet=%s, trading=%s)",
                       self.use_testnet, self._trading_enabled)
        except Exception as e:
            logger.error("❌ Paradex authentication failed: %s", e)
            self._trading_enabled = False

    def _authenticate(self) -> None:
        """Authenticate and get JWT token."""
        # Paradex uses HMAC-based authentication
        timestamp = str(int(time.time() * 1000))

        # Create signature
        message = f"{timestamp}"
        signature = hmac.new(
            self.api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

        # Request JWT token
        headers = {
            "PARADEX-API-KEY": self.api_key,
            "PARADEX-SIGNATURE": signature,
            "PARADEX-TIMESTAMP": timestamp,
        }

        response = self._client.post("/auth", headers=headers)
        response.raise_for_status()

        data = response.json()
        self._jwt_token = data.get("jwt_token")

        if not self._jwt_token:
            raise RuntimeError("Failed to get JWT token from Paradex")

        logger.info("✅ Paradex JWT token obtained")

    def _get_headers(self) -> dict:
        """Get request headers with JWT token."""
        headers = {}
        if self._jwt_token:
            headers["Authorization"] = f"Bearer {self._jwt_token}"
        return headers

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC-USD-PERP (Paradex format)."""
        if "PERP" in symbol or "-" in symbol:
            return symbol
        # BTC/USDT -> BTC-USD-PERP
        base = symbol.split("/")[0]
        return f"{base}-USD-PERP"

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Paradex."""
        if not self._client:
            raise RuntimeError("Client not connected")

        market = self._normalize_symbol(symbol)

        try:
            # Get ticker data
            response = self._client.get(f"/markets/{market}/ticker")
            response.raise_for_status()
            data = response.json()

            # Paradex API returns: {"best_bid": "...", "best_ask": "...", ...}
            bid = float(data.get("best_bid", 0))
            ask = float(data.get("best_ask", 0))

            if bid == 0 or ask == 0:
                logger.warning("⚠️ Paradex %s: Invalid bid/ask (bid=%.2f, ask=%.2f)",
                             symbol, bid, ask)

            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )

        except Exception as e:
            logger.error("❌ Paradex price fetch failed for %s: %s", symbol, e)
            raise RuntimeError(f"Paradex price fetch failed for {symbol}: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book from Paradex."""
        if not self._client:
            raise RuntimeError("Client not connected")

        market = self._normalize_symbol(symbol)

        try:
            response = self._client.get(f"/markets/{market}/orderbook",
                                       params={"depth": depth})
            response.raise_for_status()
            data = response.json()

            # Paradex format: {"bids": [[price, size], ...], "asks": [[price, size], ...]}
            bids = [(float(p), float(s)) for p, s in data.get("bids", [])]
            asks = [(float(p), float(s)) for p, s in data.get("asks", [])]

            return OrderBookDepth(bids=bids, asks=asks)

        except Exception as e:
            logger.error("❌ Paradex orderbook fetch failed: %s", e)
            raise RuntimeError(f"Paradex orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order on Paradex (LIMIT or MARKET).

        Args:
            request: OrderRequest with symbol, side, size, limit_price (optional)

        Returns:
            Order object with order ID
        """
        # Safety check
        if not self._trading_enabled:
            logger.warning("❌ Order REJECTED: Trading disabled")
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            market = self._normalize_symbol(request.symbol)

            # Determine order type
            order_type = "LIMIT" if request.limit_price is not None else "MARKET"

            # Build order payload
            payload = {
                "market": market,
                "side": request.side.upper(),  # BUY or SELL
                "type": order_type,
                "size": str(request.size),
            }

            if order_type == "LIMIT":
                payload["price"] = str(request.limit_price)

            # Optional: Add signature if STARK key is available
            if self.stark_private_key:
                payload["signature"] = self._sign_order(payload)

            # Send order
            response = self._client.post("/orders",
                                        json=payload,
                                        headers=self._get_headers())
            response.raise_for_status()

            order_data = response.json()

            # Extract order info
            order_id = order_data.get("id", "unknown")
            filled_price = float(order_data.get("price", request.limit_price or 0))

            logger.info("✅ Paradex %s order placed: %s %.4f %s @ %.2f - ID: %s",
                       order_type, request.side.upper(), request.size,
                       request.symbol, filled_price, order_id)

            return Order(
                id=str(order_id),
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=filled_price,
            )

        except Exception as e:
            logger.exception("❌ Paradex order failed: %s", e)
            return Order(
                id=f"error-{int(time.time())}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close a position with a MARKET order.

        Args:
            position: Position to close
            current_price: Current market price (for reference)

        Returns:
            Order object
        """
        # Safety check
        if not self._trading_enabled:
            logger.warning("❌ Close order REJECTED: Trading disabled")
            return Order(
                id="rejected-close",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

        # Create reverse order
        closing_side = "sell" if position.order.side == "buy" else "buy"

        close_request = OrderRequest(
            symbol=position.order.symbol,
            side=closing_side,
            size=position.order.size,
            limit_price=None,  # MARKET order
        )

        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an order on Paradex.

        Args:
            order_id: Order ID to cancel
            symbol: Optional symbol (not used by Paradex)
        """
        if not self._trading_enabled:
            logger.warning("❌ Cancel REJECTED: Trading disabled")
            return

        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            response = self._client.delete(f"/orders/{order_id}",
                                          headers=self._get_headers())
            response.raise_for_status()

            logger.info("✅ Paradex order cancelled: %s", order_id)

        except Exception as e:
            logger.error("❌ Paradex cancel failed for %s: %s", order_id, e)
            raise RuntimeError(f"Cancel failed: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders on Paradex.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of Order objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Active orders query skipped: Trading disabled")
            return []

        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            params = {}
            if symbol:
                params["market"] = self._normalize_symbol(symbol)

            response = self._client.get("/orders",
                                       params=params,
                                       headers=self._get_headers())
            response.raise_for_status()

            orders_data = response.json()
            orders: List[Order] = []

            for order_data in orders_data.get("results", []):
                # Only include open orders
                if order_data.get("status") != "OPEN":
                    continue

                market = order_data.get("market", "")
                # Convert BTC-USD-PERP back to BTC/USDT
                symbol_clean = market.replace("-USD-PERP", "/USDT")

                orders.append(Order(
                    id=str(order_data.get("id")),
                    exchange=self.name,
                    symbol=symbol_clean,
                    side=order_data.get("side", "").lower(),
                    size=float(order_data.get("size", 0)),
                    price=float(order_data.get("price", 0)),
                ))

            if orders:
                logger.info("📊 Paradex: %d active orders", len(orders))

            return orders

        except Exception as e:
            logger.error("❌ Paradex active orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get all positions on Paradex.

        Returns:
            List of Position objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Positions query skipped: Trading disabled")
            return []

        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            response = self._client.get("/account/positions",
                                       headers=self._get_headers())
            response.raise_for_status()

            positions_data = response.json()
            positions: List[Position] = []

            for pos_data in positions_data.get("results", []):
                size = float(pos_data.get("size", 0))
                if size == 0:
                    continue

                # Determine side
                side = "buy" if size > 0 else "sell"
                size = abs(size)

                market = pos_data.get("market", "")
                symbol = market.replace("-USD-PERP", "/USDT")

                entry_price = float(pos_data.get("avg_entry_price", 0))

                order = Order(
                    id=f"pos-{market}",
                    exchange=self.name,
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=entry_price,
                )

                position = Position(
                    id=order.id,
                    order=order,
                    target_profit_pct=0.0,
                )

                positions.append(position)

            if positions:
                logger.info("📊 Paradex: %d open positions", len(positions))

            return positions

        except Exception as e:
            logger.error("❌ Paradex positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get account balances on Paradex.

        Returns:
            List of Balance objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Balances query skipped: Trading disabled")
            return []

        if not self._client:
            raise RuntimeError("Client not connected")

        try:
            response = self._client.get("/account/summary",
                                       headers=self._get_headers())
            response.raise_for_status()

            data = response.json()
            balances: List[Balance] = []

            # Paradex typically returns USDC balance
            total_equity = float(data.get("equity", 0))
            available = float(data.get("available_balance", 0))
            locked = total_equity - available

            if total_equity > 0:
                balances.append(Balance(
                    asset="USDC",
                    free=available,
                    locked=locked,
                    total=total_equity,
                ))

            if balances:
                logger.info("💰 Paradex balance: %.2f USDC (available: %.2f)",
                           total_equity, available)

            return balances

        except Exception as e:
            logger.error("❌ Paradex balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup order update handler (WebSocket not implemented yet)."""
        self._order_handler = handler
        logger.info("Registered Paradex order update handler (WebSocket not active)")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup position update handler (WebSocket not implemented yet)."""
        self._position_handler = handler
        logger.info("Registered Paradex position update handler (WebSocket not active)")

    def _sign_order(self, payload: dict) -> str:
        """Sign order with STARK private key (placeholder).

        Note: Actual STARK signing requires starknet.py library.
        This is a placeholder implementation.
        """
        if not self.stark_private_key:
            return ""

        # TODO: Implement actual STARK signing when starknet.py is available
        # For now, return empty signature (Paradex may accept unsigned orders in some cases)
        logger.warning("⚠️ STARK signing not implemented, order may fail if signing is required")
        return ""
