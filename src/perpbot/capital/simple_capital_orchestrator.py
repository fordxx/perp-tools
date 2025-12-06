"""
简化资金调度器 - 三层资金池模型

对外统一抽象为3层（S1/S2/S3），内部映射到传统五层系统（L1-L5）：
- S1 (wash_pool): 刷量/对冲成交主层，60-75%，内部映射 L1+L2
- S2 (arb_pool): 微利套利增强层，15-30%，内部映射 L3
- S3 (reserve_pool): 风险备用层，5-10%，内部映射 L4+L5，禁止常规调用

所有策略模块统一通过此接口访问资金，不再直接访问 L1-L5。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CapitalPool(Enum):
    """资金池类型 - 对外三层抽象"""
    S1_WASH = "S1_wash"           # 刷量对冲主层
    S2_ARB = "S2_arb"             # 套利增强层
    S3_RESERVE = "S3_reserve"     # 风险备用层


@dataclass
class PoolState:
    """单个资金池状态"""
    name: str                      # 池名称（S1/S2/S3）
    target_pct: float              # 目标占比
    pool_size: float = 0.0         # 池总额
    allocated: float = 0.0         # 已占用额度
    locked: float = 0.0            # 锁定额度（不可用）

    # 内部映射信息（调试用）
    internal_layers: List[str] = field(default_factory=list)  # 映射的 L 层

    @property
    def available(self) -> float:
        """可用额度"""
        return max(self.pool_size - self.allocated - self.locked, 0.0)

    @property
    def utilization_pct(self) -> float:
        """占用率"""
        if self.pool_size <= 0:
            return 0.0
        return (self.allocated / self.pool_size) * 100

    def allocate(self, amount: float) -> bool:
        """分配资金"""
        if amount <= self.available + 1e-9:
            self.allocated += amount
            logger.debug(
                "[%s] 分配资金 %.2f, 占用: %.2f/%.2f (%.1f%%)",
                self.name, amount, self.allocated, self.pool_size, self.utilization_pct
            )
            return True
        logger.warning(
            "[%s] 资金不足, 需要: %.2f, 可用: %.2f",
            self.name, amount, self.available
        )
        return False

    def release(self, amount: float) -> None:
        """释放资金"""
        self.allocated = max(self.allocated - amount, 0.0)
        logger.debug(
            "[%s] 释放资金 %.2f, 占用: %.2f/%.2f (%.1f%%)",
            self.name, amount, self.allocated, self.pool_size, self.utilization_pct
        )


@dataclass
class CapitalReservation:
    """资金预留凭证"""
    approved: bool                              # 是否批准
    pool: Optional[CapitalPool] = None          # 使用的池
    exchange: Optional[str] = None              # 交易所
    amount: float = 0.0                         # 金额
    reason: Optional[str] = None                # 拒绝原因


@dataclass
class ExchangeCapitalState:
    """单个交易所的资金状态"""
    exchange: str                               # 交易所名称
    equity: float                               # 总权益
    pools: Dict[str, PoolState]                 # 三层资金池
    drawdown_pct: float = 0.0                   # 回撤百分比
    safe_mode: bool = False                     # 安全模式

    # 统计数据
    total_volume: float = 0.0                   # 累计成交量
    total_fee: float = 0.0                      # 累计手续费
    realized_pnl: float = 0.0                   # 累计已实现盈亏


class SimpleCapitalOrchestrator:
    """
    简化资金调度器

    核心职责：
    1. 管理三层资金池（S1/S2/S3）
    2. 内部映射到传统五层系统（L1-L5）
    3. 提供统一的资金预留/释放接口
    4. 支持多交易所独立计算
    5. 安全模式下限制资金池访问
    """

    # 内部五层到三层的映射关系
    LAYER_MAPPING = {
        "L1": CapitalPool.S1_WASH,      # 刷量层1 → S1
        "L2": CapitalPool.S1_WASH,      # 刷量层2 → S1
        "L3": CapitalPool.S2_ARB,       # 套利层 → S2
        "L4": CapitalPool.S3_RESERVE,   # 底仓层 → S3
        "L5": CapitalPool.S3_RESERVE,   # 安全层 → S3
    }

    def __init__(
        self,
        wu_size: float = 10_000.0,
        s1_wash_pct: float = 0.70,       # S1: 70%
        s2_arb_pct: float = 0.20,        # S2: 20%
        s3_reserve_pct: float = 0.10,    # S3: 10%
        drawdown_limit_pct: float = 0.05,
        safe_mode_pools: Optional[List[CapitalPool]] = None,
    ):
        """
        初始化简化资金调度器

        Args:
            wu_size: 单个交易所基准资金（1 WU = 10,000 USDT）
            s1_wash_pct: S1 刷量池占比（默认 70%）
            s2_arb_pct: S2 套利池占比（默认 20%）
            s3_reserve_pct: S3 备用池占比（默认 10%）
            drawdown_limit_pct: 触发安全模式的回撤阈值
            safe_mode_pools: 安全模式下允许的池（默认只允许 S1 + S3）
        """
        self.wu_size = wu_size

        # 归一化三层占比
        total = s1_wash_pct + s2_arb_pct + s3_reserve_pct
        if abs(total - 1.0) > 1e-6:
            logger.warning(
                "三层占比总和 %.4f 非 1.0，自动归一化: S1=%.2f%%, S2=%.2f%%, S3=%.2f%%",
                total, s1_wash_pct/total*100, s2_arb_pct/total*100, s3_reserve_pct/total*100
            )
            s1_wash_pct /= total
            s2_arb_pct /= total
            s3_reserve_pct /= total

        self.s1_wash_pct = s1_wash_pct
        self.s2_arb_pct = s2_arb_pct
        self.s3_reserve_pct = s3_reserve_pct

        self.drawdown_limit_pct = drawdown_limit_pct
        self.safe_mode_pools = safe_mode_pools or [CapitalPool.S1_WASH, CapitalPool.S3_RESERVE]

        # 交易所资金状态字典
        self.exchange_states: Dict[str, ExchangeCapitalState] = {}

        logger.info(
            "初始化简化资金调度器: WU=%.2f, S1=%.1f%%, S2=%.1f%%, S3=%.1f%%",
            wu_size, s1_wash_pct*100, s2_arb_pct*100, s3_reserve_pct*100
        )
        logger.info(
            "内部映射: L1+L2→S1, L3→S2, L4+L5→S3"
        )

    def _ensure_exchange(self, exchange: str) -> ExchangeCapitalState:
        """确保交易所资金状态已初始化"""
        if exchange not in self.exchange_states:
            # 创建三层资金池
            pools = {
                "S1": PoolState(
                    name="S1_wash",
                    target_pct=self.s1_wash_pct,
                    pool_size=self.wu_size * self.s1_wash_pct,
                    internal_layers=["L1", "L2"],
                ),
                "S2": PoolState(
                    name="S2_arb",
                    target_pct=self.s2_arb_pct,
                    pool_size=self.wu_size * self.s2_arb_pct,
                    internal_layers=["L3"],
                ),
                "S3": PoolState(
                    name="S3_reserve",
                    target_pct=self.s3_reserve_pct,
                    pool_size=self.wu_size * self.s3_reserve_pct,
                    internal_layers=["L4", "L5"],
                ),
            }

            self.exchange_states[exchange] = ExchangeCapitalState(
                exchange=exchange,
                equity=self.wu_size,
                pools=pools,
            )

            logger.info(
                "初始化交易所 %s 资金池: S1=%.2f, S2=%.2f, S3=%.2f (总计 %.2f)",
                exchange,
                pools["S1"].pool_size,
                pools["S2"].pool_size,
                pools["S3"].pool_size,
                self.wu_size,
            )

        return self.exchange_states[exchange]

    def reserve_wash(self, exchange: str, amount: float) -> CapitalReservation:
        """
        从 S1 刷量池预留资金

        Args:
            exchange: 交易所名称
            amount: 金额

        Returns:
            资金预留凭证
        """
        logger.info("[%s] 请求从 S1_wash 预留资金: %.2f", exchange, amount)
        return self._reserve_from_pool(exchange, CapitalPool.S1_WASH, amount)

    def reserve_arb(self, exchange: str, amount: float) -> CapitalReservation:
        """
        从 S2 套利池预留资金

        Args:
            exchange: 交易所名称
            amount: 金额

        Returns:
            资金预留凭证
        """
        logger.info("[%s] 请求从 S2_arb 预留资金: %.2f", exchange, amount)
        return self._reserve_from_pool(exchange, CapitalPool.S2_ARB, amount)

    def reserve_reserve(self, exchange: str, amount: float) -> CapitalReservation:
        """
        从 S3 备用池预留资金（仅限紧急情况）

        Args:
            exchange: 交易所名称
            amount: 金额

        Returns:
            资金预留凭证
        """
        logger.warning(
            "[%s] ⚠️  请求从 S3_reserve 预留资金: %.2f (备用池仅限紧急情况)",
            exchange, amount
        )
        return self._reserve_from_pool(exchange, CapitalPool.S3_RESERVE, amount)

    def _reserve_from_pool(
        self,
        exchange: str,
        pool: CapitalPool,
        amount: float
    ) -> CapitalReservation:
        """
        从指定资金池预留资金

        Args:
            exchange: 交易所
            pool: 资金池类型
            amount: 金额

        Returns:
            预留凭证
        """
        state = self._ensure_exchange(exchange)

        # 安全模式检查
        if state.safe_mode and pool not in self.safe_mode_pools:
            reason = f"交易所 {exchange} 处于安全模式，禁止使用 {pool.value}"
            logger.warning(reason)
            return CapitalReservation(
                approved=False,
                pool=pool,
                exchange=exchange,
                amount=amount,
                reason=reason,
            )

        # 获取对应池状态
        pool_key = pool.value.split("_")[0]  # S1/S2/S3
        pool_state = state.pools.get(pool_key)

        if not pool_state:
            reason = f"资金池 {pool.value} 不存在"
            logger.error(reason)
            return CapitalReservation(
                approved=False,
                pool=pool,
                exchange=exchange,
                amount=amount,
                reason=reason,
            )

        # 尝试分配
        if pool_state.allocate(amount):
            logger.info(
                "✅ [%s] 成功从 %s 预留 %.2f (可用: %.2f, 占用率: %.1f%%)",
                exchange, pool.value, amount, pool_state.available, pool_state.utilization_pct
            )
            return CapitalReservation(
                approved=True,
                pool=pool,
                exchange=exchange,
                amount=amount,
            )
        else:
            reason = f"资金池 {pool.value} 可用额度不足（需要 {amount:.2f}, 可用 {pool_state.available:.2f}）"
            logger.warning("❌ [%s] %s", exchange, reason)
            return CapitalReservation(
                approved=False,
                pool=pool,
                exchange=exchange,
                amount=amount,
                reason=reason,
            )

    def release(self, reservation: CapitalReservation) -> None:
        """
        释放资金预留

        Args:
            reservation: 资金预留凭证
        """
        if not reservation.approved:
            return

        exchange = reservation.exchange
        pool = reservation.pool
        amount = reservation.amount

        if not exchange or not pool:
            logger.error("无效的预留凭证")
            return

        state = self.exchange_states.get(exchange)
        if not state:
            logger.error("交易所 %s 不存在", exchange)
            return

        pool_key = pool.value.split("_")[0]  # S1/S2/S3
        pool_state = state.pools.get(pool_key)

        if pool_state:
            pool_state.release(amount)
            logger.info(
                "✅ [%s] 释放 %s 资金 %.2f (剩余占用: %.2f)",
                exchange, pool.value, amount, pool_state.allocated
            )

    def update_equity(self, exchange: str, equity: float) -> None:
        """
        更新交易所权益，重新分配资金池

        Args:
            exchange: 交易所
            equity: 新权益
        """
        state = self._ensure_exchange(exchange)
        old_equity = state.equity
        state.equity = equity

        # 重新计算资金池大小（保持占用不变）
        state.pools["S1"].pool_size = equity * self.s1_wash_pct
        state.pools["S2"].pool_size = equity * self.s2_arb_pct
        state.pools["S3"].pool_size = equity * self.s3_reserve_pct

        logger.info(
            "[%s] 更新权益: %.2f → %.2f, S1=%.2f, S2=%.2f, S3=%.2f",
            exchange, old_equity, equity,
            state.pools["S1"].pool_size,
            state.pools["S2"].pool_size,
            state.pools["S3"].pool_size,
        )

    def update_drawdown(self, exchange: str, drawdown_pct: float) -> None:
        """
        更新回撤，可能触发安全模式

        Args:
            exchange: 交易所
            drawdown_pct: 回撤百分比
        """
        state = self._ensure_exchange(exchange)
        state.drawdown_pct = drawdown_pct

        # 检查是否需要进入安全模式
        if drawdown_pct >= self.drawdown_limit_pct and not state.safe_mode:
            state.safe_mode = True
            allowed = [p.value for p in self.safe_mode_pools]
            logger.warning(
                "⚠️  [%s] 回撤 %.2f%% 超过阈值 %.2f%%，触发安全模式！仅允许使用: %s",
                exchange, drawdown_pct * 100, self.drawdown_limit_pct * 100, ", ".join(allowed)
            )
        elif drawdown_pct < self.drawdown_limit_pct * 0.8 and state.safe_mode:
            # 回撤降低到阈值的 80% 以下时解除安全模式
            state.safe_mode = False
            logger.info(
                "✅ [%s] 回撤降至 %.2f%%，解除安全模式",
                exchange, drawdown_pct * 100
            )

    def record_volume_result(
        self,
        exchange: str,
        volume: float,
        fee: float,
        pnl: float
    ) -> None:
        """
        记录成交结果

        Args:
            exchange: 交易所
            volume: 成交量
            fee: 手续费
            pnl: 盈亏
        """
        state = self._ensure_exchange(exchange)
        state.total_volume += volume
        state.total_fee += fee
        state.realized_pnl += pnl

        logger.info(
            "[%s] 成交统计: volume=%.2f, fee=%.4f, pnl=%.4f | 累计: vol=%.2f, pnl=%.4f",
            exchange, volume, fee, pnl, state.total_volume, state.realized_pnl
        )

    def get_pool_state(
        self,
        exchange: str,
        pool: CapitalPool
    ) -> Optional[PoolState]:
        """
        获取指定资金池状态

        Args:
            exchange: 交易所
            pool: 资金池

        Returns:
            资金池状态
        """
        state = self.exchange_states.get(exchange)
        if not state:
            return None

        pool_key = pool.value.split("_")[0]
        return state.pools.get(pool_key)

    def get_snapshot(self) -> Dict:
        """
        获取所有交易所的资金快照（仅展示 S1/S2/S3）

        Returns:
            资金快照字典
        """
        snapshot = {}

        for exchange, state in self.exchange_states.items():
            snapshot[exchange] = {
                "equity": state.equity,
                "drawdown_pct": state.drawdown_pct,
                "safe_mode": state.safe_mode,
                "total_volume": state.total_volume,
                "total_fee": state.total_fee,
                "realized_pnl": state.realized_pnl,
                "pools": {
                    "S1_wash": {
                        "pool_size": state.pools["S1"].pool_size,
                        "allocated": state.pools["S1"].allocated,
                        "available": state.pools["S1"].available,
                        "utilization_pct": state.pools["S1"].utilization_pct,
                    },
                    "S2_arb": {
                        "pool_size": state.pools["S2"].pool_size,
                        "allocated": state.pools["S2"].allocated,
                        "available": state.pools["S2"].available,
                        "utilization_pct": state.pools["S2"].utilization_pct,
                    },
                    "S3_reserve": {
                        "pool_size": state.pools["S3"].pool_size,
                        "allocated": state.pools["S3"].allocated,
                        "available": state.pools["S3"].available,
                        "utilization_pct": state.pools["S3"].utilization_pct,
                    },
                },
            }

        return snapshot

    def get_debug_snapshot(self) -> Dict:
        """
        获取调试快照（包含内部 L1-L5 映射关系）

        Returns:
            调试快照字典
        """
        snapshot = self.get_snapshot()

        # 添加内部映射信息
        for exchange, state in self.exchange_states.items():
            snapshot[exchange]["internal_mapping"] = {
                "S1_wash": state.pools["S1"].internal_layers,
                "S2_arb": state.pools["S2"].internal_layers,
                "S3_reserve": state.pools["S3"].internal_layers,
            }

        return snapshot
