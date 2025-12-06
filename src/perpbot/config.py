from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Dict, List

from perpbot.models import AlertCondition, ExchangeCost

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT"]


@dataclass
class BotConfig:
    symbols: List[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    position_size: float = 0.01
    profit_target_pct: float = 0.01
    arbitrage_edge: float = 0.003
    arbitrage_min_profit_pct: float = 0.001
    arbitrage_trade_size: float = 0.01
    failure_probability: float = 0.05
    max_risk_pct: float = 0.05
    risk_cooldown_seconds: int = 30
    assumed_equity: float = 10_000.0
    max_drawdown_pct: float = 0.1
    max_consecutive_failures: int = 3
    max_symbol_exposure_pct: float = 0.2
    enforce_direction_consistency: bool = True
    freeze_threshold_pct: float = 0.005
    freeze_window_seconds: int = 1
    daily_loss_limit_pct: float = 0.08
    loop_interval_seconds: float = 2.0
    default_maker_fee_bps: float = 2.0
    default_taker_fee_bps: float = 5.0
    default_slippage_bps: float = 1.0
    retry_cost_bps: float = 0.5
    exchange_costs: Dict[str, ExchangeCost] = field(default_factory=dict)
    alerts: List[AlertCondition] = field(default_factory=list)
    volatility_window_minutes: int = 5
    volatility_high_threshold_pct: float = 0.03
    high_vol_min_profit_pct: float = 0.002
    low_vol_min_profit_pct: float = 0.005
    priority_score_threshold: float = 70.0
    priority_weights: Dict[str, float] = field(
        default_factory=lambda: {"profit_pct": 0.4, "profit_abs": 0.3, "liquidity": 0.2, "reliability": 0.1}
    )
    reliability_scores: Dict[str, float] = field(default_factory=dict)
    max_slippage_bps: float = 50.0
    order_fill_timeout_seconds: int = 5
    circuit_breaker_failures: int = 3
    balance_concentration_pct: float = 0.5
    per_exchange_limit: int = 2
    trade_record_path: str = "data/trades.csv"


def load_config(path: str) -> BotConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    alerts = [AlertCondition(**a) for a in data.get("alerts", [])]
    exchange_costs = {
        name: ExchangeCost(**cfg)
        for name, cfg in (data.get("exchange_costs", {}) or {}).items()
    }
    return BotConfig(
        symbols=data.get("symbols", DEFAULT_SYMBOLS),
        position_size=data.get("position_size", 0.01),
        profit_target_pct=data.get("profit_target_pct", 0.01),
        arbitrage_edge=data.get("arbitrage_edge", 0.003),
        arbitrage_min_profit_pct=data.get("arbitrage_min_profit_pct", 0.001),
        arbitrage_trade_size=data.get("arbitrage_trade_size", data.get("position_size", 0.01)),
        failure_probability=data.get("failure_probability", 0.05),
        max_risk_pct=data.get("max_risk_pct", 0.05),
        risk_cooldown_seconds=data.get("risk_cooldown_seconds", 30),
        assumed_equity=data.get("assumed_equity", 10_000.0),
        max_drawdown_pct=data.get("max_drawdown_pct", 0.1),
        max_consecutive_failures=data.get("max_consecutive_failures", 3),
        max_symbol_exposure_pct=data.get("max_symbol_exposure_pct", 0.2),
        enforce_direction_consistency=data.get("enforce_direction_consistency", True),
        freeze_threshold_pct=data.get("freeze_threshold_pct", 0.005),
        freeze_window_seconds=data.get("freeze_window_seconds", 1),
        daily_loss_limit_pct=data.get("daily_loss_limit_pct", 0.08),
        loop_interval_seconds=data.get("loop_interval_seconds", 2.0),
        default_maker_fee_bps=data.get("default_maker_fee_bps", 2.0),
        default_taker_fee_bps=data.get("default_taker_fee_bps", 5.0),
        default_slippage_bps=data.get("default_slippage_bps", 1.0),
        retry_cost_bps=data.get("retry_cost_bps", 0.5),
        exchange_costs=exchange_costs,
        alerts=alerts,
        volatility_window_minutes=data.get("volatility_window_minutes", 5),
        volatility_high_threshold_pct=data.get("volatility_high_threshold_pct", 0.03),
        high_vol_min_profit_pct=data.get("high_vol_min_profit_pct", 0.002),
        low_vol_min_profit_pct=data.get("low_vol_min_profit_pct", 0.005),
        priority_score_threshold=data.get("priority_score_threshold", 70.0),
        priority_weights=data.get(
            "priority_weights", {"profit_pct": 0.4, "profit_abs": 0.3, "liquidity": 0.2, "reliability": 0.1}
        ),
        reliability_scores=data.get("reliability_scores", {}),
        max_slippage_bps=data.get("max_slippage_bps", 50.0),
        order_fill_timeout_seconds=data.get("order_fill_timeout_seconds", 5),
        circuit_breaker_failures=data.get("circuit_breaker_failures", 3),
        balance_concentration_pct=data.get("balance_concentration_pct", 0.5),
        per_exchange_limit=data.get("per_exchange_limit", 2),
        trade_record_path=data.get("trade_record_path", "data/trades.csv"),
    )
