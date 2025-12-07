"""
ExchangeConnectionManager - 交易所连接管理器

管理单个交易所的：
- market_data_conn（只读行情连接）
- trading_conn（可下单交易连接）

提供：
- 连接健康检查
- 交易开关控制
- KILL SWITCH 支持
"""

import logging
import os
from typing import Dict, Optional

from perpbot.connections.base_connection import (
    BaseConnection,
    ConnectionConfig,
    ConnectionState,
)


logger = logging.getLogger(__name__)


class ExchangeConnectionManager:
    """
    交易所连接管理器

    管理单个交易所的行情和交易连接
    """

    def __init__(
        self,
        exchange: str,
        market_data_config: Optional[ConnectionConfig] = None,
        trading_config: Optional[ConnectionConfig] = None,
        trade_enabled: bool = False,
        api_key_env: Optional[str] = None,
        api_secret_env: Optional[str] = None,
    ):
        """
        初始化交易所连接管理器

        Args:
            exchange: 交易所名称
            market_data_config: 行情连接配置
            trading_config: 交易连接配置
            trade_enabled: 是否启用交易
            api_key_env: API Key 环境变量名
            api_secret_env: API Secret 环境变量名
        """
        self.exchange = exchange
        self.trade_enabled = trade_enabled

        # API 凭证（从环境变量读取）
        self.api_key = None
        self.api_secret = None
        if api_key_env and api_secret_env:
            self.api_key = os.environ.get(api_key_env)
            self.api_secret = os.environ.get(api_secret_env)

            if not self.api_key or not self.api_secret:
                logger.warning(
                    f"交易所 {exchange} API 凭证未设置 "
                    f"({api_key_env}, {api_secret_env})"
                )

        # 行情连接（只读，始终创建）
        self.market_data_conn: Optional[BaseConnection] = None
        if market_data_config:
            # 确保是只读
            market_data_config.readonly = True
            # 这里使用 MockConnection 作为示例，实际应该使用具体的交易所连接类
            self.market_data_conn = MockConnection(market_data_config)

        # 交易连接（可写，仅在 trade_enabled=True 且有凭证时创建）
        self.trading_conn: Optional[BaseConnection] = None
        if trade_enabled and trading_config and self.api_key and self.api_secret:
            trading_config.readonly = False
            self.trading_conn = MockConnection(trading_config)
            logger.info(f"交易所 {exchange} 交易功能已启用")
        else:
            if trade_enabled:
                logger.warning(
                    f"交易所 {exchange} trade_enabled=True 但交易连接未创建 "
                    f"(config={trading_config is not None}, "
                    f"credentials={self.api_key is not None})"
                )

        # KILL SWITCH
        self.kill_switch = False

        logger.info(
            f"初始化交易所连接管理器: {exchange}, "
            f"market_data={market_data_config is not None}, "
            f"trading={self.trading_conn is not None}, "
            f"trade_enabled={trade_enabled}"
        )

    async def ensure_market_data(self) -> BaseConnection:
        """
        确保行情连接可用

        Returns:
            行情连接对象

        Raises:
            ConnectionError: 行情连接不可用
        """
        if not self.market_data_conn:
            raise ConnectionError(f"交易所 {self.exchange} 未配置行情连接")

        # 如果未连接，尝试连接
        if self.market_data_conn.state == ConnectionState.DISCONNECTED:
            await self.market_data_conn.connect()

        # 检查熔断
        if self.market_data_conn.state == ConnectionState.CIRCUIT_OPEN:
            raise ConnectionError(
                f"交易所 {self.exchange} 行情连接已熔断"
            )

        return self.market_data_conn

    async def ensure_trading(self) -> BaseConnection:
        """
        确保交易连接可用

        Returns:
            交易连接对象

        Raises:
            ConnectionError: 交易连接不可用
        """
        # 检查 KILL SWITCH
        if self.kill_switch:
            raise ConnectionError(
                f"交易所 {self.exchange} KILL SWITCH 已启用，禁止交易"
            )

        # 检查交易开关
        if not self.trade_enabled:
            raise ConnectionError(
                f"交易所 {self.exchange} 交易功能未启用 (trade_enabled=False)"
            )

        if not self.trading_conn:
            raise ConnectionError(
                f"交易所 {self.exchange} 未配置交易连接 "
                f"(可能缺少 API 凭证)"
            )

        # 如果未连接，尝试连接
        if self.trading_conn.state == ConnectionState.DISCONNECTED:
            await self.trading_conn.connect()

        # 检查熔断
        if self.trading_conn.state == ConnectionState.CIRCUIT_OPEN:
            raise ConnectionError(
                f"交易所 {self.exchange} 交易连接已熔断"
            )

        return self.trading_conn

    async def connect_all(self):
        """连接所有连接"""
        if self.market_data_conn:
            try:
                await self.market_data_conn.connect()
            except Exception as e:
                logger.error(f"连接行情失败: {e}")

        if self.trading_conn:
            try:
                await self.trading_conn.connect()
            except Exception as e:
                logger.error(f"连接交易失败: {e}")

    async def disconnect_all(self):
        """断开所有连接"""
        if self.market_data_conn:
            try:
                await self.market_data_conn.disconnect()
            except Exception as e:
                logger.error(f"断开行情连接失败: {e}")

        if self.trading_conn:
            try:
                await self.trading_conn.disconnect()
            except Exception as e:
                logger.error(f"断开交易连接失败: {e}")

    def enable_kill_switch(self):
        """启用 KILL SWITCH（禁止新交易）"""
        self.kill_switch = True
        logger.warning(f"⛔ 交易所 {self.exchange} KILL SWITCH 已启用")

    def disable_kill_switch(self):
        """禁用 KILL SWITCH（恢复交易）"""
        self.kill_switch = False
        logger.info(f"✅ 交易所 {self.exchange} KILL SWITCH 已禁用")

    def get_health_snapshot(self) -> Dict:
        """
        获取健康快照

        Returns:
            健康信息字典
        """
        snapshot = {
            "exchange": self.exchange,
            "trade_enabled": self.trade_enabled,
            "kill_switch": self.kill_switch,
            "has_credentials": self.api_key is not None,
            "market_data": None,
            "trading": None,
        }

        if self.market_data_conn:
            snapshot["market_data"] = self.market_data_conn.get_health_info()

        if self.trading_conn:
            snapshot["trading"] = self.trading_conn.get_health_info()

        return snapshot

    def is_healthy(self) -> bool:
        """
        检查是否健康

        Returns:
            是否健康
        """
        # KILL SWITCH 启用视为不健康
        if self.kill_switch:
            return False

        # 行情连接必须健康
        if self.market_data_conn and not self.market_data_conn.is_healthy:
            return False

        # 如果启用了交易，交易连接也必须健康
        if self.trade_enabled and self.trading_conn:
            if not self.trading_conn.is_healthy:
                return False

        return True

    def get_market_data_latency(self) -> float:
        """获取行情连接延迟（毫秒）"""
        if self.market_data_conn:
            return self.market_data_conn.avg_latency_ms
        return 0.0

    def get_trading_latency(self) -> float:
        """获取交易连接延迟（毫秒）"""
        if self.trading_conn:
            return self.trading_conn.avg_latency_ms
        return 0.0


# ==================== MockConnection 用于测试 ====================

class MockConnection(BaseConnection):
    """模拟连接（用于测试和演示）"""

    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self._connected = False
        self._failure_count = 0  # 用于模拟故障

    async def _do_connect(self):
        """模拟连接"""
        import asyncio
        await asyncio.sleep(0.1)  # 模拟连接延迟
        self._connected = True
        logger.info(f"MockConnection {self.config.name} 已连接")

    async def _do_disconnect(self):
        """模拟断开"""
        self._connected = False
        logger.info(f"MockConnection {self.config.name} 已断开")

    async def _do_request(self, method: str, *args, **kwargs):
        """模拟请求"""
        import asyncio
        import random

        if not self._connected:
            raise ConnectionError("Not connected")

        # 模拟人为故障
        if self._failure_count > 0:
            self._failure_count -= 1
            raise ConnectionError(f"Simulated failure ({self._failure_count} remaining)")

        # 模拟延迟
        delay = random.uniform(0.01, 0.05)
        await asyncio.sleep(delay)

        # 模拟响应
        return {"method": method, "args": args, "kwargs": kwargs, "success": True}

    async def _do_heartbeat(self):
        """模拟心跳"""
        await self._do_request("ping")

    def simulate_failures(self, count: int):
        """模拟连续失败（用于测试熔断）"""
        self._failure_count = count
        logger.warning(f"MockConnection {self.config.name} 将模拟 {count} 次失败")
