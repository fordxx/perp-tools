"""Lighter DEX client.

Lighter is a high-performance perpetual futures DEX built on Ethereum L2.
Uses official Python SDK: lighter-v1-python

API Documentation: https://apidocs.lighter.xyz
SDK: pip install lighter-v1-python

Environment Variables:
- LIGHTER_API_KEY: API key for authentication
- LIGHTER_PRIVATE_KEY: Private key for signing orders
- LIGHTER_ENV: mainnet or testnet (default: mainnet)
"""
from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class LighterClient(ExchangeClient):
    """Lighter DEX client using official SDK.
    
    Features:
    - Ethereum L2 with zk-rollup technology
    - Zero-fee perpetuals trading
    - Verifiable order matching
    - Non-custodial (funds stay in wallet until execution)
    """

    # API endpoints
    MAINNET_API = "https://mainnet.zklighter.elliot.ai"
    TESTNET_API = "https://testnet.zklighter.elliot.ai"
    MAINNET_WS = "wss://mainnet.zklighter.elliot.ai/stream"
    TESTNET_WS = "wss://testnet.zklighter.elliot.ai/stream"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "lighter"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key: Optional[str] = None
        self.private_key: Optional[str] = None
        
        self.base_url: str = ""
        self.ws_url: str = ""
        self.rpc_url: str = ""
        self._client = None
        self._api = None
        self._trading_enabled = False
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to Lighter using API key and initialize SDK if available."""
        load_dotenv()

        self.api_key = os.getenv("LIGHTER_API_KEY")
        self.private_key = os.getenv("LIGHTER_PRIVATE_KEY")
        
        env = os.getenv("LIGHTER_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        default_api = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.base_url = os.getenv("LIGHTER_API_BASE_URL", default_api)
        self.rpc_url = os.getenv("LIGHTER_RPC_URL", self.base_url)
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        # Always initialize client for read-only mode support
        self._trading_enabled = False
        
        if not self.api_key:
            logger.warning("⚠️ Lighter trading DISABLED: LIGHTER_API_KEY missing (read-only mode)")
            # Initialize basic HTTP client for read-only operations
            try:
                import httpx
                self._client = httpx.Client(
                    base_url=self.base_url,
                    headers={"Content-Type": "application/json"},
                    timeout=15.0
                )
            except ImportError:
                logger.debug("httpx not available for fallback mode")
            logger.info("✅ Lighter connected (testnet=%s, trading=False)", self.use_testnet)
            return

        try:
            # Try to use official SDK
            try:
                from lighter.lighter_client import Client as LighterClientSDK
                
                self._api = LighterClientSDK(
                    private_key=self.private_key,
                    api_auth=self.api_key,
                    web3_provider_url=self.rpc_url,
                )
                logger.info("✅ Lighter SDK initialized")
                
            except ImportError:
                logger.info("Lighter SDK not available, using REST API")
                import httpx
                self._client = httpx.Client(
                    base_url=self.base_url,
                    headers={
                        "X-Api-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=15.0
                )

            self._trading_enabled = True
            logger.info("✅ Lighter connected (testnet=%s, trading=True)", self.use_testnet)

        except Exception as e:
            logger.exception("❌ Lighter connection failed: %s", e)
            self._trading_enabled = False

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC_USDT format for Lighter."""
        if "/" in symbol:
            return symbol.replace("/", "_")
        return symbol

    def _request(self, method: str, path: str, params: dict = None, json_body: dict = None):
        """Make HTTP request to Lighter API."""
        if not self._client:
            logger.warning("⚠️ No HTTP client available, returning mock data")
            if "orderbook" in path:
                symbol = path.split("/")[-1] if "/" in path else "BTC_USDT"
                return self._mock_orderbook_response(symbol)
            return {}
        
        resp = self._client.request(method, path, params=params, json=json_body)
        resp.raise_for_status()
        return resp.json()

    def _mock_orderbook_response(self, symbol: str) -> dict:
        """Return mock orderbook data."""
        import random
        mid_price = 92000.0
        bids = [[mid_price - (i * 10), random.uniform(0.1, 5.0)] for i in range(1, 11)]
        asks = [[mid_price + (i * 10), random.uniform(0.1, 5.0)] for i in range(1, 11)]
        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "best_bid_price": bids[0][0] if bids else 0,
            "best_ask_price": asks[0][0] if asks else 0,
        }


    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Lighter."""
        market = self._normalize_symbol(symbol)
        
        try:
            if self._api:
                # Use SDK
                ob = self._api.get_orderbook(market_symbol=market)
                bid = float(ob.best_bid_price) if ob.best_bid_price else 0
                ask = float(ob.best_ask_price) if ob.best_ask_price else 0
            else:
                # Use REST API
                data = self._request("GET", f"/api/v1/orderbook/{market}")
                bid = float(data.get("bestBid", {}).get("price", 0))
                ask = float(data.get("bestAsk", {}).get("price", 0))

            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )
            
        except Exception as e:
            logger.error("❌ Lighter price fetch failed for %s: %s", symbol, e)
            # Return zero quote on failure
            return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type="dex")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book from Lighter."""
        market = self._normalize_symbol(symbol)
        
        try:
            if self._api:
                ob = self._api.get_orderbook(market_symbol=market, limit=depth)
                bids = [(float(o.price), float(o.size)) for o in ob.bids[:depth]]
                asks = [(float(o.price), float(o.size)) for o in ob.asks[:depth]]
            else:
                data = self._request("GET", f"/api/v1/orderbook/{market}", params={"limit": depth})
                bids = [(float(b["price"]), float(b["size"])) for b in data.get("bids", [])[:depth]]
                asks = [(float(a["price"]), float(a["size"])) for a in data.get("asks", [])[:depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
            
        except Exception as e:
            logger.error("❌ Lighter orderbook fetch failed: %s", e)
            # Return empty orderbook on failure
            return OrderBookDepth(bids=[], asks=[])

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order on Lighter."""
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

        market = self._normalize_symbol(request.symbol)
        
        try:
            is_limit = request.limit_price is not None
            order_type = "LIMIT" if is_limit else "MARKET"
            
            if self._api:
                # Use SDK
                if is_limit:
                    result = self._api.create_limit_order(
                        market_symbol=market,
                        side=request.side.upper(),
                        size=str(request.size),
                        price=str(request.limit_price),
                    )
                else:
                    result = self._api.create_market_order(
                        market_symbol=market,
                        side=request.side.upper(),
                        size=str(request.size),
                    )
                order_id = str(result.order_id)
                filled_price = float(result.price or request.limit_price or 0)
            else:
                # Use REST API
                order_data = {
                    "market": market,
                    "side": request.side.upper(),
                    "type": order_type,
                    "size": str(request.size),
                }
                if is_limit:
                    order_data["price"] = str(request.limit_price)
                
                resp = self._request("POST", "/api/v1/order", json_body=order_data)
                order_id = str(resp.get("orderId", resp.get("id", "unknown")))
                filled_price = float(resp.get("price", request.limit_price or 0))
            
            logger.info("✅ Lighter %s order placed: %s %.4f %s @ %.2f - ID: %s",
                       order_type, request.side.upper(), request.size,
                       request.symbol, filled_price, order_id)
            
            return Order(
                id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=filled_price,
            )
            
        except Exception as e:
            logger.exception("❌ Lighter order failed: %s", e)
            return Order(
                id=f"error-{os.urandom(4).hex()}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close a position with a market order."""
        if not self._trading_enabled:
            return Order(
                id="rejected-close",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

        closing_side = "sell" if position.order.side == "buy" else "buy"
        
        close_request = OrderRequest(
            symbol=position.order.symbol,
            side=closing_side,
            size=position.order.size,
            limit_price=None,
        )
        
        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an order on Lighter."""
        if not self._trading_enabled:
            logger.warning("❌ Cancel REJECTED: Trading disabled")
            return

        try:
            if self._api:
                self._api.cancel_order(order_id=order_id)
            else:
                self._request("DELETE", f"/api/v1/order/{order_id}")
            logger.info("✅ Lighter order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ Lighter cancel failed for %s: %s", order_id, e)
            raise RuntimeError(f"Cancel failed: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if self._api:
                orders_data = self._api.get_open_orders()
            else:
                params = {}
                if symbol:
                    params["market"] = self._normalize_symbol(symbol)
                resp = self._request("GET", "/api/v1/orders", params=params)
                orders_data = resp.get("orders", resp) if isinstance(resp, dict) else resp
            
            orders: List[Order] = []
            for raw in orders_data or []:
                if hasattr(raw, 'market_symbol'):
                    # SDK object
                    market = raw.market_symbol
                    symbol_clean = market.replace("_", "/")
                    orders.append(Order(
                        id=str(raw.order_id),
                        exchange=self.name,
                        symbol=symbol_clean,
                        side=str(raw.side).lower(),
                        size=float(raw.size),
                        price=float(raw.price or 0),
                    ))
                else:
                    # Dict from REST API
                    market = raw.get("market", "")
                    symbol_clean = market.replace("_", "/")
                    orders.append(Order(
                        id=str(raw.get("orderId", raw.get("id", ""))),
                        exchange=self.name,
                        symbol=symbol_clean,
                        side=str(raw.get("side", "")).lower(),
                        size=float(raw.get("size", 0)),
                        price=float(raw.get("price", 0)),
                    ))
            
            if orders:
                logger.info("📊 Lighter: %d active orders", len(orders))
            
            return orders
            
        except Exception as e:
            logger.error("❌ Lighter active orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get all positions on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if self._api:
                positions_data = self._api.get_positions()
            else:
                resp = self._request("GET", "/api/v1/positions")
                positions_data = resp.get("positions", resp) if isinstance(resp, dict) else resp
            
            positions: List[Position] = []
            for raw in positions_data or []:
                if hasattr(raw, 'size'):
                    # SDK object
                    size = float(raw.size)
                    if size == 0:
                        continue
                    side = "buy" if size > 0 else "sell"
                    size = abs(size)
                    market = raw.market_symbol
                    symbol = market.replace("_", "/")
                    entry_price = float(raw.entry_price or 0)
                else:
                    # Dict from REST API
                    size = float(raw.get("size", 0))
                    if size == 0:
                        continue
                    side = "buy" if size > 0 else "sell"
                    size = abs(size)
                    market = raw.get("market", "")
                    symbol = market.replace("_", "/")
                    entry_price = float(raw.get("entryPrice", raw.get("avgPrice", 0)))
                
                order = Order(
                    id=f"pos-{market}",
                    exchange=self.name,
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=entry_price,
                )
                
                positions.append(Position(
                    id=order.id,
                    order=order,
                    target_profit_pct=0.0,
                ))
            
            if positions:
                logger.info("📊 Lighter: %d open positions", len(positions))
            
            return positions
            
        except Exception as e:
            logger.error("❌ Lighter positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get account balances on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if self._api:
                account = self._api.get_account()
                total_equity = float(account.equity or 0)
                available = float(account.available_balance or total_equity)
            else:
                resp = self._request("GET", "/api/v1/account")
                total_equity = float(resp.get("equity", resp.get("balance", 0)))
                available = float(resp.get("availableBalance", resp.get("freeBalance", total_equity)))
            
            balances: List[Balance] = []
            locked = total_equity - available
            
            if total_equity > 0:
                balances.append(Balance(
                    asset="USDC",
                    free=available,
                    locked=locked,
                    total=total_equity,
                ))
            
            if balances:
                logger.info("💰 Lighter balance: %.2f USDC (available: %.2f)",
                           total_equity, available)
            
            return balances
            
        except Exception as e:
            logger.error("❌ Lighter balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Set up order update callback."""
        self._order_handler = handler
        logger.info("✅ Registered Lighter order update handler")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Set up position update callback."""
        self._position_handler = handler
        logger.info("✅ Registered Lighter position update handler")
