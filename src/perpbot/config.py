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
        alerts=alerts,
    )
