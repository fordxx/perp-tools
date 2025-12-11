from __future__ import annotations

from itertools import permutations
from typing import Iterable, List

from perpbot.arbitrage.profit import ProfitContext, calculate_real_profit, resolve_exchange_cost
from perpbot.arbitrage.volatility import SpreadVolatilityTracker
from perpbot.models import ArbitrageOpportunity, ExchangeCost, PriceQuote

# 所有支持的 DEX 交易所
ALL_DEX_EXCHANGES = ["paradex", "extended", "lighter", "edgex", "backpack", "grvt", "aster"]

# 生成所有 DEX 配对组合（双向）
DEX_ONLY_PAIRS = set()
for i, ex1 in enumerate(ALL_DEX_EXCHANGES):
    for ex2 in ALL_DEX_EXCHANGES[i + 1:]:
        DEX_ONLY_PAIRS.add((ex1, ex2))
        DEX_ONLY_PAIRS.add((ex2, ex1))

# 优先级配对（延迟较低、流动性较好的交易所组合）
PRIORITY_PAIRS = {
    ("paradex", "extended"),  # 同为 Starknet
    ("extended", "paradex"),
    ("lighter", "grvt"),      # 同为 ZK-rollup
    ("grvt", "lighter"),
    ("backpack", "aster"),    # 相似 API 风格
    ("aster", "backpack"),
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
    volatility_tracker: SpreadVolatilityTracker | None = None,
    high_vol_min_profit_pct: float = 0.002,
    low_vol_min_profit_pct: float = 0.005,
    volatility_high_threshold: float = 0.03,
    priority_threshold: float = 70.0,
    priority_weights: dict | None = None,
    reliability_scores: dict[str, float] | None = None,
) -> List[ArbitrageOpportunity]:
    """
    Discover executable arbitrage signals across exchanges using各交易所自己的深度盘口，
    不依赖中心化交易所锚定价，全部计算基于实时可成交价格与成本模型。
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

            spread_pct = (sell_price - buy_price) / buy_price if buy_price else 0
            if volatility_tracker:
                volatility_tracker.record(symbol, spread_pct)
                dynamic_min_profit = volatility_tracker.dynamic_min_profit(
                    symbol,
                    low_vol_min=low_vol_min_profit_pct,
                    high_vol_min=high_vol_min_profit_pct,
                    high_vol_threshold=volatility_high_threshold,
                )
            else:
                dynamic_min_profit = min_profit_pct

            success_prob = max(0.0, min(1.0, 1 - failure_probability))
            liquidity_score = 0.0
            if buy.order_book and sell.order_book:
                buy_liq = buy.order_book.fill_ratio("buy", trade_size)
                sell_liq = sell.order_book.fill_ratio("sell", trade_size)
                liquidity_score = min(buy_liq, sell_liq) * 100
            reliability_map = reliability_scores or {}
            reliability = (
                reliability_map.get(buy.exchange, 100.0) + reliability_map.get(sell.exchange, 100.0)
            ) / 2

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
                liquidity_score=liquidity_score,
                reliability_score=reliability,
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
            priority = candidate.priority_score(weights=priority_weights)

            if (
                profit.net_profit_abs > 0
                and profit.net_profit_pct >= dynamic_min_profit
                and profit.net_profit_abs >= min_profit_abs
                and priority >= priority_threshold
            ):
                opportunities.append(candidate)
    return opportunities
