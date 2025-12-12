"""Backpack Exchange DEX client.

Backpack is a crypto exchange with perpetual futures support.
API Documentation: https://docs.backpack.exchange/
Uses ED25519 signing for authenticated requests.

Environment Variables:
- BACKPACK_API_KEY: API key
- BACKPACK_API_SECRET: API secret (base64 encoded ED25519 private key)
- BACKPACK_ENV: mainnet or testnet (default: mainnet)
"""
from __future__ import annotations

import base64
import logging
import os
import time
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class BackpackClient(ExchangeClient):
    """Backpack Exchange client.
    
    Features:
    - Perpetual futures with up to 20x leverage
    - ED25519 authentication
    - Multiple market support
    """

    MAINNET_API = "https://api.backpack.exchange"
    TESTNET_API = "https://api.backpack.exchange"  # Same endpoint, different mode
    MAINNET_WS = "wss://ws.backpack.exchange"
    TESTNET_WS = "wss://ws.backpack.exchange"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "backpack"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        
        self.base_url: str = ""
        self.ws_url: str = ""
        self._client = None
        self._trading_enabled = False
        self._signing_key = None
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to Backpack."""
        load_dotenv()

        self.api_key = os.getenv("BACKPACK_API_KEY")
        self.api_secret = os.getenv("BACKPACK_API_SECRET")
        
        env = os.getenv("BACKPACK_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        self.base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        if not self.api_key or not self.api_secret:
            logger.warning("⚠️ Backpack trading DISABLED: credentials missing")
            self._trading_enabled = False
            return

        try:
            # Initialize ED25519 signing key
            try:
                from nacl.signing import SigningKey
                secret_bytes = base64.b64decode(self.api_secret)
                self._signing_key = SigningKey(secret_bytes[:32])
            except ImportError:
                logger.warning("PyNaCl not installed, signing disabled")
                self._signing_key = None
            except Exception as e:
                logger.warning("Failed to init signing key: %s", e)
                self._signing_key = None

            import httpx
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Content-Type": "application/json"},
                timeout=15.0
            )
            
            self._trading_enabled = True
            logger.info("✅ Backpack connected (testnet=%s)", self.use_testnet)

        except Exception as e:
            logger.exception("❌ Backpack connection failed: %s", e)
            self._trading_enabled = False

    def _sign_request(self, method: str, path: str, timestamp: int, body: str = "") -> dict:
        """Sign request with ED25519."""
        headers = {
            "X-API-Key": self.api_key,
            "X-Timestamp": str(timestamp),
        }
        
        if self._signing_key:
            message = f"instruction={method}&timestamp={timestamp}"
            if body:
                message += f"&body={body}"
            signature = self._signing_key.sign(message.encode())
            headers["X-Signature"] = base64.b64encode(signature.signature).decode()
        
        return headers

    def _request(self, method: str, path: str, params: dict = None, json_body: dict = None):
        """Make authenticated request."""
        if not self._client:
            raise RuntimeError("Client not connected")
        
        timestamp = int(time.time() * 1000)
        body = ""
        if json_body:
            import json
            body = json.dumps(json_body, separators=(',', ':'))
        
        headers = self._sign_request(method, path, timestamp, body)
        
        resp = self._client.request(method, path, params=params, json=json_body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC_USDT_PERP."""
        if "_PERP" in symbol:
            return symbol
        base = symbol.replace("/", "_").replace("-", "_")
        if not base.endswith("_PERP"):
            base += "_PERP"
        return base

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current price."""
        market = self._normalize_symbol(symbol)
        
        try:
            data = self._request("GET", f"/api/v1/ticker", params={"symbol": market})
            
            bid = float(data.get("bidPrice", 0))
            ask = float(data.get("askPrice", 0))
            
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )
        except Exception as e:
            logger.error("❌ Backpack price fetch failed: %s", e)
            raise RuntimeError(f"Backpack price fetch failed: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book."""
        market = self._normalize_symbol(symbol)
        
        try:
            data = self._request("GET", f"/api/v1/depth", params={"symbol": market, "limit": depth})
            
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])[:depth]]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])[:depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
        except Exception as e:
            logger.error("❌ Backpack orderbook fetch failed: %s", e)
            raise RuntimeError(f"Backpack orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order."""
        if not self._trading_enabled:
            return Order(id="rejected", exchange=self.name, symbol=request.symbol,
                        side=request.side, size=request.size, price=0.0)

        market = self._normalize_symbol(request.symbol)
        
        try:
            order_data = {
                "symbol": market,
                "side": request.side.capitalize(),
                "orderType": "Limit" if request.limit_price else "Market",
                "quantity": str(request.size),
            }
            if request.limit_price:
                order_data["price"] = str(request.limit_price)
            
            resp = self._request("POST", "/api/v1/order", json_body=order_data)
            
            order_id = str(resp.get("id", resp.get("orderId", "unknown")))
            filled_price = float(resp.get("price", request.limit_price or 0))
            
            logger.info("✅ Backpack order placed: %s - ID: %s", request.symbol, order_id)
            
            return Order(
                id=order_id, exchange=self.name, symbol=request.symbol,
                side=request.side, size=request.size, price=filled_price,
            )
        except Exception as e:
            logger.exception("❌ Backpack order failed: %s", e)
            return Order(id=f"error-{os.urandom(4).hex()}", exchange=self.name,
                        symbol=request.symbol, side=request.side, size=request.size, price=0.0)

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close position."""
        closing_side = "sell" if position.order.side == "buy" else "buy"
        return self.place_open_order(OrderRequest(
            symbol=position.order.symbol, side=closing_side,
            size=position.order.size, limit_price=None,
        ))

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel order."""
        if not self._trading_enabled:
            return
        try:
            params = {"orderId": order_id}
            if symbol:
                params["symbol"] = self._normalize_symbol(symbol)
            self._request("DELETE", "/api/v1/order", params=params)
            logger.info("✅ Backpack order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ Backpack cancel failed: %s", e)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders."""
        if not self._trading_enabled:
            return []
        try:
            params = {}
            if symbol:
                params["symbol"] = self._normalize_symbol(symbol)
            resp = self._request("GET", "/api/v1/orders", params=params)
            
            orders = []
            for o in resp or []:
                sym = o.get("symbol", "").replace("_PERP", "").replace("_", "/")
                orders.append(Order(
                    id=str(o.get("id", o.get("orderId", ""))),
                    exchange=self.name,
                    symbol=sym,
                    side=str(o.get("side", "")).lower(),
                    size=float(o.get("quantity", 0)),
                    price=float(o.get("price", 0)),
                ))
            return orders
        except Exception as e:
            logger.error("❌ Backpack orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get positions."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/api/v1/positions")
            
            positions = []
            for p in resp or []:
                size = float(p.get("netSize", p.get("size", 0)))
                if size == 0:
                    continue
                side = "buy" if size > 0 else "sell"
                sym = p.get("symbol", "").replace("_PERP", "").replace("_", "/")
                order = Order(
                    id=f"pos-{p.get('symbol', '')}",
                    exchange=self.name,
                    symbol=sym,
                    side=side,
                    size=abs(size),
                    price=float(p.get("entryPrice", p.get("avgPrice", 0))),
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error("❌ Backpack positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get balances."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/api/v1/capital")
            
            balances = []
            for asset, data in (resp or {}).items():
                available = float(data.get("available", 0))
                locked = float(data.get("locked", 0))
                total = available + locked
                if total > 0:
                    balances.append(Balance(asset=asset, free=available, locked=locked, total=total))
            return balances
        except Exception as e:
            logger.error("❌ Backpack balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
