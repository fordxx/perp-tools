# src/perpbot/incentives/dydx.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class DydxIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for dYdX v4 on Cosmos.
        # - dYdX has a well-established trading rewards program.
        # - Fetch rewards data from the Cosmos chain or dYdX indexer.
        # - Volume is consistently high.

        mock_data = [
            IncentiveSnapshot(
                exchange="dydx",
                symbol="BTC-USD",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0005,
                volume_24h=900_000_000.0,
                volume_30d=27_000_000_000.0,
                incentive_apr=0.12, # Stable, medium incentive level
                incentive_token="DYDX",
                incentive_end_ts=int(time.time()) + 86400 * 28, # Epoch-based
            ),
            IncentiveSnapshot(
                exchange="dydx",
                symbol="ETH-USD",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0005,
                volume_24h=700_000_000.0,
                volume_30d=21_000_000_000.0,
                incentive_apr=0.12,
                incentive_token="DYDX",
                incentive_end_ts=int(time.time()) + 86400 * 28,
            ),
        ]
        return mock_data
