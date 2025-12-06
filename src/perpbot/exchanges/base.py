from __future__ import annotations

import random
import string
from abc import ABC, abstractmethod
from typing import Iterable, List

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


def _random_id(prefix: str = "ord") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{suffix}"


class ExchangeClient(ABC):
    name: str

    @abstractmethod
    def fetch_price(self, symbol: str) -> PriceQuote:
        ...

    @abstractmethod
    def place_order(self, request: OrderRequest) -> Order:
        ...

    @abstractmethod
    def close_position(self, position: Position, current_price: float) -> Order:
        ...


class SimulatedExchangeClient(ExchangeClient):
    def __init__(self, name: str, base_price: float = 100.0, fee_bps: float = 5):
        self.name = name
        self.price = base_price
        self.fee_bps = fee_bps

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


def provision_exchanges() -> List[ExchangeClient]:
    return [SimulatedExchangeClient(name) for name in EXCHANGE_NAMES]


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
