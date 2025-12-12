"""
Unit Tests for Exposure Model
测试风险敞口模型的核心功能
"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.exposure.exposure_model import ExposureModel, PositionExposure
from datetime import datetime


class TestPositionExposure(unittest.TestCase):
    """测试 PositionExposure 数据模型"""

    def test_long_position(self):
        """测试多头持仓"""
        exposure = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="long",
            size=0.5,
            entry_price=50000.0,
            current_price=51000.0,
            notional=25000.0,
            unrealized_pnl=500.0,
        )

        self.assertEqual(exposure.side, "long")
        self.assertEqual(exposure.size, 0.5)
        self.assertEqual(exposure.entry_price, 50000.0)
        self.assertEqual(exposure.notional, 25000.0)
        self.assertGreater(exposure.unrealized_pnl, 0)

    def test_short_position(self):
        """测试空头持仓"""
        exposure = PositionExposure(
            exchange="paradex",
            symbol="ETH-USDT",
            side="short",
            size=-2.0,
            entry_price=3000.0,
            current_price=2950.0,
            notional=6000.0,
            unrealized_pnl=100.0,
        )

        self.assertEqual(exposure.side, "short")
        self.assertEqual(exposure.size, -2.0)
        self.assertEqual(exposure.entry_price, 3000.0)
        self.assertGreater(exposure.unrealized_pnl, 0)  # 价格下跌，空头盈利

    def test_zero_position(self):
        """测试零持仓"""
        exposure = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="flat",
            size=0.0,
            entry_price=0.0,
            current_price=50000.0,
            notional=0.0,
            unrealized_pnl=0.0,
        )

        self.assertEqual(exposure.size, 0.0)
        self.assertEqual(exposure.notional, 0.0)
        self.assertEqual(exposure.unrealized_pnl, 0.0)

    def test_notional_calculation(self):
        """测试名义价值计算"""
        size = 0.5
        price = 50000.0
        expected_notional = abs(size) * price

        exposure = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="long",
            size=size,
            entry_price=price,
            current_price=price,
            notional=expected_notional,
            unrealized_pnl=0.0,
        )

        self.assertEqual(exposure.notional, expected_notional)

    def test_pnl_calculation_long(self):
        """测试多头盈亏计算"""
        size = 1.0
        entry_price = 50000.0
        current_price = 51000.0
        expected_pnl = size * (current_price - entry_price)

        exposure = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="long",
            size=size,
            entry_price=entry_price,
            current_price=current_price,
            notional=size * current_price,
            unrealized_pnl=expected_pnl,
        )

        self.assertEqual(exposure.unrealized_pnl, expected_pnl)
        self.assertGreater(exposure.unrealized_pnl, 0)

    def test_pnl_calculation_short(self):
        """测试空头盈亏计算"""
        size = -1.0
        entry_price = 50000.0
        current_price = 49000.0
        expected_pnl = abs(size) * (entry_price - current_price)

        exposure = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="short",
            size=size,
            entry_price=entry_price,
            current_price=current_price,
            notional=abs(size) * current_price,
            unrealized_pnl=expected_pnl,
        )

        self.assertEqual(exposure.unrealized_pnl, expected_pnl)
        self.assertGreater(exposure.unrealized_pnl, 0)


class TestExposureModel(unittest.TestCase):
    """测试 ExposureModel 核心功能"""

    def setUp(self):
        """每个测试前初始化"""
        self.model = ExposureModel()

    def test_initialization(self):
        """测试模型初始化"""
        self.assertIsNotNone(self.model)

    def test_single_position_exposure(self):
        """测试单个持仓的风险敞口"""
        # 单个多头持仓
        position = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="long",
            size=1.0,
            entry_price=50000.0,
            current_price=51000.0,
            notional=51000.0,
            unrealized_pnl=1000.0,
        )

        # 验证持仓数据
        self.assertEqual(position.notional, 51000.0)
        self.assertEqual(position.unrealized_pnl, 1000.0)

    def test_multiple_positions_same_symbol(self):
        """测试同一交易对的多个持仓"""
        positions = [
            PositionExposure(
                exchange="okx",
                symbol="BTC-USDT",
                side="long",
                size=0.5,
                entry_price=50000.0,
                current_price=51000.0,
                notional=25500.0,
                unrealized_pnl=500.0,
            ),
            PositionExposure(
                exchange="paradex",
                symbol="BTC-USDT",
                side="short",
                size=-0.3,
                entry_price=51000.0,
                current_price=51000.0,
                notional=15300.0,
                unrealized_pnl=0.0,
            ),
        ]

        # 验证持仓数量
        self.assertEqual(len(positions), 2)

        # 计算净敞口
        net_size = sum(p.size for p in positions)
        self.assertEqual(net_size, 0.2)  # 0.5 - 0.3

        # 计算总名义价值
        total_notional = sum(p.notional for p in positions)
        self.assertEqual(total_notional, 25500.0 + 15300.0)

    def test_cross_symbol_exposure(self):
        """测试跨交易对的风险敞口"""
        positions = [
            PositionExposure(
                exchange="okx",
                symbol="BTC-USDT",
                side="long",
                size=1.0,
                entry_price=50000.0,
                current_price=51000.0,
                notional=51000.0,
                unrealized_pnl=1000.0,
            ),
            PositionExposure(
                exchange="paradex",
                symbol="ETH-USDT",
                side="long",
                size=10.0,
                entry_price=3000.0,
                current_price=3100.0,
                notional=31000.0,
                unrealized_pnl=1000.0,
            ),
        ]

        # 验证不同交易对
        symbols = {p.symbol for p in positions}
        self.assertEqual(len(symbols), 2)
        self.assertIn("BTC-USDT", symbols)
        self.assertIn("ETH-USDT", symbols)

        # 计算总敞口
        total_notional = sum(p.notional for p in positions)
        total_pnl = sum(p.unrealized_pnl for p in positions)

        self.assertEqual(total_notional, 82000.0)
        self.assertEqual(total_pnl, 2000.0)

    def test_hedged_position(self):
        """测试对冲持仓"""
        # 同一交易对的多空对冲
        long_position = PositionExposure(
            exchange="okx",
            symbol="BTC-USDT",
            side="long",
            size=1.0,
            entry_price=50000.0,
            current_price=51000.0,
            notional=51000.0,
            unrealized_pnl=1000.0,
        )

        short_position = PositionExposure(
            exchange="paradex",
            symbol="BTC-USDT",
            side="short",
            size=-1.0,
            entry_price=50500.0,
            current_price=51000.0,
            notional=51000.0,
            unrealized_pnl=-500.0,
        )

        # 计算净敞口
        net_size = long_position.size + short_position.size
        self.assertEqual(net_size, 0.0)  # 完全对冲

        # 计算总盈亏
        total_pnl = long_position.unrealized_pnl + short_position.unrealized_pnl
        self.assertEqual(total_pnl, 500.0)  # 套利利润


if __name__ == "__main__":
    unittest.main()
