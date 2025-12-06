from __future__ import annotations

import logging
import os
import random
import string
from abc import ABC, abstractmethod
from typing import Callable, Iterable, List, Optional

from dotenv import load_dotenv

from perpbot.models import AlertCondition, Order, OrderRequest, Position, PriceQuote, TradingState


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

    @abstractmethod
    def connect(self) -> None:
        ...

    @abstractmethod
    def get_current_price(self, symbol: str) -> PriceQuote:
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
    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        ...

    # Backward-compatible helpers
    def fetch_price(self, symbol: str) -> PriceQuote:
        return self.get_current_price(symbol)

    def place_order(self, request: OrderRequest) -> Order:
        return self.place_open_order(request)

    def close_position(self, position: Position, current_price: float) -> Order:
        return self.place_close_order(position, current_price)


class SimulatedExchangeClient(ExchangeClient):
    def __init__(self, name: str, base_price: float = 100.0, fee_bps: float = 5):
        self.name = name
        self.price = base_price
        self.fee_bps = fee_bps
        self._handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        logger.info("Connected simulated client for %s", self.name)

    def get_current_price(self, symbol: str) -> PriceQuote:
        return self.fetch_price(symbol)

    def _jitter(self) -> float:
        return random.uniform(-0.15, 0.15)

    def fetch_price(self, symbol: str) -> PriceQuote:
        drift = self._jitter()
        mid = max(1.0, self.price * (1 + drift))
        spread = max(0.01 * mid, 0.02)
        quote = PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=mid - spread / 2,
            ask=mid + spread / 2,
        )
        self.price = quote.mid
        return quote

    def place_order(self, request: OrderRequest) -> Order:
        price = request.limit_price if request.limit_price is not None else self.price
        return Order(
            id=_random_id(),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=price,
        )

    def close_position(self, position: Position, current_price: float) -> Order:
        side = "sell" if position.order.side == "buy" else "buy"
        return Order(
            id=_random_id("close"),
            exchange=self.name,
            symbol=position.order.symbol,
            side=side,
            size=position.order.size,
            price=current_price,
        )

    def place_open_order(self, request: OrderRequest) -> Order:
        return self.place_order(request)

    def place_close_order(self, position: Position, current_price: float) -> Order:
        return self.close_position(position, current_price)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        logger.info("Cancelled simulated order %s on %s", order_id, self.name)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        return []

    def get_account_positions(self) -> List[Position]:
        return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._handler = handler
        logger.info("Registered simulated order handler for %s", self.name)


def provision_exchanges() -> List[ExchangeClient]:
    load_dotenv()
    exchanges: List[ExchangeClient] = []

    for name in EXCHANGE_NAMES:
        if name == "binance":
            try:
                from .binance import BinanceClient

                client: ExchangeClient = BinanceClient(
                    use_testnet=os.getenv("BINANCE_ENV", "testnet").lower() == "testnet"
                )
                client.connect()
                exchanges.append(client)
                continue
            except Exception as exc:  # pragma: no cover - safety net for runtime issues
                logger.exception("Falling back to simulated Binance client: %s", exc)

        if name == "okx":
            try:
                from .okx import OKXClient

                client = OKXClient(
                    use_testnet=os.getenv("OKX_ENV", "testnet").lower() == "testnet"
                )
                client.connect()
                exchanges.append(client)
                continue
            except Exception as exc:  # pragma: no cover
                logger.exception("Falling back to simulated OKX client: %s", exc)

        exchanges.append(SimulatedExchangeClient(name))
    return exchanges


def update_state_with_quotes(state: TradingState, exchanges: Iterable[ExchangeClient], symbols: Iterable[str]) -> None:
    for ex in exchanges:
        for sym in symbols:
            quote = ex.fetch_price(sym)
            state.quotes[f"{ex.name}:{sym}"] = quote


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
