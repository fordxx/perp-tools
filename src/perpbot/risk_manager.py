from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from perpbot.models import Position, PriceQuote, Side

logger = logging.getLogger(__name__)


class RiskManager:
    """Portfolio-level risk controls for drawdown, exposure, and anomalies."""

    def __init__(
        self,
        assumed_equity: float,
        max_drawdown_pct: float = 0.1,
        max_consecutive_failures: int = 3,
        max_symbol_exposure_pct: float = 0.2,
        enforce_direction_consistency: bool = True,
        freeze_threshold_pct: float = 0.02,
        freeze_window_seconds: int = 1,
    ):
        self.assumed_equity = max(assumed_equity, 1.0)
        self.peak_equity = self.assumed_equity
        self.last_equity = self.assumed_equity
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_failures = max_consecutive_failures
        self.max_symbol_exposure_pct = max_symbol_exposure_pct
        self.enforce_direction_consistency = enforce_direction_consistency
        self.freeze_threshold_pct = freeze_threshold_pct
        self.freeze_window = timedelta(seconds=freeze_window_seconds)

        self.consecutive_failures = 0
        self.trading_halted = False
        self.halt_reason: Optional[str] = None
        self._frozen_until: Optional[datetime] = None
        self._freeze_reason: Optional[str] = None
        self._last_price: Dict[str, Tuple[float, datetime]] = {}

    def collect_positions(self, exchanges: Iterable) -> List[Position]:
        positions: List[Position] = []
        for ex in exchanges:
            try:
                positions.extend(ex.get_account_positions())
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.debug("Failed to collect positions from %s: %s", getattr(ex, "name", "unknown"), exc)
        return positions

    def update_equity(self, positions: Sequence[Position], quotes: Optional[Iterable[PriceQuote]] = None) -> float:
        quote_map = {q.symbol: q for q in quotes} if quotes else {}
        equity = self.assumed_equity
        for pos in positions:
            price = quote_map.get(pos.order.symbol).mid if quote_map.get(pos.order.symbol) else pos.order.price
            direction = 1 if pos.order.side == "buy" else -1
            equity += direction * pos.order.size * price
        self.last_equity = max(equity, 0.0)
        self.peak_equity = max(self.peak_equity, self.last_equity)
        drawdown = (self.peak_equity - self.last_equity) / self.peak_equity if self.peak_equity else 0.0
        if drawdown >= self.max_drawdown_pct:
            self.trading_halted = True
            self.halt_reason = f"Max drawdown reached: {drawdown * 100:.2f}%"
            logger.warning(self.halt_reason)
        return self.last_equity

    def evaluate_market(self, quotes: Iterable[PriceQuote]) -> None:
        now = datetime.utcnow()
        for quote in quotes:
            mid = quote.mid
            last_price = self._last_price.get(quote.symbol)
            if last_price:
                prev_price, ts = last_price
                if now - ts <= self.freeze_window and prev_price > 0:
                    move = abs(mid - prev_price) / prev_price
                    if move >= self.freeze_threshold_pct:
                        self._frozen_until = now + self.freeze_window
                        self._freeze_reason = (
                            f"Market freeze triggered for {quote.symbol}: {move * 100:.2f}% move in {self.freeze_window.total_seconds():.0f}s"
                        )
                        logger.warning(self._freeze_reason)
            self._last_price[quote.symbol] = (mid, now)

    def can_trade(
        self,
        symbol: str,
        side: Side,
        size: float,
        price: float,
        positions: Sequence[Position],
        quotes: Optional[Iterable[PriceQuote]] = None,
    ) -> Tuple[bool, Optional[str]]:
        if self.trading_halted:
            return False, self.halt_reason
        if self._is_frozen():
            return False, self._freeze_reason
        if self.max_consecutive_failures and self.consecutive_failures >= self.max_consecutive_failures:
            return False, "Max consecutive failures reached"

        equity = max(self.last_equity, self.assumed_equity)
        net_size, _ = self._symbol_net_and_exposure(symbol, positions, quotes, price)
        direction = 1 if side == "buy" else -1
        new_net = net_size + direction * size
        new_exposure = abs(new_net) * price

        if self.max_symbol_exposure_pct and equity > 0 and new_exposure > equity * self.max_symbol_exposure_pct:
            return False, f"Exposure limit exceeded for {symbol}"

        if self.enforce_direction_consistency and abs(net_size) > 1e-9 and (net_size > 0) != (direction > 0):
            return False, "Position direction conflict"

        return True, None

    def is_frozen(self) -> bool:
        return self._is_frozen()

    def freeze_reason(self) -> Optional[str]:
        if self._is_frozen():
            return self._freeze_reason
        return None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        logger.warning("Trade failure recorded; streak=%s", self.consecutive_failures)

    def record_success(self) -> None:
        if self.consecutive_failures:
            logger.info("Resetting failure streak after success")
        self.consecutive_failures = 0

    def _symbol_net_and_exposure(
        self,
        symbol: str,
        positions: Sequence[Position],
        quotes: Optional[Iterable[PriceQuote]],
        fallback_price: float,
    ) -> Tuple[float, float]:
        quote_map = {q.symbol: q for q in quotes} if quotes else {}
        price = quote_map.get(symbol).mid if quote_map.get(symbol) else fallback_price
        net = 0.0
        for pos in positions:
            if pos.order.symbol != symbol:
                continue
            net += pos.order.size if pos.order.side == "buy" else -pos.order.size
        return net, abs(net) * price

    def _is_frozen(self) -> bool:
        if not self._frozen_until:
            return False
        if datetime.utcnow() <= self._frozen_until:
            return True
        self._frozen_until = None
        self._freeze_reason = None
        return False
