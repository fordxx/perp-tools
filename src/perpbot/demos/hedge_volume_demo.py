"""跨交易所永续对冲刷量独立演示脚本。

运行方式：
    PYTHONPATH=src python -m perpbot.demos.hedge_volume_demo

说明：
- 仅使用本文件内的简易 MockExchange 演示调用方式；
- 删除本文件或 hedge_volume_engine 模块，不影响原有套利/风控系统运行；
- 真正实盘需要替换为实现了 ExchangeClient 接口的真实交易所实例，并在接入层显式传入。
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import Dict

from perpbot.capital_orchestrator import CapitalOrchestrator
from perpbot.hedge_volume_engine import HedgeVolumeEngine
from perpbot.models import Order, OrderRequest, PriceQuote

logging.basicConfig(level=logging.INFO)


@dataclass
class MockOrder(Order):
    pass


class MockExchange:
    """仅用于演示的轻量实现，满足 HedgeVolumeEngine 的显式接口需求。"""

    def __init__(self, name: str):
        self.name = name
        self.venue_type = "dex"

    def get_current_price(self, symbol: str) -> PriceQuote:
        mid = 30_000 + random.random() * 100
        return PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=mid - 1,
            ask=mid + 1,
            mid=mid,
            venue_type="dex",
        )

    def get_orderbook(self, symbol: str):
        mid = 30_000
        return {
            "bids": [(mid - 1, 1), (mid - 2, 2)],
            "asks": [(mid + 1, 1), (mid + 2, 2)],
        }

    def place_open_order(self, req: OrderRequest) -> Order:
        price = 30_000 + (1 if req.side == "buy" else -1)
        return MockOrder(id=f"{self.name}-{random.randint(1,10000)}", symbol=req.symbol, side=req.side, size=req.size, price=price)

    def cancel_order(self, order_id: str, symbol: str):
        logging.info("取消订单 %s %s", order_id, symbol)


async def run_demo() -> None:
    exchanges: Dict[str, MockExchange] = {
        "dex_a": MockExchange("dex_a"),
        "dex_b": MockExchange("dex_b"),
    }
    orchestrator = CapitalOrchestrator()
    engine = HedgeVolumeEngine(
        exchanges=exchanges,
        orchestrator=orchestrator,
        min_notional=300,
        max_notional=800,
        hold_seconds=(1, 2),
    )

    result = await engine.execute_wash_cycle(symbol="BTCUSDT", long_exchange="dex_a", short_exchange="dex_b")
    print("刷量结果:", result)


if __name__ == "__main__":
    asyncio.run(run_demo())

