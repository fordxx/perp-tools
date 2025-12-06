from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Dict, Iterable

from perpbot.models import ArbitrageOpportunity, ExchangeCost, ProfitResult


@dataclass
class ProfitContext:
    """Helper container for cost lookups while pricing opportunities."""

    buy_cost: ExchangeCost
    sell_cost: ExchangeCost
    failure_probability: float = 0.0


def estimate_slippage_pct(notional_usd: float) -> float:
    """Return a conservative slippage estimate based on notional size.

    The ranges are pessimistic to avoid overestimating fill quality and are
    applied per leg. Larger notionals return the upper bound of the configured
    range to encourage order splitting.
    """

    if notional_usd < 1000:
        return 0.001  # 0.1%
    if notional_usd <= 5000:
        return 0.002  # 0.2%
    return 0.005  # 0.5%


def chunk_order_sizes(total_size: float, price: float, max_notional: float = 5000) -> Iterable[float]:
    """Split large orders into multiple tranches capped by notional value."""

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
    """Compute net profit with fees, slippage, funding, and failure probability."""

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
