from __future__ import annotations

from typing import Optional

from .quote_types import RawQuote, NormalizedQuote


class QuoteNormalizer:
    """
    A stateless utility to convert and validate raw quotes into a standardized format.
    """

    @staticmethod
    def normalize(raw: RawQuote) -> Optional[NormalizedQuote]:
        """
        Converts a RawQuote to a NormalizedQuote, performing validation and calculations.

        Returns None if the quote is invalid (e.g., zero/negative prices, crossed book).
        """
        # --- Validation ---
        if raw.bid <= 0 or raw.ask <= 0:
            return None

        if raw.bid >= raw.ask:
            return None

        # --- Calculation ---
        mid_price = (raw.bid + raw.ask) / 2.0
        spread_bps = ((raw.ask - raw.bid) / mid_price) * 10000

        return NormalizedQuote(
            exchange=raw.exchange,
            symbol=raw.symbol,
            best_bid=raw.bid,
            best_ask=raw.ask,
            mid_price=mid_price,
            spread_bps=spread_bps,
            timestamp=raw.timestamp,
        )