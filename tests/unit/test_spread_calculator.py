"""
Unit Tests for Spread Calculator
测试价差计算器的核心功能
"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.scanner.spread_calculator import SpreadCalculator


class TestSpreadCalculator(unittest.TestCase):
    """测试 SpreadCalculator 核心功能"""

    def setUp(self):
        """每个测试前初始化"""
        self.calculator = SpreadCalculator()

    def test_basic_spread_calculation(self):
        """测试基本价差计算"""
        buy_price = 50000.0
        sell_price = 50100.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 计算预期值: (50100 - 50000) / 50000 * 10000 = 20 BPS
        expected_bps = 20.0
        self.assertAlmostEqual(spread_bps, expected_bps, places=2)

    def test_zero_spread(self):
        """测试零价差"""
        buy_price = 50000.0
        sell_price = 50000.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        self.assertEqual(spread_bps, 0.0)

    def test_negative_spread(self):
        """测试负价差（买价高于卖价）"""
        buy_price = 50100.0
        sell_price = 50000.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 负价差应该是负数
        self.assertLess(spread_bps, 0.0)

        # 计算预期值: (50000 - 50100) / 50100 * 10000 ≈ -19.96 BPS
        expected_bps = -19.96
        self.assertAlmostEqual(spread_bps, expected_bps, places=1)

    def test_large_spread(self):
        """测试大价差"""
        buy_price = 50000.0
        sell_price = 51000.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 计算预期值: (51000 - 50000) / 50000 * 10000 = 200 BPS
        expected_bps = 200.0
        self.assertAlmostEqual(spread_bps, expected_bps, places=2)

    def test_small_spread(self):
        """测试小价差"""
        buy_price = 50000.0
        sell_price = 50005.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 计算预期值: (50005 - 50000) / 50000 * 10000 = 1 BPS
        expected_bps = 1.0
        self.assertAlmostEqual(spread_bps, expected_bps, places=2)

    def test_decimal_precision(self):
        """测试小数精度"""
        buy_price = 50000.12345
        sell_price = 50050.67890

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 验证计算精度
        expected_bps = ((sell_price - buy_price) / buy_price) * 10000
        self.assertAlmostEqual(spread_bps, expected_bps, places=4)

    def test_different_price_levels(self):
        """测试不同价格水平"""
        # 低价
        spread_low = self.calculator.calculate_spread_bps(100.0, 101.0)
        # 中价
        spread_mid = self.calculator.calculate_spread_bps(10000.0, 10100.0)
        # 高价
        spread_high = self.calculator.calculate_spread_bps(50000.0, 50500.0)

        # 相同的绝对价差，但不同的百分比价差
        self.assertAlmostEqual(spread_low, 1000.0, places=2)  # 1% = 1000 BPS
        self.assertAlmostEqual(spread_mid, 100.0, places=2)   # 1% = 100 BPS
        self.assertAlmostEqual(spread_high, 100.0, places=2)  # 1% = 100 BPS


class TestSpreadCalculatorEdgeCases(unittest.TestCase):
    """测试 SpreadCalculator 边界情况"""

    def setUp(self):
        """每个测试前初始化"""
        self.calculator = SpreadCalculator()

    def test_very_small_prices(self):
        """测试极小价格"""
        buy_price = 0.0001
        sell_price = 0.0002

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # (0.0002 - 0.0001) / 0.0001 * 10000 = 10000 BPS (100%)
        expected_bps = 10000.0
        self.assertAlmostEqual(spread_bps, expected_bps, places=2)

    def test_very_large_prices(self):
        """测试极大价格"""
        buy_price = 1000000.0
        sell_price = 1001000.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # (1001000 - 1000000) / 1000000 * 10000 = 10 BPS
        expected_bps = 10.0
        self.assertAlmostEqual(spread_bps, expected_bps, places=2)

    def test_zero_buy_price(self):
        """测试零买价（除以零）"""
        buy_price = 0.0
        sell_price = 50000.0

        # 应该处理除以零的情况
        with self.assertRaises(ZeroDivisionError):
            self.calculator.calculate_spread_bps(buy_price, sell_price)

    def test_negative_prices(self):
        """测试负价格（不应该出现）"""
        buy_price = -50000.0
        sell_price = 50000.0

        # 根据实际业务逻辑决定如何处理负价格
        # 这里假设负价格会导致异常或返回无效值
        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 验证行为（根据实际实现调整）
        self.assertIsNotNone(spread_bps)


class TestSpreadCalculatorProfitability(unittest.TestCase):
    """测试价差盈利性判断"""

    def setUp(self):
        """每个测试前初始化"""
        self.calculator = SpreadCalculator()
        self.min_profit_bps = 10.0  # 最小盈利阈值

    def test_profitable_spread(self):
        """测试可盈利的价差"""
        buy_price = 50000.0
        sell_price = 50100.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 20 BPS > 10 BPS (最小阈值)
        self.assertGreater(spread_bps, self.min_profit_bps)

    def test_unprofitable_spread(self):
        """测试不可盈利的价差"""
        buy_price = 50000.0
        sell_price = 50030.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 6 BPS < 10 BPS (最小阈值)
        self.assertLess(spread_bps, self.min_profit_bps)

    def test_marginal_spread(self):
        """测试临界价差"""
        buy_price = 50000.0
        sell_price = 50050.0

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)

        # 10 BPS = 10 BPS (刚好达到阈值)
        self.assertAlmostEqual(spread_bps, self.min_profit_bps, places=2)

    def test_spread_with_fees(self):
        """测试考虑手续费后的价差"""
        buy_price = 50000.0
        sell_price = 50100.0
        fee_bps = 4.0  # 总手续费 4 BPS (买卖各 2 BPS)

        spread_bps = self.calculator.calculate_spread_bps(buy_price, sell_price)
        net_profit_bps = spread_bps - fee_bps

        # 净利润 = 20 - 4 = 16 BPS
        expected_net_profit = 16.0
        self.assertAlmostEqual(net_profit_bps, expected_net_profit, places=2)

        # 验证仍然盈利
        self.assertGreater(net_profit_bps, self.min_profit_bps)


if __name__ == "__main__":
    unittest.main()
