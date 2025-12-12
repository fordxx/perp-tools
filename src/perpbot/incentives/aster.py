# src/perpbot/incentives/aster.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class AsterIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for Aster.
        # - New platform, likely high incentives to attract liquidity.
        # - High APR is a key feature but also a risk if volume is low.
        # - Need to find their rewards contract or API endpoint.

        mock_data = [
            IncentiveSnapshot(
                exchange="aster",
                symbol="BTC-USDT",
                maker_rebate_pct=0.0001,
                taker_fee_pct=0.0010, # Higher fee typical for new DEXs
                volume_24h=5_000_000.0, # Low volume
                volume_30d=150_000_000.0,
                incentive_apr=0.85,  # High APR to bootstrap
                incentive_token="ASTER",
                incentive_end_ts=int(time.time()) + 86400 * 7, # Short-term program
            ),
        ]
        return mock_data
