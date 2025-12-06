from __future__ import annotations

from typing import Iterable, List

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import AlertCondition, OrderRequest, TradingState


def process_alerts(state: TradingState, alerts: Iterable[AlertCondition], exchanges: Iterable[ExchangeClient]) -> List[str]:
    messages: List[str] = []
    for alert in alerts:
        quote = next((q for q in state.quotes.values() if q.symbol == alert.symbol), None)
        if not quote:
            continue
        price = quote.mid
        if alert.direction == "above" and price < alert.price:
            continue
        if alert.direction == "below" and price > alert.price:
            continue
        messages.append(f"Alert: {alert.symbol} {alert.direction} {alert.price} (now {price:.2f})")
        if alert.action == "auto-order" and alert.side and alert.size > 0:
            exchange = next((ex for ex in exchanges if ex.name == quote.exchange), None)
            if exchange:
                exchange.place_order(
                    OrderRequest(symbol=alert.symbol, side=alert.side, size=alert.size, limit_price=quote.mid)
                )
    state.triggered_alerts.extend(messages)
    return messages
