"""
HealthChecker - 连接健康检查器

统一管理所有交易所连接的健康状态：
- 延迟监控
- 错误率监控
- 心跳检查
- 熔断触发
- KILL SWITCH 全局控制
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from perpbot.connections.exchange_connection_manager import ExchangeConnectionManager
from perpbot.connections.base_connection import ConnectionState


logger = logging.getLogger(__name__)


class ConnectionRegistry:
    """
    连接注册中心

    管理所有交易所的连接管理器
    """

    def __init__(self):
        """初始化连接注册中心"""
        self.exchanges: Dict[str, ExchangeConnectionManager] = {}

        # 全局 KILL SWITCH
        self.global_kill_switch = False

        # 单交易所 KILL SWITCH
        self.per_exchange_kill_switch: Dict[str, bool] = {}

        logger.info("初始化连接注册中心")

    def register(self, manager: ExchangeConnectionManager):
        """
        注册交易所连接管理器

        Args:
            manager: 连接管理器
        """
        self.exchanges[manager.exchange] = manager
        self.per_exchange_kill_switch[manager.exchange] = False
        logger.info(f"注册交易所: {manager.exchange}")

    def get(self, exchange: str) -> Optional[ExchangeConnectionManager]:
        """
        获取交易所连接管理器

        Args:
            exchange: 交易所名称

        Returns:
            连接管理器，如果不存在返回 None
        """
        return self.exchanges.get(exchange)

    def get_all(self) -> List[ExchangeConnectionManager]:
        """获取所有连接管理器"""
        return list(self.exchanges.values())

    async def connect_all(self):
        """连接所有交易所"""
        logger.info("连接所有交易所...")
        tasks = [manager.connect_all() for manager in self.exchanges.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def disconnect_all(self):
        """断开所有交易所连接"""
        logger.info("断开所有交易所连接...")
        tasks = [manager.disconnect_all() for manager in self.exchanges.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    def enable_global_kill_switch(self):
        """启用全局 KILL SWITCH"""
        self.global_kill_switch = True
        logger.critical("⛔⛔⛔ 全局 KILL SWITCH 已启用 - 所有交易停止 ⛔⛔⛔")

    def disable_global_kill_switch(self):
        """禁用全局 KILL SWITCH"""
        self.global_kill_switch = False
        logger.info("✅ 全局 KILL SWITCH 已禁用")

    def enable_exchange_kill_switch(self, exchange: str):
        """启用单交易所 KILL SWITCH"""
        self.per_exchange_kill_switch[exchange] = True

        manager = self.get(exchange)
        if manager:
            manager.enable_kill_switch()

        logger.warning(f"⛔ 交易所 {exchange} KILL SWITCH 已启用")

    def disable_exchange_kill_switch(self, exchange: str):
        """禁用单交易所 KILL SWITCH"""
        self.per_exchange_kill_switch[exchange] = False

        manager = self.get(exchange)
        if manager:
            manager.disable_kill_switch()

        logger.info(f"✅ 交易所 {exchange} KILL SWITCH 已禁用")

    def is_trading_allowed(self, exchange: str) -> bool:
        """
        检查交易所是否允许交易

        Args:
            exchange: 交易所名称

        Returns:
            是否允许交易
        """
        # 全局 KILL SWITCH
        if self.global_kill_switch:
            return False

        # 单交易所 KILL SWITCH
        if self.per_exchange_kill_switch.get(exchange, False):
            return False

        # 连接健康检查
        manager = self.get(exchange)
        if not manager:
            return False

        return manager.is_healthy()

    def get_health_summary(self) -> Dict:
        """
        获取所有交易所健康摘要

        Returns:
            健康摘要字典
        """
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "global_kill_switch": self.global_kill_switch,
            "total_exchanges": len(self.exchanges),
            "healthy_exchanges": 0,
            "degraded_exchanges": 0,
            "unhealthy_exchanges": 0,
            "exchanges": {},
        }

        for exchange, manager in self.exchanges.items():
            health = manager.get_health_snapshot()
            summary["exchanges"][exchange] = health

            # 统计健康状态
            if manager.is_healthy():
                summary["healthy_exchanges"] += 1
            elif manager.market_data_conn and manager.market_data_conn.state == ConnectionState.DEGRADED:
                summary["degraded_exchanges"] += 1
            else:
                summary["unhealthy_exchanges"] += 1

        return summary


class HealthChecker:
    """
    健康检查器

    定期检查所有连接的健康状态，触发告警
    """

    def __init__(
        self,
        registry: ConnectionRegistry,
        check_interval_sec: float = 10.0,
    ):
        """
        初始化健康检查器

        Args:
            registry: 连接注册中心
            check_interval_sec: 检查间隔（秒）
        """
        self.registry = registry
        self.check_interval_sec = check_interval_sec

        self._running = False
        self._check_task: Optional[asyncio.Task] = None

        # 告警历史（避免重复告警）
        self._alerted: Dict[str, set] = {}  # {exchange: set of alert types}

        logger.info(f"初始化健康检查器: 检查间隔={check_interval_sec}s")

    def start(self):
        """启动健康检查"""
        if self._running:
            logger.warning("健康检查器已经在运行")
            return

        self._running = True
        self._check_task = asyncio.create_task(self._check_loop())
        logger.info("健康检查器已启动")

    def stop(self):
        """停止健康检查"""
        self._running = False

        if self._check_task:
            self._check_task.cancel()

        logger.info("健康检查器已停止")

    async def _check_loop(self):
        """检查循环"""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval_sec)
                await self._check_all()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"健康检查异常: {e}")

    async def _check_all(self):
        """检查所有交易所"""
        for exchange, manager in self.registry.exchanges.items():
            await self._check_exchange(exchange, manager)

    async def _check_exchange(self, exchange: str, manager: ExchangeConnectionManager):
        """检查单个交易所"""
        if exchange not in self._alerted:
            self._alerted[exchange] = set()

        # 检查行情连接
        if manager.market_data_conn:
            await self._check_connection(
                exchange,
                manager.market_data_conn,
                "market_data",
            )

        # 检查交易连接
        if manager.trading_conn:
            await self._check_connection(
                exchange,
                manager.trading_conn,
                "trading",
            )

    async def _check_connection(
        self,
        exchange: str,
        connection,
        conn_type: str,
    ):
        """检查单个连接"""
        alert_key = f"{conn_type}:{connection.state.value}"

        # 状态变化告警
        if connection.state == ConnectionState.CIRCUIT_OPEN:
            if alert_key not in self._alerted[exchange]:
                logger.error(
                    f"⛔ 告警: {exchange} {conn_type} 连接已熔断 "
                    f"(连续错误 {connection.error_streak})"
                )
                self._alerted[exchange].add(alert_key)

        elif connection.state == ConnectionState.DEGRADED:
            if alert_key not in self._alerted[exchange]:
                logger.warning(
                    f"⚠️  告警: {exchange} {conn_type} 连接降级 "
                    f"(延迟 {connection.avg_latency_ms:.0f}ms)"
                )
                self._alerted[exchange].add(alert_key)

        elif connection.state == ConnectionState.CONNECTED:
            # 恢复正常，清除告警
            if self._alerted[exchange]:
                logger.info(f"✅ {exchange} {conn_type} 连接恢复正常")
                self._alerted[exchange].clear()

        # 延迟告警
        if connection.avg_latency_ms > connection.config.max_latency_ms:
            latency_alert = f"{conn_type}:high_latency"
            if latency_alert not in self._alerted[exchange]:
                logger.warning(
                    f"⚠️  告警: {exchange} {conn_type} 延迟过高 "
                    f"({connection.avg_latency_ms:.0f}ms > "
                    f"{connection.config.max_latency_ms:.0f}ms)"
                )
                self._alerted[exchange].add(latency_alert)

        # 错误率告警
        if connection.error_rate > 0.1:  # 10% 错误率
            error_alert = f"{conn_type}:high_error_rate"
            if error_alert not in self._alerted[exchange]:
                logger.warning(
                    f"⚠️  告警: {exchange} {conn_type} 错误率过高 "
                    f"({connection.error_rate * 100:.1f}%)"
                )
                self._alerted[exchange].add(error_alert)

    def get_unhealthy_exchanges(self) -> List[str]:
        """
        获取不健康的交易所列表

        Returns:
            交易所名称列表
        """
        unhealthy = []
        for exchange, manager in self.registry.exchanges.items():
            if not manager.is_healthy():
                unhealthy.append(exchange)
        return unhealthy

    def get_circuit_open_exchanges(self) -> List[str]:
        """
        获取熔断的交易所列表

        Returns:
            交易所名称列表
        """
        circuit_open = []
        for exchange, manager in self.registry.exchanges.items():
            if manager.market_data_conn:
                if manager.market_data_conn.state == ConnectionState.CIRCUIT_OPEN:
                    circuit_open.append(exchange)
            if manager.trading_conn:
                if manager.trading_conn.state == ConnectionState.CIRCUIT_OPEN:
                    circuit_open.append(exchange)
        return circuit_open
