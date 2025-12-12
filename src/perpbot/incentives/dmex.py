# src/perpbot/incentives/dmex.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class DmexIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for DMEX.
        # - DMEX is known for high incentives on certain pairs.
        # - Fetch incentive program details to calculate APR.
        # - Volume is typically low, which is a risk factor.

        mock_data = [
            IncentiveSnapshot(
                exchange="dmex",
                symbol="BTC-USDC",
                maker_rebate_pct=0.0001,
                taker_fee_pct=0.0008,
                volume_24h=10_000_000.0,
                volume_30d=300_000_000.0,
                incentive_apr=0.35,  # Estimated high APR
                incentive_token="DMEX",
                incentive_end_ts=int(time.time()) + 86400 * 14, # Mock end date
            ),
        ]
        return mock_data
