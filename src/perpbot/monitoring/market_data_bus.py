from __future__ import annotations

import asyncio
import logging
from typing import Callable, Iterable, List, Optional

from perpbot.exchanges.pricing import WebsocketPriceMonitor, fetch_quotes_concurrently
from perpbot.models import PriceQuote
from perpbot.monitoring.state import MonitoringState

logger = logging.getLogger(__name__)


class MarketDataBus:
    """统一行情总线，负责并发抓取并广播给订阅者与监控容器。"""

    def __init__(self, monitoring_state: Optional[MonitoringState] = None, per_exchange_limit: int = 2) -> None:
        self.monitor = WebsocketPriceMonitor()
        self.monitoring_state = monitoring_state
        self.per_exchange_limit = per_exchange_limit
        self.subscribers: List[Callable[[List[PriceQuote]], None]] = []

    def subscribe(self, callback: Callable[[List[PriceQuote]], None]) -> None:
        self.subscribers.append(callback)

    def collect_quotes(self, exchanges: Iterable, symbols: Iterable[str]) -> List[PriceQuote]:
        async def _collect():
            return await fetch_quotes_concurrently(exchanges, symbols, per_exchange_limit=self.per_exchange_limit, monitor=self.monitor)

        quotes = asyncio.run(_collect())
        for q in quotes:
            if self.monitoring_state:
                self.monitoring_state.update_quote(q)
        for cb in self.subscribers:
            try:
                cb(quotes)
            except Exception:
                logger.exception("行情订阅回调失败")
        return quotes

    def get_cached(self, exchange: str, symbol: str) -> Optional[PriceQuote]:
        return self.monitor.get(exchange, symbol)
