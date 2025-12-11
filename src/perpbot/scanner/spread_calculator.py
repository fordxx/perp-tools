from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class SpreadResult:
    bid_exchange: str
    ask_exchange: str
    bid: float
    ask: float
    spread_bps: float
    symbol: str


class SpreadCalculator:
    @staticmethod
    def compute_spread(
        symbol: str,
        bid_exchange: str,
        ask_exchange: str,
        bid: float,
        ask: float
    ) -> Optional[SpreadResult]:
        """
        计算跨所套利价差：spread_bps = (bid - ask) / mid * 10000
        bid <= ask 时返回 None
        """
        if bid <= ask:
            return None

        mid = (bid + ask) / 2
        if mid <= 0:
            return None

        spread_bps = ((bid - ask) / mid) * 10000
        return SpreadResult(
            bid_exchange=bid_exchange,
            ask_exchange=ask_exchange,
            bid=bid,
            ask=ask,
            spread_bps=spread_bps,
            symbol=symbol,
        )
