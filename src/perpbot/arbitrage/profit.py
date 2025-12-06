from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, Iterable

from perpbot.models import ArbitrageOpportunity, ExchangeCost, ProfitResult


@dataclass
class ProfitContext:
    """在计算套利机会时统一提供成本查询的辅助容器。"""

    buy_cost: ExchangeCost
    sell_cost: ExchangeCost
    failure_probability: float = 0.0


def estimate_slippage_pct(notional_usd: float) -> float:
    """按名义金额给出保守的滑点估计。

    采用偏保守的区间以避免高估成交质量，并对每条腿分别应用；大额订单直接取区间上限，鼓励拆单执行。
    """

    if notional_usd < 1000:
        return 0.001  # 0.1%
    if notional_usd <= 5000:
        return 0.002  # 0.2%
    return 0.005  # 0.5%


def chunk_order_sizes(total_size: float, price: float, max_notional: float = 5000) -> Iterable[float]:
    """将大额订单按名义金额上限拆成多笔。"""

    if price <= 0:
        return [total_size]

    max_size = max_notional / price
    if total_size * price <= max_notional or max_size <= 0:
        return [total_size]

    parts = ceil(total_size / max_size)
    base = total_size / parts
    return [base for _ in range(parts - 1)] + [total_size - base * (parts - 1)]


def calculate_real_profit(
    opportunity: ArbitrageOpportunity,
    amount: float,
    ctx: ProfitContext,
) -> ProfitResult:
    """综合手续费、滑点、资金费率与失败概率计算净利润。"""

    gross_spread_pct = (opportunity.sell_price - opportunity.buy_price) / opportunity.buy_price
    fees_pct = (ctx.buy_cost.taker_fee_bps + ctx.sell_cost.taker_fee_bps) / 10_000
    funding_cost_pct = (ctx.buy_cost.funding_rate or 0.0) + (ctx.sell_cost.funding_rate or 0.0)
    per_leg_slip = estimate_slippage_pct(amount)
    slippage_pct = per_leg_slip * 2

    net_profit_pct = (gross_spread_pct - fees_pct - funding_cost_pct - slippage_pct) * (
        1 - ctx.failure_probability
    )
    net_profit_abs = amount * net_profit_pct

    return ProfitResult(
        gross_spread_pct=gross_spread_pct,
        fees_pct=fees_pct,
        slippage_pct=slippage_pct,
        funding_cost_pct=funding_cost_pct,
        net_profit_pct=net_profit_pct,
        net_profit_abs=net_profit_abs,
    )


def resolve_exchange_cost(exchange: str, costs: Dict[str, ExchangeCost], default: ExchangeCost) -> ExchangeCost:
    return costs.get(exchange, default)
