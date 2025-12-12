# src/perpbot/incentives/bitget.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class BitgetIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API client to fetch real-time data from Bitget API.
        # - Fetch fee rates from their API (check documentation for endpoint).
        # - Fetch 24h volume from ticker endpoints.
        # - 30d volume must be aggregated.
        # - Bitget sometimes has promotions, but no standard APR.

        mock_data = [
            IncentiveSnapshot(
                exchange="bitget",
                symbol="BTC-USDT",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0004,
                volume_24h=2_000_000_000.0,
                volume_30d=60_000_000_000.0,
                incentive_apr=None,
                incentive_token=None,
                incentive_end_ts=None,
            ),
        ]
        return mock_data
