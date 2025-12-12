"""
Unit Tests for EventBus
测试事件总线的核心功能
"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.events.event_bus import EventBus
from perpbot.events.event_types import (
    MarketDataUpdate,
    ArbitrageOpportunityFound,
    OrderExecuted,
    PositionOpened,
    PositionClosed,
)
from datetime import datetime


class TestEventBus(unittest.TestCase):
    """测试 EventBus 核心功能"""

    def setUp(self):
        """每个测试前初始化"""
        self.event_bus = EventBus()

    def tearDown(self):
        """每个测试后清理"""
        self.event_bus = None

    def test_subscribe_and_publish(self):
        """测试订阅和发布基本功能"""
        received_events = []

        def handler(event: MarketDataUpdate):
            received_events.append(event)

        # 订阅
        self.event_bus.subscribe(MarketDataUpdate, handler)

        # 发布事件
        event = MarketDataUpdate(
            exchange="okx",
            symbol="BTC-USDT",
            bid=50000.0,
            ask=50001.0,
            bid_size=1.0,
            ask_size=1.0,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(event)

        # 验证
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0], event)

    def test_multiple_subscribers(self):
        """测试多个订阅者"""
        handler1_events = []
        handler2_events = []
        handler3_events = []

        def handler1(event: MarketDataUpdate):
            handler1_events.append(event)

        def handler2(event: MarketDataUpdate):
            handler2_events.append(event)

        def handler3(event: MarketDataUpdate):
            handler3_events.append(event)

        # 订阅
        self.event_bus.subscribe(MarketDataUpdate, handler1)
        self.event_bus.subscribe(MarketDataUpdate, handler2)
        self.event_bus.subscribe(MarketDataUpdate, handler3)

        # 发布事件
        event = MarketDataUpdate(
            exchange="okx",
            symbol="ETH-USDT",
            bid=3000.0,
            ask=3001.0,
            bid_size=5.0,
            ask_size=5.0,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(event)

        # 验证所有订阅者都收到了事件
        self.assertEqual(len(handler1_events), 1)
        self.assertEqual(len(handler2_events), 1)
        self.assertEqual(len(handler3_events), 1)

        self.assertEqual(handler1_events[0], event)
        self.assertEqual(handler2_events[0], event)
        self.assertEqual(handler3_events[0], event)

    def test_event_type_filtering(self):
        """测试事件类型过滤"""
        market_events = []
        arbitrage_events = []

        def market_handler(event: MarketDataUpdate):
            market_events.append(event)

        def arbitrage_handler(event: ArbitrageOpportunityFound):
            arbitrage_events.append(event)

        # 订阅不同类型的事件
        self.event_bus.subscribe(MarketDataUpdate, market_handler)
        self.event_bus.subscribe(ArbitrageOpportunityFound, arbitrage_handler)

        # 发布行情事件
        market_event = MarketDataUpdate(
            exchange="okx",
            symbol="BTC-USDT",
            bid=50000.0,
            ask=50001.0,
            bid_size=1.0,
            ask_size=1.0,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(market_event)

        # 发布套利事件
        arbitrage_event = ArbitrageOpportunityFound(
            symbol="BTC-USDT",
            buy_exchange="okx",
            sell_exchange="paradex",
            buy_price=50000.0,
            sell_price=50100.0,
            spread_bps=200.0,
            size=0.1,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(arbitrage_event)

        # 验证事件类型过滤正确
        self.assertEqual(len(market_events), 1)
        self.assertEqual(len(arbitrage_events), 1)

        self.assertEqual(market_events[0], market_event)
        self.assertEqual(arbitrage_events[0], arbitrage_event)

    def test_unsubscribe(self):
        """测试取消订阅"""
        received_events = []

        def handler(event: MarketDataUpdate):
            received_events.append(event)

        # 订阅
        self.event_bus.subscribe(MarketDataUpdate, handler)

        # 发布事件1
        event1 = MarketDataUpdate(
            exchange="okx",
            symbol="BTC-USDT",
            bid=50000.0,
            ask=50001.0,
            bid_size=1.0,
            ask_size=1.0,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(event1)

        self.assertEqual(len(received_events), 1)

        # 取消订阅
        self.event_bus.unsubscribe(MarketDataUpdate, handler)

        # 发布事件2
        event2 = MarketDataUpdate(
            exchange="okx",
            symbol="ETH-USDT",
            bid=3000.0,
            ask=3001.0,
            bid_size=5.0,
            ask_size=5.0,
            timestamp=datetime.utcnow(),
        )
        self.event_bus.publish(event2)

        # 验证取消订阅后不再接收事件
        self.assertEqual(len(received_events), 1)

    def test_exception_in_handler(self):
        """测试处理器异常不影响其他订阅者"""
        handler1_events = []
        handler2_events = []

        def handler1(event: MarketDataUpdate):
            handler1_events.append(event)
            raise ValueError("Intentional error in handler1")

        def handler2(event: MarketDataUpdate):
            handler2_events.append(event)

        # 订阅
        self.event_bus.subscribe(MarketDataUpdate, handler1)
        self.event_bus.subscribe(MarketDataUpdate, handler2)

        # 发布事件
        event = MarketDataUpdate(
            exchange="okx",
            symbol="BTC-USDT",
            bid=50000.0,
            ask=50001.0,
            bid_size=1.0,
            ask_size=1.0,
            timestamp=datetime.utcnow(),
        )

        # 应该捕获异常，不抛出
        try:
            self.event_bus.publish(event)
        except Exception as e:
            self.fail(f"EventBus should catch handler exceptions, but raised: {e}")

        # 验证 handler2 仍然收到事件
        self.assertEqual(len(handler1_events), 1)
        self.assertEqual(len(handler2_events), 1)


if __name__ == "__main__":
    unittest.main()
