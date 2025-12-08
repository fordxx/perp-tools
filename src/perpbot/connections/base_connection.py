"""
BaseConnection - 基础连接抽象

定义统一的连接状态、心跳、限流与重试机制。
支持只读（行情）和读写（交易）两种模式。
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional


logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"    # 未连接
    CONNECTING = "connecting"        # 连接中
    CONNECTED = "connected"          # 已连接（健康）
    DEGRADED = "degraded"            # 降级（半开状态）
    CIRCUIT_OPEN = "circuit_open"    # 熔断开启（停止使用）


@dataclass
class ConnectionConfig:
    """连接配置"""
    # 基础配置
    name: str                              # 连接名称
    exchange: str                          # 交易所名称
    readonly: bool = True                  # 是否只读（行情连接）

    # 心跳配置
    heartbeat_interval_sec: float = 30.0   # 心跳间隔
    heartbeat_timeout_sec: float = 60.0    # 心跳超时

    # 限流配置
    rate_limit_per_sec: float = 10.0       # 每秒请求限制
    burst_size: int = 20                   # 突发容量

    # 重试配置
    max_retries: int = 3                   # 最大重试次数
    retry_base_delay_sec: float = 1.0      # 重试基础延迟
    retry_max_delay_sec: float = 30.0      # 重试最大延迟

    # 熔断配置
    max_latency_ms: float = 5000.0         # 最大延迟（毫秒）
    circuit_open_error_streak: int = 5     # 连续错误触发熔断
    circuit_halfopen_wait_sec: float = 60.0  # 熔断后等待时间

    # 健康统计窗口
    latency_window_size: int = 100         # 延迟统计窗口
    error_window_size: int = 50            # 错误统计窗口


class RateLimiter:
    """令牌桶限流器"""

    def __init__(self, rate: float, burst: int):
        """
        Args:
            rate: 每秒生成令牌数
            burst: 桶容量
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> bool:
        """
        获取令牌

        Args:
            tokens: 需要的令牌数

        Returns:
            是否成功获取
        """
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update

            # 补充令牌
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            # 检查是否有足够令牌
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

    async def wait_for_token(self, tokens: int = 1):
        """等待直到获取到令牌"""
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)


class BaseConnection:
    """
    基础连接抽象

    提供：
    - 连接状态管理
    - 心跳机制
    - 延迟统计
    - 错误追踪
    - 限流
    - 自动重试
    """

    def __init__(self, config: ConnectionConfig):
        """
        初始化连接

        Args:
            config: 连接配置
        """
        self.config = config
        self.state = ConnectionState.DISCONNECTED

        # 统计数据
        self.last_heartbeat: Optional[datetime] = None
        self.last_request: Optional[datetime] = None
        self.latencies = deque(maxlen=config.latency_window_size)
        self.error_streak = 0  # 连续错误计数
        self.total_errors = 0
        self.total_requests = 0

        # 限流器
        self.rate_limiter = RateLimiter(
            rate=config.rate_limit_per_sec,
            burst=config.burst_size,
        )

        # 熔断状态
        self.circuit_open_at: Optional[datetime] = None

        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"初始化连接: {config.name} @ {config.exchange}, "
            f"readonly={config.readonly}, rate={config.rate_limit_per_sec}/s"
        )

    @property
    def avg_latency_ms(self) -> float:
        """平均延迟（毫秒）"""
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)

    @property
    def error_rate(self) -> float:
        """错误率"""
        if self.total_requests == 0:
            return 0.0
        return self.total_errors / self.total_requests

    @property
    def is_healthy(self) -> bool:
        """是否健康"""
        return self.state in {ConnectionState.CONNECTED, ConnectionState.DEGRADED}

    @property
    def is_readonly(self) -> bool:
        """是否只读"""
        return self.config.readonly

    async def connect(self):
        """连接到交易所"""
        if self.state != ConnectionState.DISCONNECTED:
            logger.warning(f"连接 {self.config.name} 已经是 {self.state.value} 状态")
            return

        self.state = ConnectionState.CONNECTING
        logger.info(f"连接 {self.config.name}...")

        try:
            # 子类实现具体连接逻辑
            await self._do_connect()

            self.state = ConnectionState.CONNECTED
            self.last_heartbeat = datetime.utcnow()
            self._running = True

            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            logger.info(f"连接 {self.config.name} 成功")

        except Exception as e:
            self.state = ConnectionState.DISCONNECTED
            logger.error(f"连接 {self.config.name} 失败: {e}")
            raise

    async def disconnect(self):
        """断开连接"""
        logger.info(f"断开连接 {self.config.name}...")

        self._running = False

        # 停止心跳
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 子类实现具体断开逻辑
        try:
            await self._do_disconnect()
        except Exception as e:
            logger.error(f"断开连接 {self.config.name} 失败: {e}")

        self.state = ConnectionState.DISCONNECTED
        logger.info(f"连接 {self.config.name} 已断开")

    async def send_request(
        self,
        method: str,
        *args,
        retries: Optional[int] = None,
        **kwargs
    ) -> Any:
        """
        发送请求（带限流和重试）

        Args:
            method: 方法名
            *args: 位置参数
            retries: 重试次数（None=使用配置）
            **kwargs: 关键字参数

        Returns:
            响应结果

        Raises:
            Exception: 请求失败
        """
        # 检查连接状态
        if self.state == ConnectionState.CIRCUIT_OPEN:
            # 检查是否可以半开
            if self.circuit_open_at:
                elapsed = (datetime.utcnow() - self.circuit_open_at).total_seconds()
                if elapsed >= self.config.circuit_halfopen_wait_sec:
                    logger.info(f"连接 {self.config.name} 进入半开状态")
                    self.state = ConnectionState.DEGRADED
                    self.circuit_open_at = None
                else:
                    raise ConnectionError(
                        f"连接 {self.config.name} 熔断中 "
                        f"(剩余 {self.config.circuit_halfopen_wait_sec - elapsed:.0f}s)"
                    )

        if self.state == ConnectionState.DISCONNECTED:
            raise ConnectionError(f"连接 {self.config.name} 未连接")

        # 限流
        await self.rate_limiter.wait_for_token()

        # 重试逻辑
        if retries is None:
            retries = self.config.max_retries

        last_error = None
        for attempt in range(retries + 1):
            try:
                start = time.time()

                # 执行请求
                result = await self._do_request(method, *args, **kwargs)

                # 记录延迟
                latency_ms = (time.time() - start) * 1000
                self.latencies.append(latency_ms)

                # 记录成功
                self.total_requests += 1
                self.last_request = datetime.utcnow()
                self._on_success(latency_ms)

                return result

            except Exception as e:
                last_error = e

                # 记录错误
                self.total_errors += 1
                self.total_requests += 1
                self._on_error(e)

                # 判断是否重试
                if attempt < retries and self._should_retry(e):
                    delay = min(
                        self.config.retry_base_delay_sec * (2 ** attempt),
                        self.config.retry_max_delay_sec,
                    )
                    logger.warning(
                        f"请求 {self.config.name}.{method} 失败 (尝试 {attempt + 1}/{retries + 1}), "
                        f"{delay:.1f}s 后重试: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    break

        # 所有重试都失败
        logger.error(f"请求 {self.config.name}.{method} 最终失败: {last_error}")
        raise last_error

    async def heartbeat(self):
        """执行心跳检查"""
        try:
            await self._do_heartbeat()
            self.last_heartbeat = datetime.utcnow()

            logger.debug(f"心跳 {self.config.name} 成功")

        except Exception as e:
            logger.warning(f"心跳 {self.config.name} 失败: {e}")
            self._on_error(e)

    def mark_error(self, error: Exception, context: str = ""):
        """
        标记错误（外部调用）

        Args:
            error: 异常
            context: 上下文信息
        """
        self.total_errors += 1
        self._on_error(error)

        logger.warning(
            f"连接 {self.config.name} 发生错误 ({context}): {error}, "
            f"连续错误: {self.error_streak}"
        )

    def get_health_info(self) -> Dict:
        """获取健康信息"""
        return {
            "name": self.config.name,
            "exchange": self.config.exchange,
            "readonly": self.config.readonly,
            "state": self.state.value,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "last_request": self.last_request.isoformat() if self.last_request else None,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "error_streak": self.error_streak,
            "error_rate": round(self.error_rate, 4),
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "circuit_open_at": self.circuit_open_at.isoformat() if self.circuit_open_at else None,
        }

    # ==================== 内部方法 ====================

    async def _heartbeat_loop(self):
        """心跳循环"""
        while self._running:
            try:
                await asyncio.sleep(self.config.heartbeat_interval_sec)

                # 检查心跳超时
                if self.last_heartbeat:
                    elapsed = (datetime.utcnow() - self.last_heartbeat).total_seconds()
                    if elapsed > self.config.heartbeat_timeout_sec:
                        logger.error(
                            f"连接 {self.config.name} 心跳超时 ({elapsed:.0f}s)"
                        )
                        self._open_circuit("heartbeat timeout")
                        continue

                # 执行心跳
                await self.heartbeat()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳循环 {self.config.name} 异常: {e}")

    def _on_success(self, latency_ms: float):
        """处理成功请求"""
        # 重置连续错误
        if self.error_streak > 0:
            logger.info(
                f"连接 {self.config.name} 恢复正常 "
                f"(之前连续错误 {self.error_streak} 次)"
            )
        self.error_streak = 0

        # 从降级恢复
        if self.state == ConnectionState.DEGRADED:
            logger.info(f"连接 {self.config.name} 从降级恢复到正常")
            self.state = ConnectionState.CONNECTED

        # 检查延迟
        if latency_ms > self.config.max_latency_ms:
            logger.warning(
                f"连接 {self.config.name} 延迟过高: {latency_ms:.0f}ms "
                f"(阈值 {self.config.max_latency_ms:.0f}ms)"
            )

    def _on_error(self, error: Exception):
        """处理错误"""
        self.error_streak += 1

        # 检查是否触发熔断
        if self.error_streak >= self.config.circuit_open_error_streak:
            self._open_circuit(f"consecutive errors: {self.error_streak}")

    def _open_circuit(self, reason: str):
        """开启熔断"""
        if self.state != ConnectionState.CIRCUIT_OPEN:
            logger.error(
                f"⛔ 连接 {self.config.name} 触发熔断: {reason}"
            )
            self.state = ConnectionState.CIRCUIT_OPEN
            self.circuit_open_at = datetime.utcnow()

    def _should_retry(self, error: Exception) -> bool:
        """判断是否应该重试"""
        # 可以根据错误类型判断
        # 这里简单处理：网络错误和超时可以重试
        error_str = str(error).lower()
        retryable_keywords = ["timeout", "connection", "network", "temporary"]
        return any(kw in error_str for kw in retryable_keywords)

    # ==================== 子类需要实现的方法 ====================

    async def _do_connect(self):
        """子类实现：具体连接逻辑"""
        raise NotImplementedError

    async def _do_disconnect(self):
        """子类实现：具体断开逻辑"""
        pass

    async def _do_request(self, method: str, *args, **kwargs) -> Any:
        """子类实现：具体请求逻辑"""
        raise NotImplementedError

    async def _do_heartbeat(self):
        """子类实现：具体心跳逻辑"""
        # 默认实现：发送 ping 请求
        await self._do_request("ping")
