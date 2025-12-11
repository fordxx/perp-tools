"""EdgeX Exchange DEX client.

EdgeX is a high-performance orderbook-based perpetual DEX.
API Documentation: https://docs.edgex.exchange/

Environment Variables:
- EDGEX_API_KEY: API key
- EDGEX_API_SECRET: API secret for signing
- EDGEX_ENV: mainnet or testnet (default: mainnet)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class EdgeXClient(ExchangeClient):
    """EdgeX DEX client.
    
    Features:
    - High-performance orderbook-based Perp DEX
    - Native trading experience for perpetual contracts
    - Multiple market support
    """

    MAINNET_API = "https://api.edgex.exchange"
    TESTNET_API = "https://testnet-api.edgex.exchange"
    MAINNET_WS = "wss://ws.edgex.exchange/ws"
    TESTNET_WS = "wss://testnet-ws.edgex.exchange/ws"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "edgex"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        
        self.base_url: str = ""
        self.ws_url: str = ""
        self._client = None
        self._trading_enabled = False
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to EdgeX."""
        load_dotenv()

        self.api_key = os.getenv("EDGEX_API_KEY")
        self.api_secret = os.getenv("EDGEX_API_SECRET")
        
        env = os.getenv("EDGEX_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        self.base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        if not self.api_key:
            logger.warning("⚠️ EdgeX trading DISABLED: EDGEX_API_KEY missing")
            self._trading_enabled = False
            return

        try:
            import httpx
            self._client = httpx.Client(
                base_url=self.base_url,
                headers=self._auth_headers(),
                timeout=15.0
            )
            
            self._trading_enabled = True
            logger.info("✅ EdgeX connected (testnet=%s)", self.use_testnet)

        except Exception as e:
            logger.exception("❌ EdgeX connection failed: %s", e)
            self._trading_enabled = False

    def _auth_headers(self) -> dict:
        """Generate authentication headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def _sign(self, payload: str) -> str:
        """Sign payload with HMAC-SHA256."""
        if not self.api_secret:
            return ""
        return hmac.new(
            self.api_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, path: str, params: dict = None, json_body: dict = None):
        """Make authenticated request."""
        if not self._client:
            raise RuntimeError("Client not connected")
        
        timestamp = str(int(time.time() * 1000))
        payload = f"{timestamp}{method}{path}"
        signature = self._sign(payload)
        
        headers = {
            "X-TIMESTAMP": timestamp,
            "X-SIGNATURE": signature,
        }
        
        resp = self._client.request(method, path, params=params, json=json_body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTCUSDT."""
        return symbol.replace("/", "").replace("-", "").upper()

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current price."""
        market = self._normalize_symbol(symbol)
        
        try:
            data = self._request("GET", f"/v1/market/ticker", params={"symbol": market})
            result = data.get("data", data)
            
            bid = float(result.get("bestBid", result.get("bid", 0)))
            ask = float(result.get("bestAsk", result.get("ask", 0)))
            
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )
        except Exception as e:
            logger.error("❌ EdgeX price fetch failed: %s", e)
            raise RuntimeError(f"EdgeX price fetch failed: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book."""
        market = self._normalize_symbol(symbol)
        
        try:
            data = self._request("GET", f"/v1/market/depth", params={"symbol": market, "limit": depth})
            result = data.get("data", data)
            
            bids = [(float(p), float(q)) for p, q in result.get("bids", [])[:depth]]
            asks = [(float(p), float(q)) for p, q in result.get("asks", [])[:depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
        except Exception as e:
            logger.error("❌ EdgeX orderbook fetch failed: %s", e)
            raise RuntimeError(f"EdgeX orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order."""
        if not self._trading_enabled:
            return Order(id="rejected", exchange=self.name, symbol=request.symbol,
                        side=request.side, size=request.size, price=0.0)

        market = self._normalize_symbol(request.symbol)
        
        try:
            order_data = {
                "symbol": market,
                "side": request.side.upper(),
                "type": "LIMIT" if request.limit_price else "MARKET",
                "quantity": str(request.size),
            }
            if request.limit_price:
                order_data["price"] = str(request.limit_price)
            
            resp = self._request("POST", "/v1/order", json_body=order_data)
            result = resp.get("data", resp)
            
            order_id = str(result.get("orderId", result.get("id", "unknown")))
            filled_price = float(result.get("price", request.limit_price or 0))
            
            logger.info("✅ EdgeX order placed: %s - ID: %s", request.symbol, order_id)
            
            return Order(
                id=order_id, exchange=self.name, symbol=request.symbol,
                side=request.side, size=request.size, price=filled_price,
            )
        except Exception as e:
            logger.exception("❌ EdgeX order failed: %s", e)
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
            self._request("DELETE", f"/v1/order/{order_id}")
            logger.info("✅ EdgeX order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ EdgeX cancel failed: %s", e)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders."""
        if not self._trading_enabled:
            return []
        try:
            params = {"symbol": self._normalize_symbol(symbol)} if symbol else {}
            resp = self._request("GET", "/v1/orders", params=params)
            orders_data = resp.get("data", resp)
            
            return [Order(
                id=str(o.get("orderId", o.get("id", ""))),
                exchange=self.name,
                symbol=o.get("symbol", ""),
                side=str(o.get("side", "")).lower(),
                size=float(o.get("quantity", o.get("size", 0))),
                price=float(o.get("price", 0)),
            ) for o in orders_data or []]
        except Exception as e:
            logger.error("❌ EdgeX orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get positions."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/v1/positions")
            positions_data = resp.get("data", resp)
            
            positions = []
            for p in positions_data or []:
                size = float(p.get("size", p.get("quantity", 0)))
                if size == 0:
                    continue
                side = "buy" if size > 0 else "sell"
                order = Order(
                    id=f"pos-{p.get('symbol', '')}",
                    exchange=self.name,
                    symbol=p.get("symbol", ""),
                    side=side,
                    size=abs(size),
                    price=float(p.get("entryPrice", p.get("avgPrice", 0))),
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error("❌ EdgeX positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get balances."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/v1/account/balance")
            data = resp.get("data", resp)
            
            total = float(data.get("equity", data.get("totalBalance", 0)))
            available = float(data.get("availableBalance", data.get("available", total)))
            
            if total > 0:
                return [Balance(asset="USDC", free=available, locked=total-available, total=total)]
            return []
        except Exception as e:
            logger.error("❌ EdgeX balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
