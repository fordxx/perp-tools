# src/perpbot/incentives/apex.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class ApexIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API client for ApeX Pro.
        # - Check for a public API endpoint for trading rewards/incentives.
        # - The "Trade-to-Earn" program provides APEX token rewards.
        # - APR calculation will be complex, based on trading activity and epoch rewards.
        # - Volume and fee data need to be fetched from their API.

        mock_data = [
            IncentiveSnapshot(
                exchange="apex",
                symbol="ETH-USDC",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0003,
                volume_24h=150_000_000.0,
                volume_30d=4_500_000_000.0,
                incentive_apr=0.15,  # Estimated APR from Trade-to-Earn
                incentive_token="APEX",
                incentive_end_ts=int(time.time()) + 86400 * 30, # Mock end date
            ),
        ]
        return mock_data
