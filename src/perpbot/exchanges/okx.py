from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Callable, List, Optional

import httpx
import websockets

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class OKXClient(ExchangeClient):
    """OKX SWAP (perpetual) client supporting live and paper trading."""

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "okx"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.base_url = "https://www.okx.com" if not use_testnet else "https://www.okx.com"
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/private"
        if use_testnet:
            self.ws_url = "wss://wspap.okx.com:8443/ws/v5/private"
        self._client: Optional[httpx.Client] = None
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def connect(self) -> None:
        from dotenv import load_dotenv
        import os

        load_dotenv()
        self.api_key = os.getenv("OKX_API_KEY")
        self.api_secret = os.getenv("OKX_API_SECRET")
        self.passphrase = os.getenv("OKX_PASSPHRASE")
        if not all([self.api_key, self.api_secret, self.passphrase]):
            raise ValueError("OKX_API_KEY, OKX_API_SECRET, and OKX_PASSPHRASE are required")

        headers = {"OK-ACCESS-KEY": self.api_key, "OK-ACCESS-PASSPHRASE": self.passphrase}
        if self.use_testnet:
            headers["x-simulated-trading"] = "1"
        self._client = httpx.Client(base_url=self.base_url, headers=headers, timeout=10)
        logger.info("Initialized OKX client (testnet=%s)", self.use_testnet)
        self._start_private_ws()

    # Signing helpers
    def _timestamp(self) -> str:
        return str(time.time())

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        prehash = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(self.api_secret.encode(), prehash.encode(), hashlib.sha256).digest()
        return base64.b64encode(mac).decode()

    def _request(self, method: str, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> httpx.Response:
        if not self._client or not self.api_key or not self.api_secret or not self.passphrase:
            raise RuntimeError("Client not connected")
        timestamp = self._timestamp()
        body_str = json.dumps(json_body) if json_body else ""
        sign = self._sign(timestamp, method, path, body_str)
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-SIGN": sign,
        }
        if self.use_testnet:
            headers["x-simulated-trading"] = "1"
        logger.debug("OKX %s %s", method, path)
        response = self._client.request(method, path, params=params, json=json_body, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data.get("code") not in ("0", 0, None):
            raise RuntimeError(f"OKX error {data}")
        return response

    def _format_instrument(self, symbol: str) -> str:
        return symbol.replace("/", "-").upper() + "-SWAP"

    def get_current_price(self, symbol: str) -> PriceQuote:
        inst_id = self._format_instrument(symbol)
        resp = httpx.get(f"https://www.okx.com/api/v5/market/ticker", params={"instId": inst_id})
        resp.raise_for_status()
        data = resp.json().get("data", [{}])[0]
        return PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=float(data.get("bidPx", 0)),
            ask=float(data.get("askPx", 0)),
        )

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        inst_id = self._format_instrument(symbol)
        resp = httpx.get("https://www.okx.com/api/v5/market/books", params={"instId": inst_id, "sz": depth})
        resp.raise_for_status()
        data = resp.json().get("data", [{}])[0]
        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q, *_ in data.get("bids", [])],
            asks=[(float(p), float(q)) for p, q, *_ in data.get("asks", [])],
        )

    def place_open_order(self, request: OrderRequest) -> Order:
        inst_id = self._format_instrument(request.symbol)
        ord_type = "limit" if request.limit_price is not None else "market"
        body = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": "buy" if request.side == "buy" else "sell",
            "ordType": ord_type,
            "sz": str(request.size),
        }
        if request.limit_price is not None:
            body["px"] = str(request.limit_price)
        resp = self._request("POST", "/api/v5/trade/order", json_body=body)
        data = resp.json().get("data", [{}])[0]
        price = request.limit_price or 0.0
        return Order(
            id=data.get("ordId", ""),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=price,
        )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        inst_id = self._format_instrument(position.order.symbol)
        close_side = "sell" if position.order.side == "buy" else "buy"
        body = {
            "instId": inst_id,
            "tdMode": "cross",
            "side": close_side,
            "ordType": "market",
            "sz": str(position.order.size),
            "reduceOnly": "true",
        }
        resp = self._request("POST", "/api/v5/trade/order", json_body=body)
        data = resp.json().get("data", [{}])[0]
        return Order(
            id=data.get("ordId", ""),
            exchange=self.name,
            symbol=position.order.symbol,
            side=close_side,
            size=position.order.size,
            price=current_price,
        )

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        inst_id = self._format_instrument(symbol) if symbol else None
        body = {"ordId": order_id}
        if inst_id:
            body["instId"] = inst_id
        self._request("POST", "/api/v5/trade/cancel-order", json_body=body)
        logger.info("Cancelled OKX order %s", order_id)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        params = {"instType": "SWAP"}
        if symbol:
            params["instId"] = self._format_instrument(symbol)
        resp = self._request("GET", "/api/v5/trade/orders-pending", params=params)
        orders: List[Order] = []
        for raw in resp.json().get("data", []):
            orders.append(
                Order(
                    id=raw.get("ordId", ""),
                    exchange=self.name,
                    symbol=raw.get("instId", symbol or ""),
                    side=raw.get("side", "").lower(),
                    size=float(raw.get("sz", 0)),
                    price=float(raw.get("px", 0) or 0),
                )
            )
        return orders

    def get_account_positions(self) -> List[Position]:
        resp = self._request("GET", "/api/v5/account/positions", params={"instType": "SWAP"})
        positions: List[Position] = []
        for raw in resp.json().get("data", []):
            size = float(raw.get("pos", 0))
            if size == 0:
                continue
            side = "buy" if raw.get("posSide") == "long" else "sell"
            order = Order(
                id=f"pos-{raw.get('instId', '')}",
                exchange=self.name,
                symbol=raw.get("instId", ""),
                side=side,
                size=abs(size),
                price=float(raw.get("avgPx", 0)),
            )
            positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
        return positions

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler
        logger.info("Registered OKX order update handler")

    # WebSocket
    def _start_private_ws(self) -> None:
        if not all([self.api_key, self.api_secret, self.passphrase]):
            raise RuntimeError("Client not connected")
        self._ws_thread = threading.Thread(target=self._run_private_ws, daemon=True)
        self._ws_thread.start()

    def _login_payload(self) -> dict:
        timestamp = self._timestamp()
        sign = self._sign(timestamp, "GET", "/users/self/verify")
        return {
            "op": "login",
            "args": [
                {
                    "apiKey": self.api_key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": sign,
                }
            ],
        }

    def _run_private_ws(self) -> None:
        async def _consume() -> None:
            headers = {"x-simulated-trading": "1"} if self.use_testnet else None
            while not self._stop_event.is_set():
                try:
                    async with websockets.connect(self.ws_url, ping_interval=15, extra_headers=headers) as ws:
                        await ws.send(json.dumps(self._login_payload()))
                        if self._order_handler:
                            await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "orders", "instType": "SWAP"}]}))
                        async for msg in ws:
                            data = json.loads(msg)
                            if self._order_handler and data.get("event") is None:
                                self._order_handler(data)
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.exception("OKX private stream error: %s", exc)
                    await asyncio.sleep(5)

        asyncio.run(_consume())
