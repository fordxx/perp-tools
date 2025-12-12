from __future__ import annotations
from typing import List

from models.order_request import OrderRequest
from .spread_calculator import SpreadResult


class ScannerExecutorAdapter:
    def __init__(self, execution_engine):
        self.execution_engine = execution_engine

    def handle_spreads(self, spreads: List[SpreadResult]):
        """
        将 SpreadResult → OrderRequest(strategy="ARBITRAGE")
        每个 signal 触发一笔下单
        """
        for s in spreads:
            req = OrderRequest(
                exchange=s.ask_exchange,    # buy 端
                symbol=s.symbol,
                side="BUY",
                limit_price=s.ask,
                size=1.0,                  # placeholder notional
                strategy="ARBITRAGE",
                is_fallback=False,
            )
            self.execution_engine.execute_order(req)
