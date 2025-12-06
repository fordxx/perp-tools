from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
import os
import random
import string
import threading
import time
from abc import ABC, abstractmethod
from typing import Callable, Iterable, List, Optional

import httpx
import websockets
from dotenv import load_dotenv

from perpbot.models import (
    AlertCondition,
    Order,
    Balance,
    OrderBookDepth,
    OrderRequest,
    Position,
    PriceQuote,
    TradingState,
)


EXCHANGE_NAMES = [
    "edgex",
    "backpack",
    "paradex",
    "aster",
    "grvt",
    "extended",
    "okx",
    "binance",
]

logger = logging.getLogger(__name__)


def _random_id(prefix: str = "ord") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{suffix}"


class ExchangeClient(ABC):
    name: str
    venue_type: str = "dex"

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> PriceQuote:
        ...

    @abstractmethod
    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        ...

    @abstractmethod
    def place_open_order(self, request: OrderRequest) -> Order:
        ...

    @abstractmethod
    def place_close_order(self, position: Position, current_price: float) -> Order:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        ...

    @abstractmethod
    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        ...

    @abstractmethod
    def get_account_positions(self) -> List[Position]:
        ...

    @abstractmethod
    def get_account_balances(self) -> List[Balance]:
        ...

    @abstractmethod
    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        ...

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Optional hook for streaming position updates."""
        self._position_handler = handler  # type: ignore[attr-defined]

    # Backward-compatible helpers
    def fetch_price(self, symbol: str) -> PriceQuote:
        return self.get_current_price(symbol)

    def place_order(self, request: OrderRequest) -> Order:
        return self.place_open_order(request)

    def close_position(self, position: Position, current_price: float) -> Order:
        return self.place_close_order(position, current_price)


class RESTWebSocketExchangeClient(ExchangeClient):
    """Generic REST + WebSocket exchange client template.

    Concrete venues should inherit and override endpoints or signing logic as
    required by their APIs. This class centralises consistent logging,
    credential loading, and graceful retries.
    """

    ticker_endpoint: str = "/api/v1/market/ticker"
    orderbook_endpoint: str = "/api/v1/market/depth"
    order_endpoint: str = "/api/v1/trade/order"
    cancel_endpoint: str = "/api/v1/trade/cancel"
    open_orders_endpoint: str = "/api/v1/trade/open-orders"
    positions_endpoint: str = "/api/v1/account/positions"
    ws_orders_channel: str = "orders"
    ws_positions_channel: str = "positions"
    balance_endpoint: str = "/api/v1/account/balances"

    def __init__(
        self,
        name: str,
        env_prefix: str,
        default_base_url: str,
        default_testnet_url: Optional[str] = None,
        default_ws_url: Optional[str] = None,
        default_testnet_ws_url: Optional[str] = None,
        venue_type: str = "dex",
    ) -> None:
        self.name = name
        self.env_prefix = env_prefix
        self.venue_type = venue_type
        self.default_base_url = default_base_url
        self.default_testnet_url = default_testnet_url or default_base_url
        self.default_ws_url = default_ws_url
        self.default_testnet_ws_url = default_testnet_ws_url or default_ws_url

        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.base_url: Optional[str] = None
        self.ws_url: Optional[str] = None
        self._client: Optional[httpx.Client] = None
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _env(self, suffix: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(f"{self.env_prefix}_{suffix}", default)

    def connect(self) -> None:
        load_dotenv()
        self.api_key = self._env("API_KEY")
        self.api_secret = self._env("API_SECRET")
        self.passphrase = self._env("PASSPHRASE")
        if not self.api_key:
            raise ValueError(f"{self.name} API key missing from environment")

        env = self._env("ENV", "testnet").lower()
        self.base_url = self._env(
            "BASE_URL", self.default_testnet_url if env == "testnet" else self.default_base_url
        )
        self.ws_url = self._env(
            "WS_URL", self.default_testnet_ws_url if env == "testnet" else self.default_ws_url
        )
        self._client = httpx.Client(base_url=self.base_url, headers=self._auth_headers(), timeout=10)
        logger.info("Connected %s client (env=%s)", self.name, env)
        if self.ws_url:
            self._start_ws()

    def _auth_headers(self) -> dict:
        headers = {}
        if self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def _sign_payload(self, payload: str) -> Optional[str]:
        if not self.api_secret:
            return None
        import hmac
        from hashlib import sha256

        signature = hmac.new(self.api_secret.encode(), payload.encode(), sha256).hexdigest()
        return signature

    def _request(self, method: str, path: str, params: Optional[dict] = None, json_body: Optional[dict] = None) -> httpx.Response:
        if not self._client:
            raise RuntimeError("Client not connected")
        params = params or {}
        payload = f"{int(time.time() * 1000)}{method}{path}{json_body or params}"
        signature = self._sign_payload(payload)
        headers = self._auth_headers()
        if signature:
            headers["X-SIGNATURE"] = signature
        logger.debug("%s %s %s", self.name, method, path)
        response = self._client.request(method, path, params=params, json=json_body, headers=headers)
        response.raise_for_status()
        return response

    def _parse_orderbook(self, data: dict) -> OrderBookDepth:
        bids = data.get("bids") or data.get("bid") or []
        asks = data.get("asks") or data.get("ask") or []
        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q in bids],
            asks=[(float(p), float(q)) for p, q in asks],
        )

    def _format_symbol(self, symbol: str) -> str:
        return symbol

    def get_current_price(self, symbol: str) -> PriceQuote:
        market = self._format_symbol(symbol)
        resp = self._request("GET", self.ticker_endpoint, params={"symbol": market})
        data = resp.json()
        if isinstance(data, dict):
            payload = data.get("data", data)
        else:
            payload = data[0]
        bid = float(payload.get("bid") or payload.get("bidPrice") or payload.get("bestBid", 0))
        ask = float(payload.get("ask") or payload.get("askPrice") or payload.get("bestAsk", 0))
        ob_data = payload.get("orderbook")
        order_book = self._parse_orderbook(ob_data) if isinstance(ob_data, dict) else None
        return PriceQuote(exchange=self.name, symbol=symbol, bid=bid, ask=ask, order_book=order_book)

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        market = self._format_symbol(symbol)
        resp = self._request("GET", self.orderbook_endpoint, params={"symbol": market, "depth": depth})
        data = resp.json()
        book_data = data.get("data", data) if isinstance(data, dict) else data
        depth_obj = self._parse_orderbook(book_data)
        return depth_obj

    def place_open_order(self, request: OrderRequest) -> Order:
        market = self._format_symbol(request.symbol)
        body = {
            "symbol": market,
            "side": request.side,
            "type": "limit" if request.limit_price is not None else "market",
            "size": request.size,
        }
        if request.limit_price is not None:
            body["price"] = request.limit_price
        resp = self._request("POST", self.order_endpoint, json_body=body)
        data = resp.json()
        order_id = str(data.get("orderId") or data.get("id") or _random_id())
        price = float(data.get("price") or request.limit_price or 0)
        return Order(id=order_id, exchange=self.name, symbol=request.symbol, side=request.side, size=request.size, price=price)

    def place_close_order(self, position: Position, current_price: float) -> Order:
        market = self._format_symbol(position.order.symbol)
        closing_side = "sell" if position.order.side == "buy" else "buy"
        body = {
            "symbol": market,
            "side": closing_side,
            "type": "market",
            "size": position.order.size,
            "reduceOnly": True,
        }
        resp = self._request("POST", self.order_endpoint, json_body=body)
        data = resp.json()
        order_id = str(data.get("orderId") or data.get("id") or _random_id("close"))
        price = float(data.get("price") or current_price)
        return Order(id=order_id, exchange=self.name, symbol=position.order.symbol, side=closing_side, size=position.order.size, price=price)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        market = self._format_symbol(symbol) if symbol else None
        params = {"orderId": order_id}
        if market:
            params["symbol"] = market
        self._request("POST", self.cancel_endpoint, json_body=params)
        logger.info("Cancelled %s order %s", self.name, order_id)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        market = self._format_symbol(symbol) if symbol else None
        params = {"symbol": market} if market else None
        resp = self._request("GET", self.open_orders_endpoint, params=params)
        payload = resp.json()
        orders_data = payload.get("data", payload) if isinstance(payload, dict) else payload
        orders: List[Order] = []
        for raw in orders_data or []:
            orders.append(
                Order(
                    id=str(raw.get("orderId") or raw.get("id") or _random_id()),
                    exchange=self.name,
                    symbol=raw.get("symbol", symbol or ""),
                    side=str(raw.get("side", "")).lower(),
                    size=float(raw.get("size", raw.get("qty", 0))),
                    price=float(raw.get("price", 0) or 0),
                )
            )
        return orders

    def get_account_positions(self) -> List[Position]:
        resp = self._request("GET", self.positions_endpoint)
        payload = resp.json()
        positions_data = payload.get("data", payload) if isinstance(payload, dict) else payload
        positions: List[Position] = []
        for raw in positions_data or []:
            size = float(raw.get("size", 0))
            if size == 0:
                continue
            side = str(raw.get("side", "")).lower() or ("buy" if size > 0 else "sell")
            symbol = raw.get("symbol", "")
            entry = float(raw.get("entryPrice", raw.get("avgPrice", 0)))
            order = Order(id=_random_id("pos"), exchange=self.name, symbol=symbol, side=side, size=abs(size), price=entry)
            positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
        return positions

    def get_account_balances(self) -> List[Balance]:
        resp = self._request("GET", self.balance_endpoint)
        payload = resp.json()
        balances_data = payload.get("data", payload) if isinstance(payload, dict) else payload
        balances: List[Balance] = []
        for raw in balances_data or []:
            try:
                asset = raw.get("asset") or raw.get("currency") or raw.get("coin")
                free = float(raw.get("free", raw.get("available", 0)))
                locked = float(raw.get("locked", raw.get("frozen", 0) or 0))
                total = float(raw.get("total", free + locked))
                balances.append(Balance(asset=asset, free=free, locked=locked, total=total))
            except Exception:
                logger.exception("Failed to parse balance payload on %s: %s", self.name, raw)
        return balances

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler
        logger.info("Registered %s order update handler", self.name)

    def _start_ws(self) -> None:
        if not self.ws_url:
            return
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self._ws_thread.start()

    def _ws_subscribe_message(self) -> List[dict]:
        channels = [self.ws_orders_channel]
        if self.ws_positions_channel:
            channels.append(self.ws_positions_channel)
        return [
            {"op": "subscribe", "channel": channel}
            for channel in channels
        ]

    def _dispatch_ws_message(self, data: dict) -> None:
        channel = data.get("channel") or data.get("topic")
        if channel == self.ws_orders_channel and self._order_handler:
            self._order_handler(data)
        elif channel == self.ws_positions_channel and self._position_handler:
            self._position_handler(data)

    def _run_ws(self) -> None:
        async def _consume() -> None:
            assert self.ws_url
            while not self._stop_event.is_set():
                try:
                    async with websockets.connect(self.ws_url, ping_interval=15) as ws:
                        for msg in self._ws_subscribe_message():
                            await ws.send(json.dumps(msg))
                        async for msg in ws:
                            try:
                                data = json.loads(msg)
                                self._dispatch_ws_message(data)
                            except Exception:
                                logger.exception("Error handling %s order stream message", self.name)
                except Exception as exc:  # pragma: no cover - network dependent
                    logger.exception("%s order stream error: %s", self.name, exc)
                    await asyncio.sleep(5)

        asyncio.run(_consume())


def provision_exchanges() -> List[ExchangeClient]:
    load_dotenv()
    exchanges: List[ExchangeClient] = []

    from perpbot.exchanges.binance import BinanceClient
    from perpbot.exchanges.okx import OKXClient
    from perpbot.exchanges.edgex import EdgeXClient
    from perpbot.exchanges.backpack import BackpackClient
    from perpbot.exchanges.paradex import ParadexClient
    from perpbot.exchanges.aster import AsterClient
    from perpbot.exchanges.grvt import GRVTClient
    from perpbot.exchanges.extended import ExtendedClient

    exchange_builders = [
        (
            "binance",
            "cex",
            lambda: BinanceClient(use_testnet=os.getenv("BINANCE_ENV", "testnet").lower() == "testnet"),
            ["BINANCE_API_KEY", "BINANCE_API_SECRET"],
        ),
        (
            "okx",
            "cex",
            lambda: OKXClient(use_testnet=os.getenv("OKX_ENV", "testnet").lower() == "testnet"),
            ["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"],
        ),
        ("edgex", "dex", lambda: EdgeXClient(), ["EDGEX_API_KEY", "EDGEX_API_SECRET"]),
        ("backpack", "dex", lambda: BackpackClient(), ["BACKPACK_API_KEY", "BACKPACK_API_SECRET"]),
        ("paradex", "dex", lambda: ParadexClient(), ["PARADEX_API_KEY", "PARADEX_API_SECRET"]),
        ("aster", "dex", lambda: AsterClient(), ["ASTER_API_KEY", "ASTER_API_SECRET"]),
        ("grvt", "dex", lambda: GRVTClient(), ["GRVT_API_KEY", "GRVT_API_SECRET"]),
        ("extended", "dex", lambda: ExtendedClient(), ["EXTENDED_API_KEY", "EXTENDED_API_SECRET"]),
    ]

    for name, venue_type, builder, required_keys in exchange_builders:
        missing = [k for k in required_keys if not os.getenv(k)]
        if missing:
            logger.warning("Skipping %s: missing credentials %s", name, missing)
            continue
        try:
            client = builder()
            client.venue_type = venue_type
            client.connect()
            exchanges.append(client)
            logger.info("Provisioned %s exchange (%s)", name, venue_type)
        except Exception as exc:  # pragma: no cover - runtime resilience
            logger.exception("Failed to initialise %s client: %s", name, exc)

    return exchanges


def update_state_with_quotes(state: TradingState, exchanges: Iterable[ExchangeClient], symbols: Iterable[str]) -> None:
    from perpbot.exchanges.pricing import WebsocketPriceMonitor, fetch_quotes_concurrently

    monitor = getattr(state, "price_monitor", None)
    if monitor is None:
        monitor = WebsocketPriceMonitor()
        state.price_monitor = monitor  # type: ignore[attr-defined]

    async def _collect():
        return await fetch_quotes_concurrently(exchanges, symbols, per_exchange_limit=getattr(state, "per_exchange_limit", 2), monitor=monitor)

    quotes = asyncio.run(_collect())
    for quote in quotes:
        state.quotes[f"{quote.exchange}:{quote.symbol}"] = quote
        history = state.price_history.setdefault(quote.symbol, [])
        history.append((datetime.utcnow(), quote.mid))
        if len(history) > 500:
            del history[: len(history) - 500]


def evaluate_alerts(state: TradingState, alerts: Iterable[AlertCondition]) -> List[AlertCondition]:
    triggered = []
    for alert in alerts:
        quote = next((q for q in state.quotes.values() if q.symbol == alert.symbol), None)
        if not quote:
            continue
        price = quote.mid
        if alert.direction == "above" and price >= alert.price:
            triggered.append(alert)
        elif alert.direction == "below" and price <= alert.price:
            triggered.append(alert)
    state.triggered_alerts.extend([f"{a.symbol} {a.direction} {a.price}" for a in triggered])
    return triggered
