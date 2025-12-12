# src/perpbot/incentives/models.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class IncentiveSnapshot:
    """
    A snapshot of a single market's fee and incentive structure.
    """
    exchange: str
    symbol: str

    maker_rebate_pct: float
    taker_fee_pct: float

    volume_24h: float
    volume_30d: float

    incentive_apr: Optional[float] = None
    incentive_token: Optional[str] = None
    incentive_end_ts: Optional[int] = None

    score: Optional[float] = None
