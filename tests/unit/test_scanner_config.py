"""
Unit Tests for Scanner Configuration
测试扫描器配置的核心功能
"""
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.scanner.scanner_config import ScannerConfig


class TestScannerConfig(unittest.TestCase):
    """测试 ScannerConfig 核心功能"""

    def test_default_config(self):
        """测试默认配置"""
        config = ScannerConfig()

        # 验证默认值
        self.assertIsInstance(config.enabled_exchanges, list)
        self.assertIsInstance(config.enabled_symbols, list)
        self.assertIsInstance(config.min_profit_bps, (int, float))
        self.assertIsInstance(config.update_interval_sec, (int, float))

    def test_custom_config(self):
        """测试自定义配置"""
        config = ScannerConfig(
            enabled_exchanges=["okx", "paradex"],
            enabled_symbols=["BTC-USDT", "ETH-USDT"],
            min_profit_bps=20,
            update_interval_sec=2.0,
            max_position_size_usd=5000.0,
        )

        # 验证自定义值
        self.assertEqual(config.enabled_exchanges, ["okx", "paradex"])
        self.assertEqual(config.enabled_symbols, ["BTC-USDT", "ETH-USDT"])
        self.assertEqual(config.min_profit_bps, 20)
        self.assertEqual(config.update_interval_sec, 2.0)
        self.assertEqual(config.max_position_size_usd, 5000.0)

    def test_exchange_validation(self):
        """测试交易所验证"""
        # 空交易所列表应该有效（或根据实际需求调整）
        config = ScannerConfig(enabled_exchanges=[])
        self.assertEqual(config.enabled_exchanges, [])

        # 单个交易所
        config = ScannerConfig(enabled_exchanges=["okx"])
        self.assertEqual(len(config.enabled_exchanges), 1)

        # 多个交易所
        config = ScannerConfig(enabled_exchanges=["okx", "paradex", "hyperliquid"])
        self.assertEqual(len(config.enabled_exchanges), 3)

    def test_symbol_validation(self):
        """测试交易对验证"""
        # 标准交易对格式
        config = ScannerConfig(enabled_symbols=["BTC-USDT", "ETH-USDT"])
        self.assertEqual(len(config.enabled_symbols), 2)

        # 验证交易对格式（如果有格式要求）
        for symbol in config.enabled_symbols:
            self.assertIn("-", symbol)
            self.assertTrue(symbol.endswith("USDT") or symbol.endswith("USD"))

    def test_profit_threshold(self):
        """测试利润阈值配置"""
        # 正常阈值
        config = ScannerConfig(min_profit_bps=10)
        self.assertEqual(config.min_profit_bps, 10)

        # 较高阈值
        config = ScannerConfig(min_profit_bps=50)
        self.assertEqual(config.min_profit_bps, 50)

        # 较低阈值
        config = ScannerConfig(min_profit_bps=5)
        self.assertEqual(config.min_profit_bps, 5)

    def test_update_interval(self):
        """测试更新间隔配置"""
        # 快速更新
        config = ScannerConfig(update_interval_sec=0.5)
        self.assertEqual(config.update_interval_sec, 0.5)

        # 慢速更新
        config = ScannerConfig(update_interval_sec=5.0)
        self.assertEqual(config.update_interval_sec, 5.0)

    def test_position_size_limit(self):
        """测试仓位大小限制"""
        # 小仓位
        config = ScannerConfig(max_position_size_usd=1000.0)
        self.assertEqual(config.max_position_size_usd, 1000.0)

        # 大仓位
        config = ScannerConfig(max_position_size_usd=100000.0)
        self.assertEqual(config.max_position_size_usd, 100000.0)

    def test_config_immutability(self):
        """测试配置不可变性（如果配置应该是不可变的）"""
        config = ScannerConfig(
            enabled_exchanges=["okx"],
            min_profit_bps=10,
        )

        # 尝试修改配置
        original_exchanges = config.enabled_exchanges.copy()
        config.enabled_exchanges.append("paradex")

        # 验证配置可以修改（或者如果需要不可变，则进行相反的断言）
        self.assertNotEqual(len(config.enabled_exchanges), len(original_exchanges))

    def test_config_copy(self):
        """测试配置复制"""
        original = ScannerConfig(
            enabled_exchanges=["okx", "paradex"],
            enabled_symbols=["BTC-USDT"],
            min_profit_bps=15,
        )

        # 创建新配置（模拟复制）
        copy = ScannerConfig(
            enabled_exchanges=original.enabled_exchanges.copy(),
            enabled_symbols=original.enabled_symbols.copy(),
            min_profit_bps=original.min_profit_bps,
        )

        # 验证值相等
        self.assertEqual(copy.enabled_exchanges, original.enabled_exchanges)
        self.assertEqual(copy.enabled_symbols, original.enabled_symbols)
        self.assertEqual(copy.min_profit_bps, original.min_profit_bps)

        # 修改 copy 不应影响 original
        copy.enabled_exchanges.append("hyperliquid")
        self.assertNotEqual(len(copy.enabled_exchanges), len(original.enabled_exchanges))


class TestScannerConfigEdgeCases(unittest.TestCase):
    """测试 ScannerConfig 边界情况"""

    def test_empty_exchanges(self):
        """测试空交易所列表"""
        config = ScannerConfig(enabled_exchanges=[])
        self.assertEqual(len(config.enabled_exchanges), 0)

    def test_empty_symbols(self):
        """测试空交易对列表"""
        config = ScannerConfig(enabled_symbols=[])
        self.assertEqual(len(config.enabled_symbols), 0)

    def test_zero_profit_threshold(self):
        """测试零利润阈值"""
        config = ScannerConfig(min_profit_bps=0)
        self.assertEqual(config.min_profit_bps, 0)

    def test_negative_profit_threshold(self):
        """测试负利润阈值（如果允许）"""
        # 根据实际业务逻辑决定是否应该允许负值
        config = ScannerConfig(min_profit_bps=-10)
        self.assertEqual(config.min_profit_bps, -10)

    def test_very_small_update_interval(self):
        """测试极小的更新间隔"""
        config = ScannerConfig(update_interval_sec=0.01)
        self.assertEqual(config.update_interval_sec, 0.01)

    def test_very_large_position_size(self):
        """测试极大的仓位限制"""
        config = ScannerConfig(max_position_size_usd=1000000.0)
        self.assertEqual(config.max_position_size_usd, 1000000.0)


if __name__ == "__main__":
    unittest.main()
