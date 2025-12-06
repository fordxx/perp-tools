from __future__ import annotations

from itertools import permutations
from typing import Iterable, List

from perpbot.arbitrage.profit import ProfitContext, calculate_real_profit, resolve_exchange_cost
from perpbot.models import ArbitrageOpportunity, ExchangeCost, PriceQuote

DEX_ONLY_PAIRS = {
    ("edgex", "paradex"),
    ("paradex", "edgex"),
    ("backpack", "aster"),
    ("aster", "backpack"),
    ("grvt", "extended"),
    ("extended", "grvt"),
}


def _effective_price(quote: PriceQuote, side: str, size: float, slippage_bps: float) -> float | None:
    return quote.executable_price(side, size, default_slippage_bps=slippage_bps)


def find_arbitrage_opportunities(
    quotes: Iterable[PriceQuote],
    trade_size: float,
    min_profit_pct: float = 0.001,
    default_maker_fee_bps: float = 2.0,
    default_taker_fee_bps: float = 5.0,
    default_slippage_bps: float = 1.0,
    failure_probability: float = 0.05,
    exchange_costs: dict[str, ExchangeCost] | None = None,
    min_profit_abs: float = 0.0,
) -> List[ArbitrageOpportunity]:
    """
    Discover executable arbitrage signals across exchanges using depth-aware prices
    and a conservative cost model.
    """

    grouped: dict[str, List[PriceQuote]] = {}
    for quote in quotes:
        grouped.setdefault(quote.symbol, []).append(quote)

    opportunities: List[ArbitrageOpportunity] = []
    default_cost = ExchangeCost(
        maker_fee_bps=default_maker_fee_bps,
        taker_fee_bps=default_taker_fee_bps,
        funding_rate=0.0,
    )
    cost_map = exchange_costs or {}
    for symbol, sym_quotes in grouped.items():
        dex_quotes = [q for q in sym_quotes if q.venue_type == "dex"]
        if len(dex_quotes) < 2:
            continue

        for buy, sell in permutations(dex_quotes, 2):
            if buy.exchange == sell.exchange:
                continue
            if (buy.exchange, sell.exchange) not in DEX_ONLY_PAIRS:
                continue

            buy_price = _effective_price(buy, "buy", trade_size, default_slippage_bps)
            sell_price = _effective_price(sell, "sell", trade_size, default_slippage_bps)
            if buy_price is None or sell_price is None:
                continue

            success_prob = max(0.0, min(1.0, 1 - failure_probability))
            candidate = ArbitrageOpportunity(
                symbol=symbol,
                buy_exchange=buy.exchange,
                sell_exchange=sell.exchange,
                buy_price=buy_price,
                sell_price=sell_price,
                size=trade_size,
                expected_pnl=0.0,
                net_profit_pct=0.0,
                confidence=success_prob,
            )

            buy_cost = resolve_exchange_cost(buy.exchange, cost_map, default_cost)
            sell_cost = resolve_exchange_cost(sell.exchange, cost_map, default_cost)
            ctx = ProfitContext(
                buy_cost=buy_cost,
                sell_cost=sell_cost,
                failure_probability=failure_probability,
            )
            profit = calculate_real_profit(candidate, buy_price * trade_size, ctx)
            candidate.expected_pnl = profit.net_profit_abs
            candidate.net_profit_pct = profit.net_profit_pct
            candidate.profit = profit

            if profit.net_profit_abs > 0 and profit.net_profit_pct >= min_profit_pct and profit.net_profit_abs >= min_profit_abs:
                opportunities.append(candidate)
    return opportunities
