# src/perpbot/incentives/scoring.py
import math
from .models import IncentiveSnapshot

def compute_incentive_score(snapshot: IncentiveSnapshot) -> float:
    """
    Computes a unified incentive score (0-100) for a given market snapshot.

    The score is based on a weighted combination of:
    - Taker fees (lower is better)
    - Maker rebates (higher is better)
    - 30-day volume (as a liquidity/stability proxy)
    - Incentive APR (with a cap to prevent manipulation)

    Args:
        snapshot: The IncentiveSnapshot to score.

    Returns:
        A score between 0 and 100.
    """
    # 1. Fee Score (0-40 points)
    # Taker fee: lower is better. Scale from 0.1% (0 points) to 0% (40 points).
    taker_fee_score = max(0, 40 * (1 - snapshot.taker_fee_pct / 0.001))

    # Maker rebate: higher is better. Scale from 0% (0 points) to 0.05% (added to score).
    # This directly rewards market making.
    maker_rebate_bonus = min(20, (snapshot.maker_rebate_pct / 0.0005) * 20)
    
    fee_score = min(40, taker_fee_score + maker_rebate_bonus)

    # 2. Volume Score (0-30 points)
    # Logarithmic scale for 30d volume. 1B = 15 points, 100B = 30 points.
    # log(1) = 0, so we add 1 to avoid log(0) and negative results.
    log_volume = math.log10(snapshot.volume_30d + 1)
    # Scale from log(100M) = 8 to log(100B) = 11
    volume_score = max(0, min(30, ((log_volume - 8) / (11 - 8)) * 30))

    # 3. Incentive APR Score (0-30 points)
    # Cap APR at 100% to prevent single-factor dominance from wash trading.
    capped_apr = min(1.0, snapshot.incentive_apr or 0.0)
    apr_score = capped_apr * 30

    # Total Score
    total_score = fee_score + volume_score + apr_score
    
    # Ensure score is within 0-100 range
    final_score = max(0.0, min(100.0, total_score))

    return round(final_score, 2)
