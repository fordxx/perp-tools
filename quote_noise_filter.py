from __future__ import annotations

import time
from typing import Optional

from .quote_types import NormalizedQuote


class QuoteNoiseFilter:
    """
    A stateless utility to filter out noisy or stale quotes based on predefined rules.
    """

    STALE_THRESHOLD_SECONDS: float = 2.0
    DEVIATION_THRESHOLD_RATIO: float = 0.01  # 1%

    @staticmethod
    def filter(quote: NormalizedQuote, mid_window: float) -> Optional[NormalizedQuote]:
        """
        Returns the quote if it passes noise checks, otherwise returns None.

        Checks for:
        1. Staleness (timestamp too old).
        2. Price deviation from a reference moving window mid-price.
        """
        # --- Staleness Check ---
        current_timestamp = time.time()
        if current_timestamp - quote.timestamp > QuoteNoiseFilter.STALE_THRESHOLD_SECONDS:
            return None

        # --- Price Deviation Check ---
        reference_mid = mid_window if mid_window > 0 else quote.mid_price
        if reference_mid <= 0:
            return quote

        deviation = abs(quote.mid_price - reference_mid) / reference_mid
        if deviation > QuoteNoiseFilter.DEVIATION_THRESHOLD_RATIO:
            return None

        # Quote passed all filters
        return quote
