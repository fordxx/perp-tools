# src/perpbot/incentives/grvt.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class GrvtIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API client for GRVT.
        # - GRVT has a points-based system to incentivize trading volume.
        # - This needs to be translated into a notional APR.
        # - Points might be based on fees paid or volume traded.

        mock_data = [
            IncentiveSnapshot(
                exchange="grvt",
                symbol="ETH-USDT",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0002,
                volume_24h=200_000_000.0, # High due to incentives
                volume_30d=6_000_000_000.0,
                incentive_apr=0.25,  # Estimated APR from points system
                incentive_token="GRVT",
                incentive_end_ts=int(time.time()) + 86400 * 60, # Mock end date
            ),
        ]
        return mock_data
