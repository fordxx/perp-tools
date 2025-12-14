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
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class BinanceClient(ExchangeClient):
    """USDT-M Futures client using REST + WebSocket user data stream."""

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "binance"
        self.venue_type = "cex"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.base_url = "https://testnet.binancefuture.com" if use_testnet else "https://fapi.binance.com"
        self.ws_base = "wss://stream.binancefuture.com" if use_testnet else "wss://fstream.binance.com"
        self._client: Optional[httpx.Client] = None
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None
        self._listen_key: Optional[str] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._listen_key_lock = threading.Lock()
        self._keepalive_thread: Optional[threading.Thread] = None
        self._keepalive_stop = threading.Event()

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
        self._ensure_listen_key()
        self._start_user_stream()
        self._start_listen_key_keepalive()

    def disconnect(self) -> None:
        self._stop_event.set()
        self._keepalive_stop.set()

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2.0)

        if self._keepalive_thread and self._keepalive_thread.is_alive():
            self._keepalive_thread.join(timeout=2.0)

        try:
            if self._client:
                self._client.close()
        finally:
            self._client = None

    # REST 辅助方法
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

    def _ensure_listen_key(self) -> str:
        """Create (or refresh) the user-data-stream listenKey."""
        if not self._client:
            raise RuntimeError("Client not connected")
        resp = self._client.post("/fapi/v1/listenKey")
        resp.raise_for_status()
        listen_key = resp.json().get("listenKey")
        with self._listen_key_lock:
            self._listen_key = listen_key
        logger.info("Obtained Binance listenKey for user stream")
        if not listen_key:
            raise RuntimeError("Failed to obtain listenKey")
        return listen_key

    def _start_user_stream(self) -> None:
        """Start (or restart) the WebSocket consumer thread."""
        if self._ws_thread and self._ws_thread.is_alive():
            return
        self._ws_thread = threading.Thread(target=self._run_user_stream, daemon=True, name="BinanceUserStream")
        self._ws_thread.start()

    def _start_listen_key_keepalive(self) -> None:
        if self._keepalive_thread and self._keepalive_thread.is_alive():
            return

        def _run() -> None:
            # Binance Futures: keepalive required within 60 minutes; we renew every 25 minutes.
            interval = 25 * 60
            while not self._keepalive_stop.is_set():
                self._keepalive_stop.wait(interval)
                if self._keepalive_stop.is_set():
                    break
                try:
                    self._renew_listen_key()
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.warning("Binance listenKey keepalive failed: %s", exc)
                    # Attempt to recreate listenKey; websocket loop will reconnect using the new key.
                    try:
                        self._ensure_listen_key()
                    except Exception as create_exc:
                        logger.warning("Binance listenKey recreate failed: %s", create_exc)

        self._keepalive_thread = threading.Thread(target=_run, daemon=True, name="BinanceListenKeyKeepalive")
        self._keepalive_thread.start()

    def _renew_listen_key(self) -> None:
        if not self._client:
            raise RuntimeError("Client not connected")
        with self._listen_key_lock:
            listen_key = self._listen_key
        if not listen_key:
            raise RuntimeError("listenKey missing")
        resp = self._client.put("/fapi/v1/listenKey", params={"listenKey": listen_key})
        resp.raise_for_status()
        logger.debug("Renewed Binance listenKey")

    def _run_user_stream(self) -> None:
        async def _consume() -> None:
            while not self._stop_event.is_set():
                with self._listen_key_lock:
                    listen_key = self._listen_key
                if not listen_key:
                    await asyncio.sleep(1)
                    continue
                url = f"{self.ws_base}/ws/{listen_key}"
                try:
                    async with websockets.connect(url, ping_interval=15) as ws:
                        async for msg in ws:
                            data = json.loads(msg)
                            event_type = data.get("e") or data.get("eventType")
                            if event_type == "ACCOUNT_UPDATE" and self._position_handler:
                                self._position_handler(data)
                            elif self._order_handler:
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
            venue_type="cex",
        )
        return quote

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        if not self._client:
            raise RuntimeError("Client not connected")
        sym = self._normalize_symbol(symbol)
        resp = self._client.get("/fapi/v1/depth", params={"symbol": sym, "limit": depth})
        resp.raise_for_status()
        data = resp.json()
        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q in data.get("bids", [])],
            asks=[(float(p), float(q)) for p, q in data.get("asks", [])],
        )

    def place_open_order(self, request: OrderRequest) -> Order:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def place_close_order(self, position: Position, current_price: float) -> Order:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def get_account_positions(self) -> List[Position]:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def get_account_balances(self) -> List[Balance]:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        raise NotImplementedError("Binance trading is disabled; CEX is reference-only")
