# src/perpbot/incentives/hyperliquid.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class HyperliquidIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement on-chain data fetcher for Hyperliquid.
        # - Hyperliquid has a points program for their native token airdrop.
        # - Need to query their state on the L1 to get this data.
        # - Volume is very high, and rebates are strong for makers.

        mock_data = [
            IncentiveSnapshot(
                exchange="hyperliquid",
                symbol="BTC-USDC",
                maker_rebate_pct=0.0002, # Strong maker rebate
                taker_fee_pct=0.00025,
                volume_24h=1_000_000_000.0, # Very high volume
                volume_30d=30_000_000_000.0,
                incentive_apr=0.22, # Strong, points-based APR
                incentive_token="HYPE", # Hypothetical token for points
                incentive_end_ts=None, # Ongoing
            ),
             IncentiveSnapshot(
                exchange="hyperliquid",
                symbol="ETH-USDC",
                maker_rebate_pct=0.0002,
                taker_fee_pct=0.00025,
                volume_24h=800_000_000.0,
                volume_30d=24_000_000_000.0,
                incentive_apr=0.22,
                incentive_token="HYPE",
                incentive_end_ts=None,
            ),
        ]
        return mock_data
