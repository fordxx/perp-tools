"""Execution cost and profit estimation utilities.

This module encapsulates pure calculation helpers for execution-related
profits and costs in a dual-exchange hedging or wash-volume workflow.
Each function accepts only ``float`` inputs so it can be easily unit
tested without relying on external SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass
class ExecutionBreakdown:
    """Structured execution profit and cost breakdown.

    Attributes:
        spread_profit: Profit captured from entry/exit spread differences.
        funding_profit: Net funding paid/received over the holding window.
        wash_volume_reward: Rebates or incentives from wash volume activity.
        trading_fee_cost: Fees paid for maker/taker execution.
        slippage_cost: Cost from price impact or slip versus mid.
        latency_cost: Expected loss attributed to latency-induced drift.
        net_profit: Sum of all components.
        net_profit_pct: Profit relative to the provided notional ("return").
    """

    spread_profit: float
    funding_profit: float
    wash_volume_reward: float
    trading_fee_cost: float
    slippage_cost: float
    latency_cost: float
    net_profit: float
    net_profit_pct: float

    def to_dict(self) -> Dict[str, float]:
        """Return the breakdown as a dict for logging or serialization."""

        return {
            "spread_profit": self.spread_profit,
            "funding_profit": self.funding_profit,
            "wash_volume_reward": self.wash_volume_reward,
            "trading_fee_cost": self.trading_fee_cost,
            "slippage_cost": self.slippage_cost,
            "latency_cost": self.latency_cost,
            "net_profit": self.net_profit,
            "net_profit_pct": self.net_profit_pct,
        }


class ExecutionCostEngine:
    """Pure math helpers for execution profit/cost estimation."""

    @staticmethod
    def calc_funding_profit(
        long_notional: float,
        short_notional: float,
        long_funding_rate: float,
        short_funding_rate: float,
        holding_hours: float,
        settlement_cycle_hours: float = 8.0,
    ) -> float:
        """Calculate net funding profit over a holding window.

        Formula: ``(long_notional * long_funding_rate - short_notional * short_funding_rate)
        * holding_hours / settlement_cycle_hours``
        """

        effective_ratio = holding_hours / settlement_cycle_hours
        return (long_notional * long_funding_rate - short_notional * short_funding_rate) * effective_ratio

    @staticmethod
    def calc_spread_profit(
        base_qty: float,
        entry_long_price: float,
        entry_short_price: float,
        exit_long_price: float,
        exit_short_price: float,
    ) -> float:
        """Calculate profit from entry/exit spread with symmetric position sizes.

        Long PnL = -(exit_long_price - entry_long_price) * base_qty
        Short PnL = (entry_short_price - exit_short_price) * base_qty
        Spread profit = Long PnL + Short PnL
        """

        long_pnl = -(exit_long_price - entry_long_price) * base_qty
        short_pnl = (entry_short_price - exit_short_price) * base_qty
        return long_pnl + short_pnl

    @staticmethod
    def calc_wash_volume_reward(
        notional: float, maker_rebate_rate: float, taker_rebate_rate: float
    ) -> float:
        """Calculate rebates from wash volume incentives.

        Formula: ``notional * (maker_rebate_rate + taker_rebate_rate)``
        """

        return notional * (maker_rebate_rate + taker_rebate_rate)

    @staticmethod
    def calc_trading_fee_cost(
        notional: float, maker_fee_rate: float, taker_fee_rate: float
    ) -> float:
        """Calculate total trading fee cost.

        Formula: ``notional * (maker_fee_rate + taker_fee_rate)``
        """

        return notional * (maker_fee_rate + taker_fee_rate)

    @staticmethod
    def calc_slippage_cost(
        notional: float, long_slippage_bps: float, short_slippage_bps: float
    ) -> float:
        """Calculate cost from slippage.

        Formula: ``notional * (long_slippage_bps + short_slippage_bps) / 10_000``
        """

        return notional * (long_slippage_bps + short_slippage_bps) / 10_000

    @staticmethod
    def calc_latency_cost(
        notional: float, latency_ms: float, drift_cost_rate_per_ms: float
    ) -> float:
        """Estimate cost due to latency-induced price drift.

        Formula: ``notional * latency_ms * drift_cost_rate_per_ms``
        """

        return notional * latency_ms * drift_cost_rate_per_ms

    @staticmethod
    def calc_total_execution_profit(
        notional: float,
        base_qty: float,
        entry_long_price: float,
        entry_short_price: float,
        exit_long_price: float,
        exit_short_price: float,
        long_notional: float,
        short_notional: float,
        long_funding_rate: float,
        short_funding_rate: float,
        holding_hours: float,
        maker_fee_rate: float,
        taker_fee_rate: float,
        maker_rebate_rate: float,
        taker_rebate_rate: float,
        long_slippage_bps: float,
        short_slippage_bps: float,
        latency_ms: float,
        drift_cost_rate_per_ms: float,
        settlement_cycle_hours: float = 8.0,
    ) -> Dict[str, float]:
        """Aggregate all execution components into a structured breakdown.

        Returns:
            A dict containing each component and the resulting net profit and
            net profit percentage relative to the provided notional.
        """

        spread_profit = ExecutionCostEngine.calc_spread_profit(
            base_qty, entry_long_price, entry_short_price, exit_long_price, exit_short_price
        )
        funding_profit = ExecutionCostEngine.calc_funding_profit(
            long_notional,
            short_notional,
            long_funding_rate,
            short_funding_rate,
            holding_hours,
            settlement_cycle_hours,
        )
        wash_volume_reward = ExecutionCostEngine.calc_wash_volume_reward(
            notional, maker_rebate_rate, taker_rebate_rate
        )
        trading_fee_cost = ExecutionCostEngine.calc_trading_fee_cost(
            notional, maker_fee_rate, taker_fee_rate
        )
        slippage_cost = ExecutionCostEngine.calc_slippage_cost(
            notional, long_slippage_bps, short_slippage_bps
        )
        latency_cost = ExecutionCostEngine.calc_latency_cost(
            notional, latency_ms, drift_cost_rate_per_ms
        )

        net_profit = (
            spread_profit
            + funding_profit
            + wash_volume_reward
            - trading_fee_cost
            - slippage_cost
            - latency_cost
        )
        net_profit_pct = net_profit / notional if notional else 0.0

        return ExecutionBreakdown(
            spread_profit=spread_profit,
            funding_profit=funding_profit,
            wash_volume_reward=wash_volume_reward,
            trading_fee_cost=trading_fee_cost,
            slippage_cost=slippage_cost,
            latency_cost=latency_cost,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
        ).to_dict()
