# src/perpbot/incentives/sunx.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class SunxIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for SUNX (Sun Wukong).
        # - Early stage exchange, expect high incentives and very low volume.
        # - This is a high-risk, high-reward scenario.
        # - Find API for rewards program.

        mock_data = [
            IncentiveSnapshot(
                exchange="sunx",
                symbol="BTC-USDT",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0010,
                volume_24h=1_000_000.0, # Very low
                volume_30d=30_000_000.0,
                incentive_apr=1.20,  # Extremely high initial APR
                incentive_token="SUNX",
                incentive_end_ts=int(time.time()) + 86400 * 10,
            ),
        ]
        return mock_data
