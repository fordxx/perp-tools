import threading
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .quote_types import NormalizedQuote


class QuoteCache:
    """
    A thread-safe cache for storing and retrieving normalized quotes for multiple symbols
    from various exchanges. It provides methods to get the global Best Bid and Offer (BBO).
    """

    def __init__(self):
        # The cache stores quotes per symbol, with each exchange's latest quote in a nested dict.
        # Structure: { "symbol": { "exchange": NormalizedQuote } }
        self._cache: Dict[str, Dict[str, NormalizedQuote]] = defaultdict(dict)
        self._lock = threading.Lock()

    def update(self, quote: NormalizedQuote):
        """
        Updates the cache with a new normalized quote. This operation is thread-safe.
        It replaces the previous quote for the same exchange and symbol.
        """
        with self._lock:
            self._cache[quote.symbol][quote.exchange] = quote

    def get_best_bid_ask(self, symbol: str) -> Optional[Tuple[float, float]]:
        """
        Calculates the global Best Bid and Offer (BBO) for a given symbol
        by aggregating quotes from all exchanges in the cache.

        Returns:
            A tuple of (best_bid, best_ask) or None if no quotes are available for the symbol.
        """
        with self._lock:
            symbol_quotes = self._cache.get(symbol)
            if not symbol_quotes:
                return None

            all_quotes = list(symbol_quotes.values())
            if not all_quotes:
                return None

            best_bid = max(q.best_bid for q in all_quotes)
            best_ask = min(q.best_ask for q in all_quotes)

            # Ensure the book is not crossed
            if best_bid < best_ask:
                return best_bid, best_ask
            else:
                # This can happen in volatile markets or with stale data from one exchange.
                # A simple approach is to return None, letting the caller handle the invalid state.
                return None

    def get_mid_price(self, symbol: str) -> float:
        """
        Calculates a simple mid-price from the global BBO.

        Returns:
            The mid-price, or 0.0 if no valid BBO is available.
        """
        bbo = self.get_best_bid_ask(symbol)
        if bbo:
            best_bid, best_ask = bbo
            return (best_bid + best_ask) / 2.0
        return 0.0

    def get_weighted_mid(self, symbol: str) -> float:
        """
        Calculates a weighted mid-price based on the best bid and ask across all exchanges.
        This implementation is a placeholder as NormalizedQuote does not contain size information.
        A real implementation would require bid/ask sizes.

        For now, it falls back to the simple mid-price.

        Returns:
            The weighted mid-price, or 0.0 if not computable.
        """
        # NOTE: The current `NormalizedQuote` does not include size information,
        # which is necessary for a true weighted mid-price calculation.
        # This method falls back to the simple mid-price.
        # To implement this properly, `bid_size` and `ask_size` would need to be
        # carried over from `RawQuote` to `NormalizedQuote`.
        return self.get_mid_price(symbol)

    def get_all_quotes_for_symbol(self, symbol: str) -> List[NormalizedQuote]:
        """Returns a list of all cached quotes for a specific symbol."""
        with self._lock:
            return list(self._cache.get(symbol, {}).values())