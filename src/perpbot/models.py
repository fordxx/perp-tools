from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional


Side = Literal["buy", "sell"]


@dataclass
class PriceQuote:
    exchange: str
    symbol: str
    bid: float
    ask: float
    ts: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass
class OrderRequest:
    symbol: str
    side: Side
    size: float
    limit_price: Optional[float] = None


@dataclass
class Order:
    id: str
    exchange: str
    symbol: str
    side: Side
    size: float
    price: float
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Position:
    id: str
    order: Order
    target_profit_pct: float
    open_ts: datetime = field(default_factory=datetime.utcnow)
    closed_ts: Optional[datetime] = None

    def is_open(self) -> bool:
        return self.closed_ts is None


@dataclass
class ArbitrageOpportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    edge: float
    discovered_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AlertCondition:
    symbol: str
    direction: Literal["above", "below"]
    price: float
    action: Literal["notify", "auto-order"] = "notify"
    size: float = 0
    side: Optional[Side] = None


@dataclass
class TradingState:
    quotes: Dict[str, PriceQuote] = field(default_factory=dict)
    open_positions: Dict[str, Position] = field(default_factory=dict)
    recent_arbitrage: List[ArbitrageOpportunity] = field(default_factory=list)
    triggered_alerts: List[str] = field(default_factory=list)
