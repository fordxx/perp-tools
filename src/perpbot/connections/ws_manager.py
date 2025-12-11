"""WebSocket 统一管理器

功能:
- 统一管理多交易所 WebSocket 连接
- 自动重连机制
- 心跳检测
- 消息路由
- 连接状态监控
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class WebSocketConfig:
    """WebSocket 配置"""
    url: str
    exchange: str
    channels: List[str] = field(default_factory=list)
    ping_interval: float = 15.0
    ping_timeout: float = 10.0
    reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 10
    auth_message: Optional[dict] = None


@dataclass
class ConnectionStats:
    """连接统计"""
    exchange: str
    state: ConnectionState
    connected_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    reconnect_count: int = 0
    message_count: int = 0
    error_count: int = 0
    last_error: Optional[str] = None


class WebSocketConnection:
    """单个 WebSocket 连接管理"""

    def __init__(
        self,
        config: WebSocketConfig,
        on_message: Callable[[str, dict], None],
        on_state_change: Optional[Callable[[str, ConnectionState], None]] = None,
    ):
        self.config = config
        self.on_message = on_message
        self.on_state_change = on_state_change

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._state = ConnectionState.DISCONNECTED
        self._stats = ConnectionStats(exchange=config.exchange, state=self._state)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def stats(self) -> ConnectionStats:
        return self._stats

    def _set_state(self, state: ConnectionState):
        """更新连接状态"""
        if self._state != state:
            old_state = self._state
            self._state = state
            self._stats.state = state
            logger.debug(f"{self.config.exchange} 状态变更: {old_state.value} -> {state.value}")
            if self.on_state_change:
                self.on_state_change(self.config.exchange, state)

    async def connect(self):
        """建立连接"""
        self._set_state(ConnectionState.CONNECTING)

        try:
            self._ws = await websockets.connect(
                self.config.url,
                ping_interval=self.config.ping_interval,
                ping_timeout=self.config.ping_timeout,
            )

            self._set_state(ConnectionState.CONNECTED)
            self._stats.connected_at = datetime.utcnow()

            # 发送认证消息
            if self.config.auth_message:
                await self._ws.send(json.dumps(self.config.auth_message))

            # 订阅频道
            for channel in self.config.channels:
                sub_msg = {"op": "subscribe", "channel": channel}
                await self._ws.send(json.dumps(sub_msg))
                logger.debug(f"{self.config.exchange} 订阅: {channel}")

            logger.info(f"✅ {self.config.exchange} WebSocket 已连接")

        except Exception as e:
            self._stats.error_count += 1
            self._stats.last_error = str(e)
            self._set_state(ConnectionState.ERROR)
            raise

    async def disconnect(self):
        """断开连接"""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info(f"🔌 {self.config.exchange} WebSocket 已断开")

    async def _listen(self):
        """监听消息"""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                self._stats.message_count += 1
                self._stats.last_message_at = datetime.utcnow()

                try:
                    data = json.loads(message)
                    self.on_message(self.config.exchange, data)
                except json.JSONDecodeError:
                    logger.warning(f"{self.config.exchange} 无效 JSON: {message[:100]}")
                except Exception as e:
                    logger.error(f"{self.config.exchange} 消息处理错误: {e}")

        except ConnectionClosed as e:
            logger.warning(f"{self.config.exchange} 连接关闭: {e}")
            self._set_state(ConnectionState.DISCONNECTED)
        except Exception as e:
            logger.error(f"{self.config.exchange} 监听错误: {e}")
            self._stats.error_count += 1
            self._stats.last_error = str(e)
            self._set_state(ConnectionState.ERROR)

    async def run(self):
        """运行连接（带自动重连）"""
        self._running = True
        attempts = 0

        while self._running:
            try:
                await self.connect()
                attempts = 0  # 连接成功，重置计数
                await self._listen()

            except Exception as e:
                logger.error(f"{self.config.exchange} 错误: {e}")

            if not self._running:
                break

            # 重连逻辑
            attempts += 1
            self._stats.reconnect_count += 1

            if attempts >= self.config.max_reconnect_attempts:
                logger.error(f"{self.config.exchange} 达到最大重连次数 ({attempts})")
                self._set_state(ConnectionState.ERROR)
                break

            self._set_state(ConnectionState.RECONNECTING)
            delay = min(self.config.reconnect_delay * (2 ** (attempts - 1)), 60)
            logger.info(f"{self.config.exchange} 将在 {delay:.1f}s 后重连 (第 {attempts} 次)")
            await asyncio.sleep(delay)


class WebSocketManager:
    """WebSocket 统一管理器"""

    def __init__(self):
        self._connections: Dict[str, WebSocketConnection] = {}
        self._handlers: Dict[str, List[Callable[[str, dict], None]]] = {}
        self._state_handlers: List[Callable[[str, ConnectionState], None]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def add_exchange(self, config: WebSocketConfig):
        """添加交易所连接"""
        if config.exchange in self._connections:
            logger.warning(f"{config.exchange} 已存在，将被替换")

        conn = WebSocketConnection(
            config=config,
            on_message=self._on_message,
            on_state_change=self._on_state_change,
        )
        self._connections[config.exchange] = conn
        logger.info(f"📡 添加 WebSocket: {config.exchange}")

    def on_message(self, exchange: str, handler: Callable[[str, dict], None]):
        """注册消息处理器"""
        if exchange not in self._handlers:
            self._handlers[exchange] = []
        self._handlers[exchange].append(handler)

    def on_state_change(self, handler: Callable[[str, ConnectionState], None]):
        """注册状态变更处理器"""
        self._state_handlers.append(handler)

    def _on_message(self, exchange: str, data: dict):
        """内部消息路由"""
        handlers = self._handlers.get(exchange, [])
        for handler in handlers:
            try:
                handler(exchange, data)
            except Exception as e:
                logger.error(f"{exchange} 消息处理器错误: {e}")

        # 通用处理器 (exchange="*")
        for handler in self._handlers.get("*", []):
            try:
                handler(exchange, data)
            except Exception as e:
                logger.error(f"通用消息处理器错误: {e}")

    def _on_state_change(self, exchange: str, state: ConnectionState):
        """内部状态变更处理"""
        for handler in self._state_handlers:
            try:
                handler(exchange, state)
            except Exception as e:
                logger.error(f"状态变更处理器错误: {e}")

    async def _run_all(self):
        """运行所有连接"""
        tasks = []
        for conn in self._connections.values():
            task = asyncio.create_task(conn.run())
            tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def start(self):
        """启动所有 WebSocket 连接"""
        if self._running:
            logger.warning("WebSocketManager 已在运行")
            return

        self._running = True

        def _run_in_thread():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._run_all())
            except Exception as e:
                logger.error(f"WebSocket 事件循环错误: {e}")
            finally:
                self._loop.close()

        self._thread = threading.Thread(target=_run_in_thread, daemon=True, name="WSManager")
        self._thread.start()
        logger.info("🚀 WebSocketManager 已启动")

    def stop(self):
        """停止所有连接"""
        self._running = False

        async def _stop_all():
            for conn in self._connections.values():
                await conn.disconnect()

        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(_stop_all(), self._loop)

        if self._thread:
            self._thread.join(timeout=5.0)

        logger.info("🛑 WebSocketManager 已停止")

    def get_stats(self) -> Dict[str, ConnectionStats]:
        """获取所有连接统计"""
        return {name: conn.stats for name, conn in self._connections.items()}

    def get_state(self, exchange: str) -> Optional[ConnectionState]:
        """获取指定交易所的连接状态"""
        conn = self._connections.get(exchange)
        return conn.state if conn else None

    def is_connected(self, exchange: str) -> bool:
        """检查指定交易所是否已连接"""
        return self.get_state(exchange) == ConnectionState.CONNECTED


# 预配置的交易所 WebSocket
def create_exchange_ws_config(exchange: str, api_key: str = None) -> Optional[WebSocketConfig]:
    """创建交易所 WebSocket 配置"""
    configs = {
        "paradex": WebSocketConfig(
            url="wss://ws.prod.paradex.trade/v1",
            exchange="paradex",
            channels=["orders", "positions"],
        ),
        "extended": WebSocketConfig(
            url="wss://api.starknet.extended.exchange/stream.extended.exchange/v1",
            exchange="extended",
            channels=["account"],
        ),
        "lighter": WebSocketConfig(
            url="wss://mainnet.zklighter.elliot.ai/stream",
            exchange="lighter",
            channels=["orders", "positions"],
        ),
        "edgex": WebSocketConfig(
            url="wss://ws.edgex.exchange/ws",
            exchange="edgex",
            channels=["orders", "positions"],
        ),
        "backpack": WebSocketConfig(
            url="wss://ws.backpack.exchange",
            exchange="backpack",
            channels=["orders", "positions"],
        ),
        "grvt": WebSocketConfig(
            url="wss://trades.grvt.io/ws",
            exchange="grvt",
            channels=["orders", "fills"],
        ),
        "aster": WebSocketConfig(
            url="wss://fstream.asterdex.com/ws",
            exchange="aster",
            channels=["orders", "positions"],
        ),
    }

    config = configs.get(exchange)
    if config and api_key:
        config.auth_message = {"op": "auth", "key": api_key}

    return config


# 全局 WebSocket 管理器
_ws_manager: Optional[WebSocketManager] = None


def get_ws_manager() -> WebSocketManager:
    """获取全局 WebSocket 管理器"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager
