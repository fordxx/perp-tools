from __future__ import annotations

import asyncio
import logging
from typing import Dict, Iterable, List, Optional

from perpbot.models import PriceQuote

logger = logging.getLogger(__name__)


class WebsocketPriceMonitor:
    """Caches latest prices from streaming sources with REST fallback."""

    def __init__(self) -> None:
        self._prices: Dict[str, PriceQuote] = {}

    def update(self, quote: PriceQuote) -> None:
        key = f"{quote.exchange}:{quote.symbol}"
        self._prices[key] = quote

    def get(self, exchange: str, symbol: str) -> Optional[PriceQuote]:
        return self._prices.get(f"{exchange}:{symbol}")


async def fetch_price_with_semaphore(ex, symbol: str, sem: asyncio.Semaphore, monitor: Optional[WebsocketPriceMonitor]):
    async with sem:
        loop = asyncio.get_running_loop()
        quote = await loop.run_in_executor(None, ex.get_current_price, symbol)
        quote.venue_type = getattr(ex, "venue_type", "dex")
        if monitor:
            monitor.update(quote)
        try:
            # 在执行端并发抓取盘口
            book = await loop.run_in_executor(None, ex.get_orderbook, symbol)
            quote.order_book = book
        except Exception:
            logger.exception("Failed orderbook fetch for %s on %s", symbol, ex.name)
        return quote


async def fetch_quotes_concurrently(
    exchanges: Iterable,
    symbols: Iterable[str],
    per_exchange_limit: int = 2,
    monitor: Optional[WebsocketPriceMonitor] = None,
) -> List[PriceQuote]:
    tasks = []
    semaphores: Dict[str, asyncio.Semaphore] = {ex.name: asyncio.Semaphore(per_exchange_limit) for ex in exchanges}
    for ex in exchanges:
        for sym in symbols:
            ws_quote = monitor.get(ex.name, sym) if monitor else None
            if ws_quote:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=ws_quote)))
                continue
            sem = semaphores[ex.name]
            tasks.append(asyncio.create_task(fetch_price_with_semaphore(ex, sym, sem, monitor)))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    quotes: List[PriceQuote] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("Price fetch failed: %s", res)
            continue
        quotes.append(res)
    return quotes

