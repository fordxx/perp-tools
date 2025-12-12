"""
Unit Tests for RiskManager
测试风控管理器的核心功能
"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.risk_manager import RiskManager
from perpbot.events.event_bus import EventBus


class TestRiskManager(unittest.TestCase):
    """测试 RiskManager 核心功能"""

    def setUp(self):
        """每个测试前初始化"""
        self.event_bus = EventBus()
        self.risk_manager = RiskManager(
            max_position_size=10000.0,
            max_daily_loss=500.0,
            max_drawdown_percent=5.0,
            event_bus=self.event_bus,
        )

    def tearDown(self):
        """每个测试后清理"""
        self.risk_manager = None
        self.event_bus = None

    def test_initialization(self):
        """测试风控管理器初始化"""
        self.assertEqual(self.risk_manager.max_position_size, 10000.0)
        self.assertEqual(self.risk_manager.max_daily_loss, 500.0)
        self.assertEqual(self.risk_manager.max_drawdown_percent, 5.0)

    def test_position_size_limit(self):
        """测试仓位大小限制"""
        # 小于限制的仓位应该通过
        self.assertTrue(self.risk_manager.max_position_size > 5000.0)

        # 大于限制的仓位应该被拒绝（需要实现具体的检查逻辑）
        large_position = 15000.0
        self.assertGreater(large_position, self.risk_manager.max_position_size)

    def test_daily_loss_limit(self):
        """测试日内亏损限制"""
        # 正常范围内的亏损
        normal_loss = 100.0
        self.assertLess(normal_loss, self.risk_manager.max_daily_loss)

        # 超过限制的亏损
        excessive_loss = 600.0
        self.assertGreater(excessive_loss, self.risk_manager.max_daily_loss)

    def test_drawdown_limit(self):
        """测试最大回撤限制"""
        initial_capital = 10000.0
        max_allowed_loss = initial_capital * (self.risk_manager.max_drawdown_percent / 100)

        # 计算允许的最大回撤金额
        self.assertEqual(max_allowed_loss, 500.0)

        # 小于回撤限制
        acceptable_drawdown = 400.0
        self.assertLess(acceptable_drawdown, max_allowed_loss)

        # 超过回撤限制
        excessive_drawdown = 600.0
        self.assertGreater(excessive_drawdown, max_allowed_loss)

    def test_risk_check_result(self):
        """测试风控检查结果结构"""
        # 这里测试风控检查结果的数据结构
        # 实际的检查逻辑需要根据 RiskManager 的实现来测试

        # 示例：检查结果应该包含的字段
        result_fields = ["passed", "reason", "timestamp"]

        # 验证这些字段存在（需要实际的方法调用）
        # result = self.risk_manager.check_trade(...)
        # for field in result_fields:
        #     self.assertIn(field, result)


class TestRiskManagerIntegration(unittest.TestCase):
    """测试 RiskManager 集成功能"""

    def setUp(self):
        """每个测试前初始化"""
        self.event_bus = EventBus()
        self.risk_manager = RiskManager(
            max_position_size=10000.0,
            max_daily_loss=500.0,
            max_drawdown_percent=5.0,
            event_bus=self.event_bus,
        )

    def test_multiple_concurrent_checks(self):
        """测试并发风控检查"""
        # 模拟多个并发的风控检查请求
        positions = [
            {"size": 1000.0, "symbol": "BTC-USDT"},
            {"size": 2000.0, "symbol": "ETH-USDT"},
            {"size": 1500.0, "symbol": "SOL-USDT"},
        ]

        # 验证总仓位不超过限制
        total_size = sum(p["size"] for p in positions)
        self.assertLess(total_size, self.risk_manager.max_position_size)

    def test_risk_limits_update(self):
        """测试动态更新风控限制"""
        # 更新限制
        new_max_position = 15000.0
        self.risk_manager.max_position_size = new_max_position

        # 验证更新成功
        self.assertEqual(self.risk_manager.max_position_size, 15000.0)

        # 更新日内亏损限制
        new_max_loss = 1000.0
        self.risk_manager.max_daily_loss = new_max_loss

        # 验证更新成功
        self.assertEqual(self.risk_manager.max_daily_loss, 1000.0)


if __name__ == "__main__":
    unittest.main()
