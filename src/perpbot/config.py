from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import List

from perpbot.models import AlertCondition

DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT"]


@dataclass
class BotConfig:
    symbols: List[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    position_size: float = 0.01
    profit_target_pct: float = 0.01
    arbitrage_edge: float = 0.003
    arbitrage_min_profit_pct: float = 0.0005
    arbitrage_trade_size: float = 0.01
    max_risk_pct: float = 0.05
    risk_cooldown_seconds: int = 30
    assumed_equity: float = 10_000.0
    max_drawdown_pct: float = 0.1
    max_consecutive_failures: int = 3
    max_symbol_exposure_pct: float = 0.2
    enforce_direction_consistency: bool = True
    freeze_threshold_pct: float = 0.02
    freeze_window_seconds: int = 1
    loop_interval_seconds: float = 2.0
    default_maker_fee_bps: float = 2.0
    default_taker_fee_bps: float = 5.0
    default_slippage_bps: float = 1.0
    retry_cost_bps: float = 0.5
    alerts: List[AlertCondition] = field(default_factory=list)


def load_config(path: str) -> BotConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    alerts = [AlertCondition(**a) for a in data.get("alerts", [])]
    return BotConfig(
        symbols=data.get("symbols", DEFAULT_SYMBOLS),
        position_size=data.get("position_size", 0.01),
        profit_target_pct=data.get("profit_target_pct", 0.01),
        arbitrage_edge=data.get("arbitrage_edge", 0.003),
        arbitrage_min_profit_pct=data.get("arbitrage_min_profit_pct", 0.0005),
        arbitrage_trade_size=data.get("arbitrage_trade_size", data.get("position_size", 0.01)),
        max_risk_pct=data.get("max_risk_pct", 0.05),
        risk_cooldown_seconds=data.get("risk_cooldown_seconds", 30),
        assumed_equity=data.get("assumed_equity", 10_000.0),
        max_drawdown_pct=data.get("max_drawdown_pct", 0.1),
        max_consecutive_failures=data.get("max_consecutive_failures", 3),
        max_symbol_exposure_pct=data.get("max_symbol_exposure_pct", 0.2),
        enforce_direction_consistency=data.get("enforce_direction_consistency", True),
        freeze_threshold_pct=data.get("freeze_threshold_pct", 0.02),
        freeze_window_seconds=data.get("freeze_window_seconds", 1),
        loop_interval_seconds=data.get("loop_interval_seconds", 2.0),
        default_maker_fee_bps=data.get("default_maker_fee_bps", 2.0),
        default_taker_fee_bps=data.get("default_taker_fee_bps", 5.0),
        default_slippage_bps=data.get("default_slippage_bps", 1.0),
        retry_cost_bps=data.get("retry_cost_bps", 0.5),
        alerts=alerts,
    )
