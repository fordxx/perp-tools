# src/perpbot/incentives/binance.py
from typing import List
import time

from .base import IncentiveFetcher
from .models import IncentiveSnapshot

class BinanceIncentiveFetcher(IncentiveFetcher):
    def fetch(self) -> List[IncentiveSnapshot]:
        # TODO: Implement API client to fetch real-time data from Binance API.
        # - Fetch taker/maker fees from /api/v3/account
        # - Fetch 24h volume from /api/v3/ticker/24hr
        # - 30d volume needs to be aggregated or estimated.
        # - Binance has no direct incentive APR for spot/futures trading, focus on fees.

        mock_data = [
            IncentiveSnapshot(
                exchange="binance",
                symbol="BTC-USDT",
                maker_rebate_pct=0.0001,  # Tiered, this is an approximation
                taker_fee_pct=0.0002,   # Tiered, this is an approximation
                volume_24h=5_000_000_000.0,
                volume_30d=150_000_000_000.0,
                incentive_apr=None,
                incentive_token=None,
                incentive_end_ts=None,
            ),
            IncentiveSnapshot(
                exchange="binance",
                symbol="ETH-USDT",
                maker_rebate_pct=0.0001,
                taker_fee_pct=0.0002,
                volume_24h=3_000_000_000.0,
                volume_30d=90_000_000_000.0,
                incentive_apr=None,
                incentive_token=None,
                incentive_end_ts=None,
            ),
        ]
        return mock_data
