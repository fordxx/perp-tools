# src/perpbot/incentives/backpack.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class BackpackIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API client for Backpack.
        # - Backpack has a points system ("droplets") and other events.
        # - Need to check how this translates to a yield/APR.
        # - Fees are generally competitive.

        mock_data = [
            IncentiveSnapshot(
                exchange="backpack",
                symbol="SOL-USDC",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.00025, # Friendly fees
                volume_24h=100_000_000.0,
                volume_30d=3_000_000_000.0,
                incentive_apr=0.10, # Moderate, points-based
                incentive_token="BPK", # Hypothetical token for points
                incentive_end_ts=None, # Ongoing program
            ),
        ]
        return mock_data
