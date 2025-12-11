"""Aster DEX client.

AsterDEX is a decentralized perpetual exchange on BNB Chain.
API Documentation: https://github.com/asterdex/api-docs

Environment Variables:
- ASTER_API_KEY: API key
- ASTER_API_SECRET: API secret for signing
- ASTER_ENV: mainnet or testnet (default: mainnet)
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


class AsterClient(ExchangeClient):
    """Aster DEX client.
    
    Features:
    - Decentralized perpetual exchange
    - Stock perpetuals with up to 50x leverage
    - BNB Chain, Ethereum, Solana, Arbitrum support
    - USDT settled
    """

    MAINNET_API = "https://fapi.asterdex.com"
    TESTNET_API = "https://testnet-fapi.asterdex.com"
    MAINNET_WS = "wss://fstream.asterdex.com/ws"
    TESTNET_WS = "wss://testnet-fstream.asterdex.com/ws"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "aster"
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
        """Connect to Aster."""
        load_dotenv()

        self.api_key = os.getenv("ASTER_API_KEY")
        self.api_secret = os.getenv("ASTER_API_SECRET")
        
        env = os.getenv("ASTER_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        self.base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        if not self.api_key:
            logger.warning("⚠️ Aster trading DISABLED: ASTER_API_KEY missing")
            self._trading_enabled = False
            return

        try:
            import httpx
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Content-Type": "application/json"},
                timeout=15.0
            )
            
            self._trading_enabled = True
            logger.info("✅ Aster connected (testnet=%s)", self.use_testnet)

        except Exception as e:
            logger.exception("❌ Aster connection failed: %s", e)
            self._trading_enabled = False

    def _sign(self, params: dict) -> str:
        """Sign parameters with HMAC-SHA256."""
        if not self.api_secret:
            return ""
        # Sort params and create query string
        sorted_params = sorted(params.items())
        query = "&".join(f"{k}={v}" for k, v in sorted_params)
        return hmac.new(
            self.api_secret.encode(),
            query.encode(),
            hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, path: str, params: dict = None, json_body: dict = None, signed: bool = False):
        """Make HTTP request."""
        if not self._client:
            raise RuntimeError("Client not connected")
        
        params = params or {}
        headers = {"X-MBX-APIKEY": self.api_key}
        
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 5000
            params["signature"] = self._sign(params)
        
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
            data = self._request("GET", "/fapi/v1/ticker/bookTicker", params={"symbol": market})
            
            bid = float(data.get("bidPrice", 0))
            ask = float(data.get("askPrice", 0))
            
            return PriceQuote(exchange=self.name, symbol=symbol, bid=bid, ask=ask, venue_type="dex")
        except Exception as e:
            logger.error("❌ Aster price fetch failed: %s", e)
            raise RuntimeError(f"Aster price fetch failed: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book."""
        market = self._normalize_symbol(symbol)
        
        try:
            data = self._request("GET", "/fapi/v1/depth", params={"symbol": market, "limit": depth})
            
            bids = [(float(p), float(q)) for p, q in data.get("bids", [])[:depth]]
            asks = [(float(p), float(q)) for p, q in data.get("asks", [])[:depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
        except Exception as e:
            logger.error("❌ Aster orderbook fetch failed: %s", e)
            raise RuntimeError(f"Aster orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order."""
        if not self._trading_enabled:
            return Order(id="rejected", exchange=self.name, symbol=request.symbol,
                        side=request.side, size=request.size, price=0.0)

        market = self._normalize_symbol(request.symbol)
        
        try:
            params = {
                "symbol": market,
                "side": request.side.upper(),
                "type": "LIMIT" if request.limit_price else "MARKET",
                "quantity": str(request.size),
            }
            if request.limit_price:
                params["price"] = str(request.limit_price)
                params["timeInForce"] = "GTC"
            
            resp = self._request("POST", "/fapi/v1/order", params=params, signed=True)
            
            order_id = str(resp.get("orderId", resp.get("id", "unknown")))
            filled_price = float(resp.get("price", request.limit_price or 0))
            
            logger.info("✅ Aster order placed: %s - ID: %s", request.symbol, order_id)
            
            return Order(
                id=order_id, exchange=self.name, symbol=request.symbol,
                side=request.side, size=request.size, price=filled_price,
            )
        except Exception as e:
            logger.exception("❌ Aster order failed: %s", e)
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
            self._request("DELETE", "/fapi/v1/order", params=params, signed=True)
            logger.info("✅ Aster order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ Aster cancel failed: %s", e)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders."""
        if not self._trading_enabled:
            return []
        try:
            params = {}
            if symbol:
                params["symbol"] = self._normalize_symbol(symbol)
            resp = self._request("GET", "/fapi/v1/openOrders", params=params, signed=True)
            
            orders = []
            for o in resp or []:
                orders.append(Order(
                    id=str(o.get("orderId", o.get("id", ""))),
                    exchange=self.name,
                    symbol=o.get("symbol", ""),
                    side=str(o.get("side", "")).lower(),
                    size=float(o.get("origQty", o.get("quantity", 0))),
                    price=float(o.get("price", 0)),
                ))
            return orders
        except Exception as e:
            logger.error("❌ Aster orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get positions."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/fapi/v2/positionRisk", signed=True)
            
            positions = []
            for p in resp or []:
                size = float(p.get("positionAmt", 0))
                if size == 0:
                    continue
                side = "buy" if size > 0 else "sell"
                order = Order(
                    id=f"pos-{p.get('symbol', '')}",
                    exchange=self.name,
                    symbol=p.get("symbol", ""),
                    side=side,
                    size=abs(size),
                    price=float(p.get("entryPrice", 0)),
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error("❌ Aster positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get balances."""
        if not self._trading_enabled:
            return []
        try:
            resp = self._request("GET", "/fapi/v2/balance", signed=True)
            
            balances = []
            for b in resp or []:
                total = float(b.get("balance", 0))
                available = float(b.get("availableBalance", b.get("crossWalletBalance", total)))
                if total > 0:
                    balances.append(Balance(
                        asset=b.get("asset", "USDT"),
                        free=available,
                        locked=total - available,
                        total=total,
                    ))
            return balances
        except Exception as e:
            logger.error("❌ Aster balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
