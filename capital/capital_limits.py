from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class StrategyCapitalLimit:
    name: str
    max_notional_per_order: float
    max_open_notional: Optional[float] = None


@dataclass
class ExchangeCapitalLimit:
    name: str
    max_equity_usage_pct: float
    max_open_notional_pct: float


@dataclass
class CapitalLimitConfig:
    strategy_limits: Dict[str, StrategyCapitalLimit] = field(default_factory=dict)
    exchange_limits: Dict[str, ExchangeCapitalLimit] = field(default_factory=dict)

    def get_strategy_limit(self, strategy: str) -> Optional[StrategyCapitalLimit]:
        return self.strategy_limits.get(strategy)

    def get_exchange_limit(self, exchange: str) -> Optional[ExchangeCapitalLimit]:
        return self.exchange_limits.get(exchange)
