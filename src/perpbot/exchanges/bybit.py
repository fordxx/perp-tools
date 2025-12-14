from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class BybitClient(ExchangeClient):
    """Bybit USDT perpetual client (read-only market data).

    Uses `pybit` unified trading HTTP endpoints.
    Trading methods are intentionally disabled in perp-tools.

    Env:
    - BYBIT_API_KEY, BYBIT_API_SECRET (optional for public market data)
    - BYBIT_ENV=mainnet|testnet (optional, default mainnet)
    """

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "bybit"
        self.venue_type = "cex"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self._session = None
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        load_dotenv()

        env = os.getenv("BYBIT_ENV", "mainnet").lower()
        self.use_testnet = env == "testnet"

        self.api_key = os.getenv("BYBIT_API_KEY")
        self.api_secret = os.getenv("BYBIT_API_SECRET")

        try:
            from pybit.unified_trading import HTTP
        except Exception as exc:  # pragma: no cover - depends on optional deps
            raise RuntimeError("Bybit requires pybit. Run: pip install pybit") from exc

        kwargs = {"testnet": self.use_testnet}
        if self.api_key and self.api_secret:
            kwargs.update({"api_key": self.api_key, "api_secret": self.api_secret})

        self._session = HTTP(**kwargs)
        logger.info("Initialized Bybit client (testnet=%s, auth=%s)", self.use_testnet, bool(self.api_key))

    def _normalize_symbol(self, symbol: str) -> str:
        # BTC/USDT -> BTCUSDT
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return f"{base}{quote}".upper()
        return symbol.replace("-", "").upper()

    def get_current_price(self, symbol: str) -> PriceQuote:
        if not self._session:
            raise RuntimeError("Client not connected")

        sym = self._normalize_symbol(symbol)
        resp = self._session.get_tickers(category="linear", symbol=sym)
        result = (resp or {}).get("result") or {}
        items = result.get("list") or []
        if not items:
            raise RuntimeError(f"Bybit ticker missing for {sym}: {resp}")

        item = items[0]
        bid = float(item.get("bid1Price") or 0)
        ask = float(item.get("ask1Price") or 0)

        return PriceQuote(exchange=self.name, symbol=symbol, bid=bid, ask=ask, venue_type="cex")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        if not self._session:
            raise RuntimeError("Client not connected")

        sym = self._normalize_symbol(symbol)
        limit = max(1, min(int(depth), 50))
        resp = self._session.get_orderbook(category="linear", symbol=sym, limit=limit)
        result = (resp or {}).get("result") or {}

        bids_raw = result.get("b") or []
        asks_raw = result.get("a") or []

        bids = [(float(p), float(q)) for p, q in bids_raw[:depth]]
        asks = [(float(p), float(q)) for p, q in asks_raw[:depth]]

        return OrderBookDepth(bids=bids, asks=asks)

    def place_open_order(self, request: OrderRequest) -> Order:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def place_close_order(self, position: Position, current_price: float) -> Order:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def get_account_positions(self) -> List[Position]:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def get_account_balances(self) -> List[Balance]:  # pragma: no cover
        raise NotImplementedError("Bybit trading is disabled; CEX is reference-only")

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:  # pragma: no cover
        raise NotImplementedError("Bybit WebSocket is not wired in perp-tools")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:  # pragma: no cover
        raise NotImplementedError("Bybit WebSocket is not wired in perp-tools")

