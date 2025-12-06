from __future__ import annotations

from typing import Iterable, List

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderRequest, Position, PriceQuote, TradingState


class TakeProfitStrategy:
    """
    Places a market-like order and auto-closes once the target profit percentage is reached.
    """

    def __init__(self, profit_target_pct: float = 0.01):
        self.target = profit_target_pct

    def open_position(self, exchange: ExchangeClient, quote: PriceQuote, size: float, side: str) -> Position:
        order_req = OrderRequest(symbol=quote.symbol, side=side, size=size, limit_price=quote.mid)
        order = exchange.place_order(order_req)
        return Position(id=order.id, order=order, target_profit_pct=self.target)

    def evaluate_positions(self, state: TradingState, quotes: Iterable[PriceQuote], exchanges: List[ExchangeClient]) -> List[Order]:
        closed: List[Order] = []
        quote_map = {q.exchange: q for q in quotes}
        for pos_id, position in list(state.open_positions.items()):
            if not position.is_open():
                continue
            quote = quote_map.get(position.order.exchange)
            if not quote:
                continue
            pnl_pct = (quote.mid - position.order.price) / position.order.price
            if position.order.side == "sell":
                pnl_pct *= -1
            if pnl_pct >= position.target_profit_pct:
                ex = next(ex for ex in exchanges if ex.name == position.order.exchange)
                close_order = ex.close_position(position, quote.mid)
                position.closed_ts = close_order.created_at
                closed.append(close_order)
                del state.open_positions[pos_id]
        return closed

    def maybe_trade(self, state: TradingState, exchange: ExchangeClient, signal: float, quote: PriceQuote, size: float) -> Position | None:
        if abs(signal) < 0.5:
            return None
        side = "buy" if signal > 0 else "sell"
        position = self.open_position(exchange, quote, size=size, side=side)
        state.open_positions[position.id] = position
        return position
