"""GRVT Exchange DEX client.

GRVT (Gravity Markets) is a hybrid derivatives exchange on ZK-rollup.
API Documentation: https://api-docs.grvt.io/
SDK: pip install grvt-pysdk

Environment Variables:
- GRVT_API_KEY: API key
- GRVT_PRIVATE_KEY: Private key for EIP-712 signing
- GRVT_TRADING_ACCOUNT_ID: Trading account ID
- GRVT_ENV: mainnet or testnet (default: mainnet)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class GRVTClient(ExchangeClient):
    """GRVT Exchange client.
    
    Features:
    - Hybrid exchange with ZK-rollup settlement
    - Crypto perpetual futures up to 50x leverage
    - EIP-712 signing for orders
    - Low latency order matching
    """

    MAINNET_API = "https://trades.grvt.io"
    TESTNET_API = "https://trades.testnet.grvt.io"
    MAINNET_WS = "wss://trades.grvt.io/ws"
    TESTNET_WS = "wss://trades.testnet.grvt.io/ws"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "grvt"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key: Optional[str] = None
        self.private_key: Optional[str] = None
        self.trading_account_id: Optional[str] = None
        
        self.base_url: str = ""
        self.ws_url: str = ""
        self._client = None
        self._sdk = None
        self._trading_enabled = False
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to GRVT."""
        load_dotenv()

        self.api_key = os.getenv("GRVT_API_KEY")
        self.private_key = os.getenv("GRVT_PRIVATE_KEY")
        self.trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID")
        
        env = os.getenv("GRVT_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        self.base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        if not self.api_key:
            logger.warning("⚠️ GRVT trading DISABLED: GRVT_API_KEY missing")
            self._trading_enabled = False
            return

        try:
            # Try to use official SDK
            try:
                from grvt.grvt_raw_sync import GrvtRawSync
                from grvt.grvt_env_config import GrvtEnvConfig
                
                env_config = GrvtEnvConfig.TESTNET if self.use_testnet else GrvtEnvConfig.PROD
                self._sdk = GrvtRawSync(
                    env=env_config,
                    api_key=self.api_key,
                    private_key=self.private_key,
                    trading_account_id=self.trading_account_id,
                )
                logger.info("✅ GRVT SDK initialized")
            except ImportError:
                logger.info("GRVT SDK not available, using REST API")
                import httpx
                self._client = httpx.Client(
                    base_url=self.base_url,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                    timeout=15.0
                )

            self._trading_enabled = True
            logger.info("✅ GRVT connected (testnet=%s)", self.use_testnet)

        except Exception as e:
            logger.exception("❌ GRVT connection failed: %s", e)
            self._trading_enabled = False

    def _request(self, method: str, path: str, params: dict = None, json_body: dict = None):
        """Make HTTP request."""
        if not self._client:
            raise RuntimeError("Client not connected")
        
        headers = {"X-Timestamp": str(int(time.time() * 1000))}
        resp = self._client.request(method, path, params=params, json=json_body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC_USDT_Perp."""
        if "Perp" in symbol:
            return symbol
        base = symbol.replace("/", "_").replace("-", "_")
        if not base.endswith("_Perp"):
            base += "_Perp"
        return base

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current price."""
        market = self._normalize_symbol(symbol)
        
        try:
            if self._sdk:
                result = self._sdk.get_ticker(instrument=market)
                bid = float(result.best_bid_price or 0)
                ask = float(result.best_ask_price or 0)
            else:
                data = self._request("GET", f"/full/v1/ticker", params={"instrument": market})
                result = data.get("result", data)
                bid = float(result.get("bestBidPrice", result.get("bid", 0)))
                ask = float(result.get("bestAskPrice", result.get("ask", 0)))
            
            return PriceQuote(exchange=self.name, symbol=symbol, bid=bid, ask=ask, venue_type="dex")
        except Exception as e:
            logger.error("❌ GRVT price fetch failed: %s", e)
            raise RuntimeError(f"GRVT price fetch failed: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book."""
        market = self._normalize_symbol(symbol)
        
        try:
            if self._sdk:
                result = self._sdk.get_orderbook(instrument=market, depth=depth)
                bids = [(float(l.price), float(l.size)) for l in result.bids[:depth]]
                asks = [(float(l.price), float(l.size)) for l in result.asks[:depth]]
            else:
                data = self._request("GET", f"/full/v1/orderbook", params={"instrument": market, "depth": depth})
                result = data.get("result", data)
                bids = [(float(b["price"]), float(b["size"])) for b in result.get("bids", [])[:depth]]
                asks = [(float(a["price"]), float(a["size"])) for a in result.get("asks", [])[:depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
        except Exception as e:
            logger.error("❌ GRVT orderbook fetch failed: %s", e)
            raise RuntimeError(f"GRVT orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order."""
        if not self._trading_enabled:
            return Order(id="rejected", exchange=self.name, symbol=request.symbol,
                        side=request.side, size=request.size, price=0.0)

        market = self._normalize_symbol(request.symbol)
        
        try:
            is_limit = request.limit_price is not None
            
            if self._sdk:
                if is_limit:
                    result = self._sdk.create_order(
                        instrument=market,
                        side=request.side.upper(),
                        order_type="LIMIT",
                        size=str(request.size),
                        price=str(request.limit_price),
                        time_in_force="GTC",
                    )
                else:
                    result = self._sdk.create_order(
                        instrument=market,
                        side=request.side.upper(),
                        order_type="MARKET",
                        size=str(request.size),
                    )
                order_id = str(result.order_id)
                filled_price = float(result.price or request.limit_price or 0)
            else:
                order_data = {
                    "instrument": market,
                    "side": request.side.upper(),
                    "type": "LIMIT" if is_limit else "MARKET",
                    "size": str(request.size),
                }
                if is_limit:
                    order_data["price"] = str(request.limit_price)
                    order_data["timeInForce"] = "GTC"
                
                resp = self._request("POST", "/full/v1/create_order", json_body=order_data)
                result = resp.get("result", resp)
                order_id = str(result.get("orderId", result.get("id", "unknown")))
                filled_price = float(result.get("price", request.limit_price or 0))
            
            logger.info("✅ GRVT order placed: %s - ID: %s", request.symbol, order_id)
            
            return Order(
                id=order_id, exchange=self.name, symbol=request.symbol,
                side=request.side, size=request.size, price=filled_price,
            )
        except Exception as e:
            logger.exception("❌ GRVT order failed: %s", e)
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
            if self._sdk:
                self._sdk.cancel_order(order_id=order_id)
            else:
                self._request("POST", "/full/v1/cancel_order", json_body={"orderId": order_id})
            logger.info("✅ GRVT order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ GRVT cancel failed: %s", e)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders."""
        if not self._trading_enabled:
            return []
        try:
            if self._sdk:
                orders_data = self._sdk.get_open_orders()
            else:
                params = {}
                if symbol:
                    params["instrument"] = self._normalize_symbol(symbol)
                resp = self._request("POST", "/full/v1/open_orders", json_body=params)
                orders_data = resp.get("result", resp)
            
            orders = []
            for o in orders_data or []:
                if hasattr(o, 'instrument'):
                    sym = o.instrument.replace("_Perp", "").replace("_", "/")
                    orders.append(Order(
                        id=str(o.order_id), exchange=self.name, symbol=sym,
                        side=str(o.side).lower(), size=float(o.size), price=float(o.price or 0),
                    ))
                else:
                    sym = o.get("instrument", "").replace("_Perp", "").replace("_", "/")
                    orders.append(Order(
                        id=str(o.get("orderId", o.get("id", ""))),
                        exchange=self.name, symbol=sym,
                        side=str(o.get("side", "")).lower(),
                        size=float(o.get("size", 0)), price=float(o.get("price", 0)),
                    ))
            return orders
        except Exception as e:
            logger.error("❌ GRVT orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get positions."""
        if not self._trading_enabled:
            return []
        try:
            if self._sdk:
                positions_data = self._sdk.get_positions()
            else:
                resp = self._request("POST", "/full/v1/positions")
                positions_data = resp.get("result", resp)
            
            positions = []
            for p in positions_data or []:
                if hasattr(p, 'size'):
                    size = float(p.size)
                    if size == 0:
                        continue
                    side = "buy" if size > 0 else "sell"
                    sym = p.instrument.replace("_Perp", "").replace("_", "/")
                    entry = float(p.entry_price or 0)
                else:
                    size = float(p.get("size", 0))
                    if size == 0:
                        continue
                    side = "buy" if size > 0 else "sell"
                    sym = p.get("instrument", "").replace("_Perp", "").replace("_", "/")
                    entry = float(p.get("entryPrice", p.get("avgPrice", 0)))
                
                order = Order(
                    id=f"pos-{sym}", exchange=self.name, symbol=sym,
                    side=side, size=abs(size), price=entry,
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error("❌ GRVT positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get balances."""
        if not self._trading_enabled:
            return []
        try:
            if self._sdk:
                account = self._sdk.get_account()
                total = float(account.equity or 0)
                available = float(account.available or total)
            else:
                resp = self._request("POST", "/full/v1/account_summary")
                data = resp.get("result", resp)
                total = float(data.get("equity", data.get("balance", 0)))
                available = float(data.get("available", data.get("freeCollateral", total)))
            
            if total > 0:
                return [Balance(asset="USDC", free=available, locked=total-available, total=total)]
            return []
        except Exception as e:
            logger.error("❌ GRVT balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
