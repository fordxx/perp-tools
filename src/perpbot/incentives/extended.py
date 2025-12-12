# src/perpbot/incentives/extended.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class ExtendedIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API/subgraph client for Extended Finance on Starknet.
        # - Need to query Starknet for contract data or use a subgraph.
        # - Look for liquidity mining or trading reward contracts.
        # - EXT token rewards are likely.

        mock_data = [
            IncentiveSnapshot(
                exchange="extended",
                symbol="ETH-USDC",
                maker_rebate_pct=0.0000,
                taker_fee_pct=0.0005,
                volume_24h=25_000_000.0,
                volume_30d=750_000_000.0,
                incentive_apr=0.20,
                incentive_token="EXT",
                incentive_end_ts=int(time.time()) + 86400 * 20,
            ),
        ]
        return mock_data
