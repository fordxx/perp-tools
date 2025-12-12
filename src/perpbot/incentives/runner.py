# src/perpbot/incentives/runner.py
from typing import List

from .models import IncentiveSnapshot
from .scoring import compute_incentive_score

# Import all fetcher implementations
from .binance import BinanceIncentiveFetcher
from .okx import OkxIncentiveFetcher
from .bitget import BitgetIncentiveFetcher
from .apex import ApexIncentiveFetcher
from .dmex import DmexIncentiveFetcher
from .grvt import GrvtIncentiveFetcher
from .extended import ExtendedIncentiveFetcher
from .aster import AsterIncentiveFetcher
from .sunx import SunxIncentiveFetcher
from .lighter import LighterIncentiveFetcher
from .backpack import BackpackIncentiveFetcher
from .hyperliquid import HyperliquidIncentiveFetcher
from .dydx import DydxIncentiveFetcher

def collect_incentives() -> List[IncentiveSnapshot]:
    """
    Collects and scores incentive data from all supported exchanges.

    This function serves as the main entry point for the incentives module.
    It instantiates and runs each exchange-specific fetcher, then computes
    a standardized score for each returned snapshot.

    It does not perform any I/O, logging, or printing. It is a pure
    data collection and processing function.

    Returns:
        A flat list of scored IncentiveSnapshot objects from all exchanges.
    """
    all_snapshots: List[IncentiveSnapshot] = []
    
    fetchers = [
        BinanceIncentiveFetcher(),
        OkxIncentiveFetcher(),
        BitgetIncentiveFetcher(),
        ApexIncentiveFetcher(),
        DmexIncentiveFetcher(),
        GrvtIncentiveFetcher(),
        ExtendedIncentiveFetcher(),
        AsterIncentiveFetcher(),
        SunxIncentiveFetcher(),
        LighterIncentiveFetcher(),
        BackpackIncentiveFetcher(),
        HyperliquidIncentiveFetcher(),
        DydxIncentiveFetcher(),
    ]

    for fetcher in fetchers:
        snapshots = fetcher.fetch()
        for snapshot in snapshots:
            snapshot.score = compute_incentive_score(snapshot)
            all_snapshots.append(snapshot)
            
    return all_snapshots

# --- PerpBot V2 Integration Notes ---
#
# This module is designed to be a plug-in data source for other core
# components of PerpBot V2. The data should be used as follows:
#
# 1. ScannerV3 Integration:
#    The `ScannerV3` should consume the output of `collect_incentives()`.
#    The `snapshot.score` can be used as a positive weighting factor when
#    evaluating arbitrage opportunities. For example, a high score could
#    justify pursuing a trade with a slightly smaller initial spread, as
#    the expected value from rebates/incentives is higher.
#    Example: `effective_spread = raw_spread + (snapshot.score / 10000)`
#
# 2. ExecutionEngineV2 Integration:
#    The `ExecutionEngineV2` can use the `maker_rebate_pct` as a form of
#    "implied PnL" when executing passive (maker) orders. When calculating
#    the final PnL of a trade, the rebate should be added to the exit price.
#    Example: `final_pnl = (exit_price * (1 + maker_rebate_pct)) - entry_price`
#
# 3. RiskEngine Integration:
#    The `RiskEngine` must use this data to identify and penalize potential
#    "incentive traps" or "wash trading schemes". A key heuristic is to
#    flag snapshots where `incentive_apr` is very high (> 75%) while
#    `volume_30d` is very low (< $50M). Such markets should be deprioritized
#    or blacklisted from execution, as the APR is unsustainable and the
#    liquidity is too thin to realize the arbitrage.
#    Example:
#    `is_trap = snapshot.incentive_apr > 0.75 and snapshot.volume_30d < 50_000_000`
#    if is_trap:
#        # Lower position size limits or block trading on this market.
#
# --- End Integration Notes ---
