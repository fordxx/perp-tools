# src/perpbot/incentives/lighter.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class LighterIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for Lighter.
        # - Focus on their maker rebate structure.
        # - This is a primary source of yield for market-making strategies.
        # - Fetch details on the LIGHT token incentives if they exist.

        mock_data = [
            IncentiveSnapshot(
                exchange="lighter",
                symbol="ETH-USDC",
                maker_rebate_pct=0.0003, # High maker rebate
                taker_fee_pct=0.0005,
                volume_24h=40_000_000.0,
                volume_30d=1_200_000_000.0,
                incentive_apr=0.05, # Lower APR, focus is on rebate
                incentive_token="LIGHT",
                incentive_end_ts=int(time.time()) + 86400 * 90,
            ),
        ]
        return mock_data
