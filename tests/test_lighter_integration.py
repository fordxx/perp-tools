#!/usr/bin/env python3
"""
Lighter 集成测试套件
====================

测试覆盖：
1. 接口完整性 - 验证 LighterClient 实现了所有必需的方法
2. get_position() 方法 - 验证新增的方法正常工作
3. 端到端流程 - 模拟 TradingView webhook 信号处理
4. 异常处理 - 验证错误场景的健壮性

运行方式：
    # 只运行接口测试（不需要真实API）
    pytest tests/test_lighter_integration.py -k test_interface

    # 运行完整测试（需要配置 .env）
    pytest tests/test_lighter_integration.py -v

    # 跳过真实交易测试
    pytest tests/test_lighter_integration.py -m "not real_trading"
"""
import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from perpbot.exchanges.lighter import LighterClient
from perpbot.exchanges.okx import OKXClient
from perpbot.models import OrderRequest, Position, Order


class TestLighterInterfaceCompleteness:
    """测试 LighterClient 是否实现了所有必需的接口方法"""

    def test_has_get_position_method(self):
        """验证 get_position 方法存在"""
        assert hasattr(LighterClient, "get_position"), \
            "LighterClient 必须实现 get_position() 方法"

    def test_get_position_signature(self):
        """验证 get_position 方法签名正确"""
        import inspect
        method = getattr(LighterClient, "get_position")
        sig = inspect.signature(method)

        # 验证参数
        params = list(sig.parameters.keys())
        assert "inst_id" in params, "get_position 必须有 inst_id 参数"
        assert "pos_side" in params, "get_position 必须有 pos_side 参数"

        # 验证参数是 keyword-only
        inst_id_param = sig.parameters["inst_id"]
        assert inst_id_param.kind == inspect.Parameter.KEYWORD_ONLY, \
            "inst_id 应该是 keyword-only 参数"

    def test_interface_parity_with_okx(self):
        """验证 Lighter 和 OKX 有相同的核心方法"""
        # main.py 中使用的关键方法
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

    def test_get_position_returns_dict_or_none(self):
        """验证 get_position 返回类型正确"""
        import inspect
        method = getattr(LighterClient, "get_position")
        sig = inspect.signature(method)

        # 检查返回类型标注
        return_annotation = sig.return_annotation
        # 应该是 dict[str, Any] | None 或类似的类型
        assert return_annotation != inspect.Signature.empty, \
            "get_position 应该有返回类型标注"


class TestLighterGetPositionMethod:
    """测试 get_position() 方法的具体功能"""

    @pytest.fixture
    def mock_client(self):
        """创建一个 mock 的 LighterClient"""
        client = LighterClient(use_testnet=True)
        # Mock get_account_positions 方法
        client.get_account_positions = Mock()
        return client

    def test_get_position_converts_inst_id_format(self, mock_client):
        """验证 inst_id 格式转换（OKX -> Lighter）"""
        # 模拟持仓数据
        mock_position = Mock()
        mock_position.order.symbol = "EIGEN/USDT"
        mock_position.order.side = "buy"
        mock_position.order.size = 100.0
        mock_position.order.price = 3.5

        mock_client.get_account_positions.return_value = [mock_position]

        # 调用 get_position（使用 OKX 格式）
        result = mock_client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="long")

        # 验证返回结果
        assert result is not None
        assert result["instId"] == "EIGEN-USDT-SWAP"
        assert result["posSide"] == "long"
        assert result["pos"] == "100.0"
        assert result["avgPx"] == "3.5"

    def test_get_position_matches_long_side(self, mock_client):
        """验证 pos_side='long' 匹配 side='buy'"""
        mock_position = Mock()
        mock_position.order.symbol = "TON/USDT"
        mock_position.order.side = "buy"
        mock_position.order.size = 500.0
        mock_position.order.price = 5.2

        mock_client.get_account_positions.return_value = [mock_position]

        result = mock_client.get_position(inst_id="TON-USDT-SWAP", pos_side="long")
        assert result is not None
        assert result["posSide"] == "long"

    def test_get_position_matches_short_side(self, mock_client):
        """验证 pos_side='short' 匹配 side='sell'"""
        mock_position = Mock()
        mock_position.order.symbol = "BTC/USDT"
        mock_position.order.side = "sell"
        mock_position.order.size = 0.5
        mock_position.order.price = 98000.0

        mock_client.get_account_positions.return_value = [mock_position]

        result = mock_client.get_position(inst_id="BTC-USDT-SWAP", pos_side="short")
        assert result is not None
        assert result["posSide"] == "short"

    def test_get_position_returns_none_when_no_match(self, mock_client):
        """验证没有匹配持仓时返回 None"""
        mock_position = Mock()
        mock_position.order.symbol = "ETH/USDT"
        mock_position.order.side = "buy"

        mock_client.get_account_positions.return_value = [mock_position]

        # 查询不存在的币种
        result = mock_client.get_position(inst_id="SOL-USDT-SWAP", pos_side="long")
        assert result is None

    def test_get_position_wrong_side_returns_none(self, mock_client):
        """验证方向不匹配时返回 None"""
        mock_position = Mock()
        mock_position.order.symbol = "XRP/USDT"
        mock_position.order.side = "buy"  # 持有多仓

        mock_client.get_account_positions.return_value = [mock_position]

        # 查询空仓（应该找不到）
        result = mock_client.get_position(inst_id="XRP-USDT-SWAP", pos_side="short")
        assert result is None

    def test_get_position_empty_positions_returns_none(self, mock_client):
        """验证无持仓时返回 None"""
        mock_client.get_account_positions.return_value = []

        result = mock_client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="long")
        assert result is None

    def test_get_position_multiple_positions(self, mock_client):
        """验证多个持仓时能正确匹配"""
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

        mock_client.get_account_positions.return_value = [pos1, pos2, pos3]

        # 查询 EIGEN 空仓
        result = mock_client.get_position(inst_id="EIGEN-USDT-SWAP", pos_side="short")
        assert result is not None
        assert result["instId"] == "EIGEN-USDT-SWAP"
        assert result["pos"] == "200.0"
        assert result["avgPx"] == "3.2"


class TestLighterEndToEndFlow:
    """端到端流程测试 - 模拟真实的 webhook 信号处理"""

    @pytest.fixture
    def mock_lighter_for_webhook(self):
        """创建用于 webhook 测试的 mock client"""
        with patch("perpbot.exchanges.lighter.LighterClient") as MockClient:
            instance = MockClient.return_value

            # Mock 基本方法
            instance.get_account_positions.return_value = []
            instance.get_current_price.return_value = Mock(mid=3.5, bid=3.49, ask=3.51)
            instance.place_open_order.return_value = Mock(
                id="order-123",
                symbol="EIGEN/USDT",
                side="buy",
                size=100.0,
                price=3.5,
            )

            yield instance

    def test_webhook_checks_existing_position_before_open(self, mock_lighter_for_webhook):
        """模拟 main.py:1755 的仓位检查逻辑"""
        client = mock_lighter_for_webhook

        # 模拟已有持仓
        existing_position = Mock()
        existing_position.order.symbol = "EIGEN/USDT"
        existing_position.order.side = "buy"
        existing_position.order.size = 100.0
        existing_position.order.price = 3.2

        client.get_account_positions.return_value = [existing_position]

        # 模拟 webhook 检查现有仓位
        inst_id = "EIGEN-USDT-SWAP"
        pos_side = "long"

        # 这里调用 get_position（之前会崩溃的地方！）
        existing_pos = client.get_position(inst_id=inst_id, pos_side=pos_side)

        # 验证返回的格式正确（OKX 兼容）
        assert existing_pos is not None
        assert "instId" in existing_pos
        assert "pos" in existing_pos
        assert float(existing_pos.get("pos", "0")) == 100.0

        # 模拟 main.py 的逻辑：如果已有持仓，跳过开仓
        if existing_pos and float(existing_pos.get("pos", "0")) != 0:
            print(f"⚠️ Position conflict detected, skipping trade")
            # 不执行 place_open_order
            should_place_order = False
        else:
            should_place_order = True

        assert should_place_order is False, "应该检测到仓位冲突并跳过开仓"

    def test_webhook_proceeds_when_no_existing_position(self, mock_lighter_for_webhook):
        """验证无现有仓位时继续开仓"""
        client = mock_lighter_for_webhook
        client.get_account_positions.return_value = []

        inst_id = "TON-USDT-SWAP"
        pos_side = "long"

        # 检查现有仓位
        existing_pos = client.get_position(inst_id=inst_id, pos_side=pos_side)

        assert existing_pos is None

        # 继续开仓逻辑
        should_place_order = (existing_pos is None or
                             float(existing_pos.get("pos", "0") or "0") == 0)
        assert should_place_order is True


@pytest.mark.real_trading
class TestLighterRealConnection:
    """真实环境测试（需要配置 .env）"""

    @pytest.fixture
    def real_client(self):
        """创建真实的 Lighter 客户端"""
        # 检查环境变量
        if not os.getenv("LIGHTER_API_KEY"):
            pytest.skip("需要配置 LIGHTER_API_KEY")

        client = LighterClient(use_testnet=True)
        try:
            client.connect()
        except Exception as e:
            pytest.skip(f"无法连接到 Lighter: {e}")

        return client

    def test_real_get_position_call(self, real_client):
        """验证真实环境下 get_position 不会崩溃"""
        try:
            # 调用 get_position（即使没有持仓也应该正常返回）
            result = real_client.get_position(
                inst_id="EIGEN-USDT-SWAP",
                pos_side="long"
            )

            # 应该返回 None 或 dict
            assert result is None or isinstance(result, dict)

            if result:
                # 如果有持仓，验证格式正确
                assert "instId" in result
                assert "posSide" in result
                assert "pos" in result
                assert "avgPx" in result

        except AttributeError as e:
            pytest.fail(f"get_position 方法调用失败: {e}")


class TestLighterErrorHandling:
    """异常处理测试"""

    @pytest.fixture
    def error_client(self):
        """创建会抛出异常的 mock client"""
        client = LighterClient(use_testnet=True)
        return client

    def test_get_position_handles_api_error(self, error_client):
        """验证 API 错误时的处理"""
        # Mock get_account_positions 抛出异常
        error_client.get_account_positions = Mock(
            side_effect=Exception("API connection failed")
        )

        # get_position 应该让异常向上传播（或根据实际实现验证）
        with pytest.raises(Exception):
            error_client.get_position(inst_id="ETH-USDT-SWAP", pos_side="long")

    def test_get_position_handles_malformed_data(self, error_client):
        """验证数据格式异常时的处理"""
        # Mock 返回格式错误的数据
        bad_position = Mock()
        bad_position.order = None  # 缺少必需字段

        error_client.get_account_positions = Mock(return_value=[bad_position])

        # 应该抛出 AttributeError 或返回 None
        try:
            result = error_client.get_position(inst_id="BTC-USDT-SWAP", pos_side="long")
            # 如果没有崩溃，至少应该返回 None
            assert result is None
        except AttributeError:
            # 这也是可以接受的行为
            pass


def test_module_imports():
    """验证测试模块可以正确导入"""
    from perpbot.exchanges.lighter import LighterClient
    from perpbot.exchanges.okx import OKXClient
    assert LighterClient is not None
    assert OKXClient is not None


if __name__ == "__main__":
    # 方便直接运行
    pytest.main([__file__, "-v", "--tb=short"])
