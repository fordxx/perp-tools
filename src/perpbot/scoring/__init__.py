"""
perpbot.scoring - Opportunity scoring engine

Mathematical-level profit evaluation for all trading opportunities.

Integrates:
- FeeModel: Exchange fee calculation
- FundingModel: Funding rate profit/cost
- SlippageModel: Slippage and latency estimation
- OpportunityScorer: Unified scoring engine
"""

from perpbot.scoring.fee_model import FeeModel, ExchangeFeeConfig
from perpbot.scoring.funding_model import FundingModel, FundingRateInfo
from perpbot.scoring.slippage_model import SlippageModel, OrderbookDepth
from perpbot.scoring.opportunity_scorer import OpportunityScorer, OpportunityScore

__all__ = [
    "FeeModel",
    "ExchangeFeeConfig",
    "FundingModel",
    "FundingRateInfo",
    "SlippageModel",
    "OrderbookDepth",
    "OpportunityScorer",
    "OpportunityScore",
]
