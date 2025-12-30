#!/usr/bin/env python3
"""
简化版 Lighter 测试运行器
不依赖 pytest，直接运行测试
"""
import os
import sys
from typing import Callable, List
import traceback

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from perpbot.exchanges.lighter import LighterClient
from perpbot.exchanges.okx import OKXClient
from unittest.mock import Mock

# ANSI 颜色
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record_pass(self, name: str):
        self.passed += 1
        print(f"{GREEN}✓{RESET} {name}")

    def record_fail(self, name: str, error: str):
        self.failed += 1
        self.errors.append((name, error))
        print(f"{RED}✗{RESET} {name}")
        print(f"  {RED}Error: {error}{RESET}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*70}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"{RED}失败: {self.failed}{RESET}")
            return False
        else:
            print(f"{GREEN}全部通过!{RESET}")
            return True


def run_test(result: TestResult, name: str, test_func: Callable):
    """运行单个测试"""
    try:
        test_func()
        result.record_pass(name)
    except AssertionError as e:
        result.record_fail(name, str(e))
    except Exception as e:
        result.record_fail(name, f"{type(e).__name__}: {e}")


def main():
    result = TestResult()

    print(f"\n{BLUE}{'='*70}{RESET}")
    print(f"{BLUE}Lighter 集成测试套件{RESET}")
    print(f"{BLUE}{'='*70}{RESET}\n")

    # ========== 测试组 1: 接口完整性 ==========
    print(f"\n{YELLOW}[1] 接口完整性测试{RESET}")

    def test_has_get_position():
        assert hasattr(LighterClient, "get_position"), \
            "LighterClient 必须实现 get_position() 方法"

    run_test(result, "LighterClient 有 get_position 方法", test_has_get_position)

    def test_interface_parity():
        required_methods = [
            "get_position",
            "get_account_positions",
            "get_current_price",
            "place_open_order",
            "cancel_order",
            "get_active_orders",
        ]
        for method_name in required_methods:
            assert hasattr(LighterClient, method_name), \
                f"LighterClient 缺少方法: {method_name}"
            assert hasattr(OKXClient, method_name), \
                f"OKXClient 缺少方法: {method_name}"

    run_test(result, "Lighter 和 OKX 接口一致性", test_interface_parity)

    # ========== 测试组 2: get_position 功能 ==========
    print(f"\n{YELLOW}[2] get_position() 方法功能测试{RESET}")

    def test_position_format_conversion():
        """测试 inst_id 格式转换"""
        client = LighterClient(use_testnet=True)

        # Mock 持仓数据
        mock_pos = Mock()
        mock_pos.order.symbol = "EIGEN/USDT"
        mock_pos.order.side = "buy"
        mock_pos.order.size = 100.0
        mock_pos.order.price = 3.5

        client.get_account_positions = Mock(return_value=[mock_pos])

        # 调用 get_position
        result = client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="long")

        assert result is not None, "应该找到匹配的持仓"
        assert result["instId"] == "EIGEN-USDT-SWAP", "inst_id 应该保持 OKX 格式"
        assert result["posSide"] == "long", "pos_side 应该正确"
        assert result["pos"] == "100.0", "持仓数量应该正确"
        assert result["avgPx"] == "3.5", "平均价格应该正确"

    run_test(result, "inst_id 格式转换正确（OKX -> Lighter）", test_position_format_conversion)

    def test_long_side_matching():
        """测试 long 方向匹配"""
        client = LighterClient(use_testnet=True)

        mock_pos = Mock()
        mock_pos.order.symbol = "TON/USDT"
        mock_pos.order.side = "buy"
        mock_pos.order.size = 500.0
        mock_pos.order.price = 5.2

        client.get_account_positions = Mock(return_value=[mock_pos])

        result = client.get_position(inst_id="TON-USDT-SWAP", pos_side="long")
        assert result is not None, "long 应该匹配 buy"
        assert result["posSide"] == "long"

    run_test(result, "pos_side='long' 匹配 side='buy'", test_long_side_matching)

    def test_short_side_matching():
        """测试 short 方向匹配"""
        client = LighterClient(use_testnet=True)

        mock_pos = Mock()
        mock_pos.order.symbol = "BTC/USDT"
        mock_pos.order.side = "sell"
        mock_pos.order.size = 0.5
        mock_pos.order.price = 98000.0

        client.get_account_positions = Mock(return_value=[mock_pos])

        result = client.get_position(inst_id="BTC-USDT-SWAP", pos_side="short")
        assert result is not None, "short 应该匹配 sell"
        assert result["posSide"] == "short"

    run_test(result, "pos_side='short' 匹配 side='sell'", test_short_side_matching)

    def test_no_match_returns_none():
        """测试无匹配时返回 None"""
        client = LighterClient(use_testnet=True)

        mock_pos = Mock()
        mock_pos.order.symbol = "ETH/USDT"
        mock_pos.order.side = "buy"

        client.get_account_positions = Mock(return_value=[mock_pos])

        result = client.get_position(inst_id="SOL-USDT-SWAP", pos_side="long")
        assert result is None, "找不到持仓应该返回 None"

    run_test(result, "无匹配持仓返回 None", test_no_match_returns_none)

    def test_wrong_side_returns_none():
        """测试方向不匹配返回 None"""
        client = LighterClient(use_testnet=True)

        mock_pos = Mock()
        mock_pos.order.symbol = "XRP/USDT"
        mock_pos.order.side = "buy"

        client.get_account_positions = Mock(return_value=[mock_pos])

        result = client.get_position(inst_id="XRP-USDT-SWAP", pos_side="short")
        assert result is None, "方向不匹配应该返回 None"

    run_test(result, "方向不匹配返回 None", test_wrong_side_returns_none)

    def test_empty_positions():
        """测试无持仓时返回 None"""
        client = LighterClient(use_testnet=True)
        client.get_account_positions = Mock(return_value=[])

        result = client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="long")
        assert result is None, "无持仓应该返回 None"

    run_test(result, "无持仓返回 None", test_empty_positions)

    def test_multiple_positions():
        """测试多个持仓时正确匹配"""
        client = LighterClient(use_testnet=True)

        pos1 = Mock()
        pos1.order.symbol = "ETH/USDT"
        pos1.order.side = "buy"
        pos1.order.size = 1.0
        pos1.order.price = 3500.0

        pos2 = Mock()
        pos2.order.symbol = "EIGEN/USDT"
        pos2.order.side = "sell"
        pos2.order.size = 200.0
        pos2.order.price = 3.2

        pos3 = Mock()
        pos3.order.symbol = "TON/USDT"
        pos3.order.side = "buy"
        pos3.order.size = 1000.0
        pos3.order.price = 5.5

        client.get_account_positions = Mock(return_value=[pos1, pos2, pos3])

        result = client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="short")
        assert result is not None, "应该找到 EIGEN 空仓"
        assert result["pos"] == "200.0"
        assert result["avgPx"] == "3.2"

    run_test(result, "多个持仓时正确匹配目标持仓", test_multiple_positions)

    # ========== 测试组 3: 端到端场景 ==========
    print(f"\n{YELLOW}[3] 端到端场景测试{RESET}")

    def test_webhook_detects_existing_position():
        """模拟 webhook 检测到现有持仓"""
        client = LighterClient(use_testnet=True)

        existing_pos = Mock()
        existing_pos.order.symbol = "EIGEN/USDT"
        existing_pos.order.side = "buy"
        existing_pos.order.size = 100.0
        existing_pos.order.price = 3.2

        client.get_account_positions = Mock(return_value=[existing_pos])

        # 模拟 main.py:1755 的逻辑
        inst_id = "EIGEN-USDT-SWAP"
        pos_side = "long"

        existing_position = client.get_position(inst_id=inst_id, pos_side=pos_side)

        # 验证检测到仓位
        assert existing_position is not None, "应该检测到现有持仓"
        assert float(existing_position.get("pos", "0")) == 100.0

        # 模拟 main.py 的决策逻辑
        should_skip = (existing_position and
                      float(existing_position.get("pos", "0") or "0") != 0)
        assert should_skip is True, "应该跳过开仓"

    run_test(result, "Webhook 正确检测现有持仓并跳过", test_webhook_detects_existing_position)

    def test_webhook_proceeds_without_position():
        """模拟 webhook 无现有持仓时继续"""
        client = LighterClient(use_testnet=True)
        client.get_account_positions = Mock(return_value=[])

        inst_id = "TON-USDT-SWAP"
        pos_side = "long"

        existing_position = client.get_position(inst_id=inst_id, pos_side=pos_side)

        assert existing_position is None, "应该没有现有持仓"

        # 模拟决策逻辑
        should_proceed = (existing_position is None or
                         float(existing_position.get("pos", "0") or "0") == 0)
        assert should_proceed is True, "应该继续开仓"

    run_test(result, "Webhook 无持仓时继续开仓流程", test_webhook_proceeds_without_position)

    def test_handles_morning_signal_scenario():
        """模拟早上失败的场景（EIGEN, TON, FARTCOIN）"""
        client = LighterClient(use_testnet=True)
        client.get_account_positions = Mock(return_value=[])

        # 模拟早上的 3 种信号
        test_signals = [
            ("EIGEN-USDT-SWAP", "long"),
            ("TON-USDT-SWAP", "long"),
            ("FARTCOIN-USDT-SWAP", "long"),
        ]

        for inst_id, pos_side in test_signals:
            try:
                # 这个调用之前会崩溃
                result = client.get_position(inst_id=inst_id, pos_side=pos_side)
                # 应该成功执行（返回 None 因为无持仓）
                assert result is None
            except AttributeError:
                raise AssertionError(f"get_position 对 {inst_id} 调用失败")

    run_test(result, "处理早上失败的信号（EIGEN/TON/FARTCOIN）", test_handles_morning_signal_scenario)

    # ========== 打印总结 ==========
    success = result.summary()

    if not success:
        print(f"\n{RED}部分测试失败，请检查上述错误{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}✅ 所有测试通过！Lighter 集成已验证。{RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
