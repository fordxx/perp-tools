import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .quote_cache import QuoteCache
from .quote_noise_filter import QuoteNoiseFilter
from .quote_normalizer import QuoteNormalizer
from .quote_quality import QuoteQuality, QuoteQualityScorer
from .quote_types import NormalizedQuote, RawQuote

logger = logging.getLogger(__name__)


class QuoteEngineV2:
    """
    Processes raw quotes through a normalization, filtering, and quality scoring pipeline,
    and maintains a cache of the best available quotes.
    """

    def __init__(self):
        self.cache = QuoteCache()
        # State for noise filter and quality scoring
        self._mid_price_windows: Dict[str, float] = defaultdict(float)
        self._last_quote_qualities: Dict[str, QuoteQuality] = {}

    def on_raw_quote(self, raw: RawQuote):
        """
        The main entry point for processing a new raw quote from an exchange.
        """
        processing_start_time = time.time()

        # 1. Normalize
        normalized_quote = QuoteNormalizer.normalize(raw)
        if not normalized_quote:
            logger.debug(f"Raw quote failed normalization: {raw}")
            return

        # 2. Noise Filter
        # Use the last known mid-price from the cache as the reference for the noise filter.
        # If no price exists, the filter will be skipped on the first quote.
        reference_mid_price = self.cache.get_mid_price(normalized_quote.symbol)
        filtered_quote = QuoteNoiseFilter.filter(normalized_quote, reference_mid_price)
        if not filtered_quote:
            logger.debug(f"Normalized quote failed noise filter: {normalized_quote}")
            return

        # 3. Quality Scoring
        # Calculate metrics for scoring
        latency_ms = (processing_start_time - raw.timestamp) * 1000
        freshness_ms = (processing_start_time - filtered_quote.timestamp) * 1000
        variance_ratio = (
            abs(filtered_quote.mid_price - reference_mid_price) / reference_mid_price
            if reference_mid_price > 0
            else 0.0
        )

        quality = QuoteQualityScorer.score(
            exchange=filtered_quote.exchange,
            latency_ms=latency_ms,
            freshness_ms=freshness_ms,
            variance_ratio=variance_ratio,
        )
        self._last_quote_qualities[filtered_quote.exchange] = quality
        logger.debug(f"Quote scored: {filtered_quote.symbol} on {quality.exchange} -> {quality.label} ({quality.score:.1f})")

        # 4. Update Cache
        # Only update the cache with quotes that are not of BAD quality.
        if quality.label != "BAD":
            self.cache.update(filtered_quote)

    def get_bbo(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Retrieves the best bid and ask for a given symbol from the global cache.
        """
        return self.cache.get_best_bid_ask(symbol)