import threading
from collections import defaultdict
from typing import Dict, List

from ..models.position_snapshot import UnifiedPosition
from ..models.order import Order


class PositionAggregator:
    """
    Aggregates positions from multiple exchanges to provide a unified, real-time view of exposure.
    It is designed to be thread-safe for concurrent updates and reads.
    """

    def __init__(self):
        self._lock = threading.Lock()
        # Key: exchange, Value: List of UnifiedPosition
        self._positions_by_exchange: Dict[str, List[UnifiedPosition]] = defaultdict(list)
        self._fill_history: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def update_positions_for_exchange(self, exchange: str, positions: List[UnifiedPosition]):
        """
        Updates the snapshot of positions for a single exchange.
        This is a full replacement, not an incremental update.
        """
        with self._lock:
            self._positions_by_exchange[exchange] = positions

    def get_all_positions(self) -> List[UnifiedPosition]:
        """
        Returns a flattened list of all positions across all exchanges.
        """
        with self._lock:
            all_positions = []
            for positions in self._positions_by_exchange.values():
                all_positions.extend(positions)
            return all_positions

    def get_net_exposure(self) -> float:
        """
        Calculates the total net exposure in USD across all positions.
        Long positions are positive, short positions are negative.
        """
        total_net = 0.0
        for pos in self.get_all_positions():
            total_net += pos.notional if pos.side.upper() == "LONG" else -pos.notional
        return total_net

    def get_gross_exposure(self) -> float:
        """
        Calculates the total gross exposure (absolute value) in USD across all positions.
        """
        return sum(pos.notional for pos in self.get_all_positions())

    def get_exposure_by_symbol(self) -> Dict[str, float]:
        """
        Calculates the net exposure for each symbol across all exchanges.
        """
        with self._lock:
            exposure_by_symbol: Dict[str, float] = defaultdict(float)
            for pos in self.get_all_positions():
                signed_notional = pos.notional if pos.side.upper() == "LONG" else -pos.notional
                exposure_by_symbol[pos.symbol] += signed_notional
            return dict(exposure_by_symbol)

    def update_after_fill(self, order: Order, fill_price: float, fill_size: float):
        """
        Optional helper for fills: records fill history per symbol/exchange.
        """
        with self._lock:
            self._fill_history[order.exchange][order.symbol] += fill_size * fill_price
