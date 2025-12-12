from typing import Optional

from .scanner_config import ScannerConfig
from .spread_calculator import SpreadCalculator, SpreadResult


class PairScanner:
    def __init__(self, config: ScannerConfig):
        self.config = config

    def scan(
        self,
        symbol: str,
        bbo_a: tuple,
        bbo_b: tuple,
        latency_a: float,
        latency_b: float,
        quality_a: float,
        quality_b: float,
        exchange_a: str,
        exchange_b: str,
    ) -> Optional[SpreadResult]:
        """
        bbo_x = (bid, ask)
        检查两方向套利：
        - buy A → sell B
        - buy B → sell A
        满足条件返回 SpreadResult，否则 None。
        """
        bid_a, ask_a = bbo_a
        bid_b, ask_b = bbo_b

        if latency_a > self.config.max_latency_ms or latency_b > self.config.max_latency_ms:
            return None

        if quality_a > self.config.max_quality_penalty or quality_b > self.config.max_quality_penalty:
            return None

        result_ab = SpreadCalculator.compute_spread(symbol, exchange_b, exchange_a, bid_b, ask_a)
        if result_ab and result_ab.spread_bps >= self.config.min_spread_bps:
            return result_ab

        result_ba = SpreadCalculator.compute_spread(symbol, exchange_a, exchange_b, bid_a, ask_b)
        if result_ba and result_ba.spread_bps >= self.config.min_spread_bps:
            return result_ba

        return None
