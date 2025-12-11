"""
MakerTracker - Maker 填单跟踪与降级机制

功能：
- 统计 maker 订单成交率
- 统计 maker → taker fallback 频率
- 自动降级到 SAFE_TAKER_ONLY
- 冷却期后恢复
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class MakerStats:
    """Maker 订单统计"""

    # 交易所对
    exchange_pair: str  # "binance<->okx"

    # 总尝试次数
    total_attempts: int = 0

    # 成功填单次数
    successful_fills: int = 0

    # 超时次数
    timeout_count: int = 0

    # Fallback 到 taker 次数
    fallback_count: int = 0

    # 最近一次更新时间
    last_update_ts: float = 0.0

    def get_fill_rate(self) -> float:
        """获取填单成功率"""
        if self.total_attempts == 0:
            return 1.0
        return self.successful_fills / self.total_attempts

    def get_fallback_rate(self) -> float:
        """获取 fallback 率"""
        if self.total_attempts == 0:
            return 0.0
        return self.fallback_count / self.total_attempts


@dataclass
class DegradationState:
    """降级状态"""

    # 是否已降级
    is_degraded: bool = False

    # 降级开始时间
    degraded_at: float = 0.0

    # 冷却期（秒）
    cooldown_seconds: float = 300.0  # 5 分钟

    # 降级原因
    reason: str = ""

    def is_in_cooldown(self) -> bool:
        """是否在冷却期中"""
        if not self.is_degraded:
            return False
        elapsed = time.time() - self.degraded_at
        return elapsed < self.cooldown_seconds

    def can_recover(self) -> bool:
        """是否可以恢复"""
        return self.is_degraded and not self.is_in_cooldown()


class MakerTracker:
    """
    Maker 填单跟踪器

    追踪每个交易所对的 maker 订单表现，并在表现不佳时自动降级
    """

    def __init__(
        self,
        # 降级阈值
        min_fill_rate: float = 0.5,  # 最低填单率 50%
        max_fallback_rate: float = 0.3,  # 最大 fallback 率 30%
        # 统计窗口
        window_size: int = 20,  # 最近 20 笔订单
        # 冷却期
        cooldown_seconds: float = 300.0,  # 5 分钟
    ):
        """
        初始化 Maker 跟踪器

        Args:
            min_fill_rate: 最低填单率阈值
            max_fallback_rate: 最大 fallback 率阈值
            window_size: 统计窗口大小（最近 N 笔订单）
            cooldown_seconds: 降级后的冷却期（秒）
        """
        self.min_fill_rate = min_fill_rate
        self.max_fallback_rate = max_fallback_rate
        self.window_size = window_size
        self.cooldown_seconds = cooldown_seconds

        # 存储每个交易所对的统计
        # {exchange_pair: MakerStats}
        self.stats: Dict[str, MakerStats] = {}

        # 存储最近的填单结果（用于滑动窗口）
        # {exchange_pair: deque[(is_filled, is_fallback)]}
        self.recent_results: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=window_size)
        )

        # 降级状态
        # {exchange_pair: DegradationState}
        self.degradation_states: Dict[str, DegradationState] = {}

        logger.info(
            f"初始化 MakerTracker: min_fill_rate={min_fill_rate:.1%}, "
            f"max_fallback_rate={max_fallback_rate:.1%}, "
            f"window_size={window_size}, cooldown={cooldown_seconds}s"
        )

    def _get_exchange_pair_key(self, exchange1: str, exchange2: str) -> str:
        """
        获取交易所对的键（标准化顺序）

        Args:
            exchange1: 交易所1
            exchange2: 交易所2

        Returns:
            标准化的交易所对键
        """
        # 按字母顺序排序，确保 "binance<->okx" 和 "okx<->binance" 是同一个键
        exchanges = sorted([exchange1, exchange2])
        return f"{exchanges[0]}<->{exchanges[1]}"

    def record_maker_attempt(
        self,
        exchange1: str,
        exchange2: str,
        is_filled: bool,
        is_timeout: bool = False,
        is_fallback: bool = False,
    ):
        """
        记录一次 maker 订单尝试

        Args:
            exchange1: 交易所1
            exchange2: 交易所2
            is_filled: 是否成功填单
            is_timeout: 是否超时
            is_fallback: 是否 fallback 到 taker
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)

        # 初始化统计
        if key not in self.stats:
            self.stats[key] = MakerStats(exchange_pair=key)

        stats = self.stats[key]

        # 更新统计
        stats.total_attempts += 1
        if is_filled:
            stats.successful_fills += 1
        if is_timeout:
            stats.timeout_count += 1
        if is_fallback:
            stats.fallback_count += 1
        stats.last_update_ts = time.time()

        # 记录到滑动窗口
        self.recent_results[key].append((is_filled, is_fallback))

        logger.debug(
            f"记录 maker 尝试: {key}, filled={is_filled}, "
            f"timeout={is_timeout}, fallback={is_fallback}"
        )

        # 检查是否需要降级
        self._check_degradation(key)

    def _check_degradation(self, exchange_pair: str):
        """
        检查是否需要降级

        Args:
            exchange_pair: 交易所对
        """
        # 如果已经降级且在冷却期，不再检查
        if exchange_pair in self.degradation_states:
            state = self.degradation_states[exchange_pair]
            if state.is_in_cooldown():
                return

        # 计算最近窗口的统计
        recent = self.recent_results[exchange_pair]

        # 需要至少有一定样本量
        if len(recent) < min(10, self.window_size // 2):
            return

        # 计算填单率和 fallback 率
        filled_count = sum(1 for is_filled, _ in recent if is_filled)
        fallback_count = sum(1 for _, is_fallback in recent if is_fallback)

        fill_rate = filled_count / len(recent)
        fallback_rate = fallback_count / len(recent)

        # 检查是否需要降级
        should_degrade = False
        reason = ""

        if fill_rate < self.min_fill_rate:
            should_degrade = True
            reason = f"填单率过低: {fill_rate:.1%} < {self.min_fill_rate:.1%}"

        if fallback_rate > self.max_fallback_rate:
            should_degrade = True
            if reason:
                reason += f", fallback 率过高: {fallback_rate:.1%} > {self.max_fallback_rate:.1%}"
            else:
                reason = f"fallback 率过高: {fallback_rate:.1%} > {self.max_fallback_rate:.1%}"

        if should_degrade:
            self._degrade(exchange_pair, reason)
        elif exchange_pair in self.degradation_states:
            # 表现良好，且已过冷却期，可以恢复
            state = self.degradation_states[exchange_pair]
            if state.can_recover():
                self._recover(exchange_pair)

    def _degrade(self, exchange_pair: str, reason: str):
        """
        降级到 SAFE_TAKER_ONLY

        Args:
            exchange_pair: 交易所对
            reason: 降级原因
        """
        self.degradation_states[exchange_pair] = DegradationState(
            is_degraded=True,
            degraded_at=time.time(),
            cooldown_seconds=self.cooldown_seconds,
            reason=reason,
        )

        logger.warning(
            f"🔻 降级 {exchange_pair} 到 SAFE_TAKER_ONLY: {reason}, "
            f"冷却期 {self.cooldown_seconds}s"
        )

    def _recover(self, exchange_pair: str):
        """
        从降级中恢复

        Args:
            exchange_pair: 交易所对
        """
        if exchange_pair in self.degradation_states:
            del self.degradation_states[exchange_pair]

        logger.info(f"✅ 恢复 {exchange_pair} 到正常模式")

    def is_degraded(self, exchange1: str, exchange2: str) -> bool:
        """
        检查交易所对是否已降级

        Args:
            exchange1: 交易所1
            exchange2: 交易所2

        Returns:
            是否已降级
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)

        if key not in self.degradation_states:
            return False

        state = self.degradation_states[key]

        # 如果冷却期已过，尝试恢复
        if state.can_recover():
            # 但需要等到下次记录时才真正恢复（避免立即恢复）
            pass

        return state.is_in_cooldown()

    def get_stats(self, exchange1: str, exchange2: str) -> Optional[MakerStats]:
        """
        获取交易所对的统计信息

        Args:
            exchange1: 交易所1
            exchange2: 交易所2

        Returns:
            统计信息（如果有）
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)
        return self.stats.get(key)

    def get_degradation_state(
        self, exchange1: str, exchange2: str
    ) -> Optional[DegradationState]:
        """
        获取降级状态

        Args:
            exchange1: 交易所1
            exchange2: 交易所2

        Returns:
            降级状态（如果有）
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)
        return self.degradation_states.get(key)

    def get_all_stats(self) -> Dict[str, MakerStats]:
        """获取所有统计信息"""
        return self.stats.copy()

    def get_all_degraded_pairs(self) -> Dict[str, DegradationState]:
        """获取所有已降级的交易所对"""
        return {
            k: v
            for k, v in self.degradation_states.items()
            if v.is_in_cooldown()
        }

    def reset_stats(self, exchange1: Optional[str] = None, exchange2: Optional[str] = None):
        """
        重置统计信息

        Args:
            exchange1: 交易所1（如果为 None 则重置所有）
            exchange2: 交易所2
        """
        if exchange1 is None:
            # 重置所有
            self.stats.clear()
            self.recent_results.clear()
            self.degradation_states.clear()
            logger.info("重置所有 MakerTracker 统计")
        else:
            # 重置特定交易所对
            key = self._get_exchange_pair_key(exchange1, exchange2)
            if key in self.stats:
                del self.stats[key]
            if key in self.recent_results:
                del self.recent_results[key]
            if key in self.degradation_states:
                del self.degradation_states[key]
            logger.info(f"重置 {key} 的统计")

    def force_degrade(self, exchange1: str, exchange2: str, reason: str = "手动降级"):
        """
        手动强制降级

        Args:
            exchange1: 交易所1
            exchange2: 交易所2
            reason: 降级原因
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)
        self._degrade(key, reason)

    def force_recover(self, exchange1: str, exchange2: str):
        """
        手动强制恢复

        Args:
            exchange1: 交易所1
            exchange2: 交易所2
        """
        key = self._get_exchange_pair_key(exchange1, exchange2)
        self._recover(key)
