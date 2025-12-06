from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional, Sequence, Tuple


Side = Literal["buy", "sell"]


@dataclass
class PriceQuote:
    exchange: str
    symbol: str
    bid: float
    ask: float
    order_book: Optional["OrderBookDepth"] = None
    maker_fee_bps: float = 0.0
    taker_fee_bps: float = 0.0
    funding_rate: float = 0.0
    slippage_bps: float = 0.0
    venue_type: Literal["dex", "cex"] = "dex"
    ts: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def is_dex(self) -> bool:
        return self.venue_type == "dex"

    def executable_price(self, side: Side, size: float, default_slippage_bps: float = 0.0) -> Optional[float]:
        """Return the volume-weighted executable price for the requested size.

        If order book depth is unavailable, fall back to best bid/ask and apply
        slippage pessimistically.
        """

        depth_price = None
        if self.order_book:
            depth_price = self.order_book.volume_weighted_price(side, size)

        if depth_price is None:
            best = self.ask if side == "buy" else self.bid
            depth_price = best

        slippage = self.slippage_bps or default_slippage_bps
        if slippage:
            adjust = 1 + slippage / 10_000 if side == "buy" else 1 - slippage / 10_000
            depth_price *= adjust

        return depth_price


@dataclass
class OrderBookDepth:
    bids: Sequence[Tuple[float, float]] = field(default_factory=list)
    asks: Sequence[Tuple[float, float]] = field(default_factory=list)

    def volume_weighted_price(self, side: Side, size: float) -> Optional[float]:
        levels = self.asks if side == "buy" else self.bids
        remaining = size
        notional = 0.0
        for price, qty in levels:
            take = min(remaining, qty)
            notional += price * take
            remaining -= take
            if remaining <= 0:
                break
        if remaining > 1e-9:
            return None
        return notional / size


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
class Balance:
    asset: str
    free: float
    locked: float = 0.0
    total: float = 0.0

    @property
    def available(self) -> float:
        return self.free


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
    size: float
    expected_pnl: float
    net_profit_pct: float
    confidence: float = 1.0
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
    account_positions: List[Position] = field(default_factory=list)
    equity: float = 0.0
    pnl: float = 0.0
    equity_history: List[Tuple[datetime, float]] = field(default_factory=list)
    pnl_history: List[Tuple[datetime, float]] = field(default_factory=list)
    last_cycle_at: Optional[datetime] = None
    trading_enabled: bool = True
    status: str = "initializing"
    min_profit_pct: float = 0.0
