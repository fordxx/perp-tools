from __future__ import annotations

from itertools import permutations
from typing import Iterable, List

from perpbot.models import ArbitrageOpportunity, PriceQuote

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


def _fee_bps(quote: PriceQuote, default_maker_fee_bps: float, default_taker_fee_bps: float) -> tuple[float, float]:
    maker = quote.maker_fee_bps if quote.maker_fee_bps is not None else default_maker_fee_bps
    taker = quote.taker_fee_bps if quote.taker_fee_bps is not None else default_taker_fee_bps
    return maker, taker


def find_arbitrage_opportunities(
    quotes: Iterable[PriceQuote],
    trade_size: float,
    min_profit_pct: float = 0.001,
    default_maker_fee_bps: float = 2.0,
    default_taker_fee_bps: float = 5.0,
    default_slippage_bps: float = 1.0,
    retry_cost_bps: float = 0.5,
    failure_probability: float = 0.05,
) -> List[ArbitrageOpportunity]:
    """
    Discover executable arbitrage signals across exchanges using depth-aware prices
    and a conservative cost model.
    """

    grouped: dict[str, List[PriceQuote]] = {}
    for quote in quotes:
        grouped.setdefault(quote.symbol, []).append(quote)

    opportunities: List[ArbitrageOpportunity] = []
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

            _, buy_taker_fee = _fee_bps(buy, default_maker_fee_bps, default_taker_fee_bps)
            _, sell_taker_fee = _fee_bps(sell, default_maker_fee_bps, default_taker_fee_bps)

            gross_pnl = (sell_price - buy_price) * trade_size
            fee_cost = trade_size * (
                buy_price * (buy_taker_fee / 10_000) + sell_price * (sell_taker_fee / 10_000)
            )
            funding_cost = trade_size * (
                buy_price * (buy.funding_rate or 0.0) + sell_price * (sell.funding_rate or 0.0)
            )
            retry_cost = trade_size * (
                buy_price * (retry_cost_bps / 10_000) + sell_price * (retry_cost_bps / 10_000)
            )

            net_pnl = gross_pnl - fee_cost - funding_cost - retry_cost
            success_prob = max(0.0, min(1.0, 1 - failure_probability))
            expected_pnl = net_pnl * success_prob
            net_profit_pct = expected_pnl / (buy_price * trade_size)

            if expected_pnl > 0 and net_profit_pct >= min_profit_pct:
                opportunities.append(
                    ArbitrageOpportunity(
                        symbol=symbol,
                        buy_exchange=buy.exchange,
                        sell_exchange=sell.exchange,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        size=trade_size,
                        expected_pnl=expected_pnl,
                        net_profit_pct=net_profit_pct,
                        confidence=success_prob,
                    )
                )
    return opportunities
