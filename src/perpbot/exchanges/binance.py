from __future__ import annotations

import asyncio
import hmac
import json
import logging
import threading
import time
from hashlib import sha256
from typing import Callable, List, Optional
from urllib.parse import urlencode

import httpx
import websockets

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class BinanceClient(ExchangeClient):
    """USDT-M Futures client using REST + WebSocket user data stream."""

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "binance"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.base_url = "https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"
        self.ws_base = "wss://stream.binancefuture.com" if use_testnet else "wss://fstream.binance.com"
        self._client: Optional[httpx.Client] = None
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._listen_key: Optional[str] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def connect(self) -> None:
        from dotenv import load_dotenv
        import os

        load_dotenv()
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        if not self.api_key or not self.api_secret:
            raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required")

        self._client = httpx.Client(base_url=self.base_url, headers={"X-MBX-APIKEY": self.api_key}, timeout=10)
        logger.info("Initialized Binance client (testnet=%s)", self.use_testnet)
        self._start_user_stream()

    # REST helpers
    def _signed_request(self, method: str, path: str, params: Optional[dict] = None) -> httpx.Response:
        if not self._client or not self.api_secret:
            raise RuntimeError("Client not connected")
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        query = urlencode(params, doseq=True)
        signature = hmac.new(self.api_secret.encode(), query.encode(), sha256).hexdigest()
        signed_query = f"{query}&signature={signature}"
        url = f"{path}?{signed_query}"
        logger.debug("Binance %s %s", method, url)
        response = self._client.request(method, url)
        response.raise_for_status()
        return response

    def _start_user_stream(self) -> None:
        if not self._client:
            raise RuntimeError("Client not connected")
        resp = self._client.post("/fapi/v1/listenKey")
        resp.raise_for_status()
        self._listen_key = resp.json().get("listenKey")
        logger.info("Obtained Binance listenKey for user stream")
        if self._listen_key:
            self._ws_thread = threading.Thread(target=self._run_user_stream, daemon=True)
            self._ws_thread.start()

    def _run_user_stream(self) -> None:
        async def _consume() -> None:
            if not self._listen_key:
                return
            url = f"{self.ws_base}/ws/{self._listen_key}"
            while not self._stop_event.is_set():
                try:
                    async with websockets.connect(url, ping_interval=15) as ws:
                        async for msg in ws:
                            data = json.loads(msg)
                            if self._order_handler:
                                self._order_handler(data)
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.exception("Binance user stream error: %s", exc)
                    await asyncio.sleep(5)

        asyncio.run(_consume())

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.replace("/", "").upper()

    def get_current_price(self, symbol: str) -> PriceQuote:
        if not self._client:
            raise RuntimeError("Client not connected")
        sym = self._normalize_symbol(symbol)
        resp = self._client.get("/fapi/v1/ticker/bookTicker", params={"symbol": sym})
        resp.raise_for_status()
        data = resp.json()
        quote = PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=float(data["bidPrice"]),
            ask=float(data["askPrice"]),
        )
        return quote

    def place_open_order(self, request: OrderRequest) -> Order:
        sym = self._normalize_symbol(request.symbol)
        order_type = "LIMIT" if request.limit_price is not None else "MARKET"
        params = {
            "symbol": sym,
            "side": request.side.upper(),
            "type": order_type,
            "quantity": request.size,
        }
        if request.limit_price is not None:
            params.update({"price": request.limit_price, "timeInForce": "GTC"})
        resp = self._signed_request("POST", "/fapi/v1/order", params)
        data = resp.json()
        price = float(data.get("avgPrice") or data.get("price") or request.limit_price or 0)
        return Order(
            id=str(data.get("orderId")),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=price,
        )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        sym = self._normalize_symbol(position.order.symbol)
        side = "SELL" if position.order.side == "buy" else "BUY"
        params = {
            "symbol": sym,
            "side": side,
            "type": "MARKET",
            "quantity": position.order.size,
            "reduceOnly": "true",
        }
        resp = self._signed_request("POST", "/fapi/v1/order", params)
        data = resp.json()
        price = float(data.get("avgPrice") or current_price)
        return Order(
            id=str(data.get("orderId")),
            exchange=self.name,
            symbol=position.order.symbol,
            side="sell" if position.order.side == "buy" else "buy",
            size=position.order.size,
            price=price,
        )

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        if not symbol:
            raise ValueError("symbol is required to cancel an order on Binance")
        sym = self._normalize_symbol(symbol)
        self._signed_request("DELETE", "/fapi/v1/order", {"symbol": sym, "orderId": order_id})
        logger.info("Cancelled Binance order %s (%s)", order_id, symbol)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        params = {"symbol": self._normalize_symbol(symbol)} if symbol else None
        resp = self._signed_request("GET", "/fapi/v1/openOrders", params)
        orders = []
        for raw in resp.json():
            orders.append(
                Order(
                    id=str(raw.get("orderId")),
                    exchange=self.name,
                    symbol=(symbol or raw.get("symbol")),
                    side=raw.get("side", "").lower(),
                    size=float(raw.get("origQty", 0)),
                    price=float(raw.get("price", 0)),
                )
            )
        return orders

    def get_account_positions(self) -> List[Position]:
        resp = self._signed_request("GET", "/fapi/v2/positionRisk")
        positions: List[Position] = []
        for raw in resp.json():
            size = float(raw.get("positionAmt", 0))
            if size == 0:
                continue
            side = "buy" if size > 0 else "sell"
            size_abs = abs(size)
            symbol = raw.get("symbol", "")
            order = Order(
                id=f"pos-{symbol}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size_abs,
                price=float(raw.get("entryPrice", 0)),
            )
            positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
        return positions

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler
        logger.info("Registered Binance order update handler")
