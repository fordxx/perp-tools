from __future__ import annotations

from typing import Iterable, List

from perpbot.models import ArbitrageOpportunity, PriceQuote


def find_arbitrage_opportunities(quotes: Iterable[PriceQuote], min_edge: float = 0.002) -> List[ArbitrageOpportunity]:
    grouped = {}
    for quote in quotes:
        grouped.setdefault(quote.symbol, []).append(quote)

    opportunities: List[ArbitrageOpportunity] = []
    for symbol, sym_quotes in grouped.items():
        if len(sym_quotes) < 2:
            continue
        sorted_quotes = sorted(sym_quotes, key=lambda q: q.mid)
        buy = sorted_quotes[0]
        sell = sorted_quotes[-1]
        edge = (sell.mid - buy.mid) / buy.mid
        if edge >= min_edge:
            opportunities.append(
                ArbitrageOpportunity(
                    symbol=symbol,
                    buy_exchange=buy.exchange,
                    sell_exchange=sell.exchange,
                    buy_price=buy.mid,
                    sell_price=sell.mid,
                    edge=edge,
                )
            )
    return opportunities
