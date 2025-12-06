"""
核心资金调度器 - 三层极简模型（统一资金中枢）

按交易所维度管理三层资金：
- S1 (wash_pool):    70% - 刷量/对冲成交主层
- S2 (arb_pool):     20% - 微利套利/机会增强层
- S3 (reserve_pool): 10% - 风控备用/救火层（默认不主动使用）

核心职责：
1. 按交易所维度锁定资金
2. 支持多对刷量并发
3. 严格的资金占用约束
4. 实时 PnL 追踪
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional, Set

logger = logging.getLogger(__name__)


class PoolType(Enum):
    """资金池类型"""
    WASH = "wash"        # S1: 刷量池
    ARB = "arb"          # S2: 套利池
    RESERVE = "reserve"  # S3: 备用池


@dataclass
class PoolState:
    """单个资金池状态"""
    pool_type: PoolType
    budget_pct: float           # 目标占比
    total_budget: float = 0.0   # 总预算
    used: float = 0.0           # 已使用
    in_flight: float = 0.0      # 在途（已锁定但未完成）

    @property
    def available(self) -> float:
        """可用额度"""
        return max(self.total_budget - self.used - self.in_flight, 0.0)

    @property
    def utilization_pct(self) -> float:
        """占用率"""
        if self.total_budget <= 0:
            return 0.0
        return (self.used + self.in_flight) / self.total_budget * 100

    def can_reserve(self, amount: float, max_single_reserve_pct: float = 0.10) -> tuple[bool, Optional[str]]:
        """检查是否可以预留指定金额"""
        if amount <= 0:
            return False, "金额必须大于0"

        # 检查可用额度
        if amount > self.available:
            return False, f"可用额度不足: 需要 {amount:.2f}, 可用 {self.available:.2f}"

        # 检查单笔占用比例
        if self.total_budget > 0 and amount / self.total_budget > max_single_reserve_pct:
            return False, f"单笔占用超限: {amount/self.total_budget*100:.1f}% > {max_single_reserve_pct*100:.1f}%"

        return True, None

    def reserve(self, amount: float) -> bool:
        """预留资金（移入在途）"""
        if amount > self.available:
            return False
        self.in_flight += amount
        return True

    def confirm(self, amount: float) -> None:
        """确认使用（从在途移到已使用）"""
        transfer = min(amount, self.in_flight)
        self.in_flight -= transfer
        self.used += transfer

    def release(self, amount: float, from_in_flight: bool = True) -> None:
        """释放资金"""
        if from_in_flight:
            self.in_flight = max(self.in_flight - amount, 0.0)
        else:
            self.used = max(self.used - amount, 0.0)


@dataclass
class ExchangeCapital:
    """单个交易所的资金状态"""
    exchange: str
    total_equity: float = 0.0

    # 三层资金池
    wash_pool: PoolState = field(default=None)
    arb_pool: PoolState = field(default=None)
    reserve_pool: PoolState = field(default=None)

    # 统计数据
    today_realized_pnl: float = 0.0
    today_volume: float = 0.0
    today_fees: float = 0.0

    # 风控状态
    safe_mode: bool = False
    last_update: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """初始化资金池"""
        if self.wash_pool is None:
            self.wash_pool = PoolState(pool_type=PoolType.WASH, budget_pct=0.70)
        if self.arb_pool is None:
            self.arb_pool = PoolState(pool_type=PoolType.ARB, budget_pct=0.20)
        if self.reserve_pool is None:
            self.reserve_pool = PoolState(pool_type=PoolType.RESERVE, budget_pct=0.10)

    def get_pool(self, pool_type: PoolType | str) -> PoolState:
        """获取指定资金池"""
        if isinstance(pool_type, str):
            pool_type = PoolType(pool_type)

        if pool_type == PoolType.WASH:
            return self.wash_pool
        elif pool_type == PoolType.ARB:
            return self.arb_pool
        elif pool_type == PoolType.RESERVE:
            return self.reserve_pool
        else:
            raise ValueError(f"未知的资金池类型: {pool_type}")

    @property
    def total_in_flight(self) -> float:
        """所有在途资金总额"""
        return (self.wash_pool.in_flight +
                self.arb_pool.in_flight +
                self.reserve_pool.in_flight)

    @property
    def total_used(self) -> float:
        """所有已使用资金总额"""
        return (self.wash_pool.used +
                self.arb_pool.used +
                self.reserve_pool.used)


class CoreCapitalOrchestrator:
    """
    核心资金调度器

    按交易所维度管理三层资金池，支持并发任务调度和严格风控
    """

    def __init__(
        self,
        wash_budget_pct: float = 0.70,
        arb_budget_pct: float = 0.20,
        reserve_budget_pct: float = 0.10,
        max_single_reserve_pct: float = 0.10,    # 单笔最大占用比例
        max_total_notional_pct: float = 0.30,    # 总在途最大占用比例
        safe_mode_pools: Optional[List[PoolType]] = None,
    ):
        """
        初始化资金调度器

        Args:
            wash_budget_pct: S1 刷量池占比
            arb_budget_pct: S2 套利池占比
            reserve_budget_pct: S3 备用池占比
            max_single_reserve_pct: 单笔最大占用比例（相对于对应池）
            max_total_notional_pct: 总在途最大占用比例（相对于总权益）
            safe_mode_pools: 安全模式下允许的池（默认只允许 WASH + RESERVE）
        """
        # 归一化占比
        total = wash_budget_pct + arb_budget_pct + reserve_budget_pct
        if abs(total - 1.0) > 1e-6:
            logger.warning(f"资金占比总和 {total:.4f} 非 1.0，自动归一化")
            wash_budget_pct /= total
            arb_budget_pct /= total
            reserve_budget_pct /= total

        self.wash_budget_pct = wash_budget_pct
        self.arb_budget_pct = arb_budget_pct
        self.reserve_budget_pct = reserve_budget_pct

        self.max_single_reserve_pct = max_single_reserve_pct
        self.max_total_notional_pct = max_total_notional_pct

        self.safe_mode_pools = safe_mode_pools or [PoolType.WASH, PoolType.RESERVE]

        # 交易所资金状态
        self.exchanges: Dict[str, ExchangeCapital] = {}

        logger.info(
            f"初始化核心资金调度器: S1={wash_budget_pct*100:.1f}%, "
            f"S2={arb_budget_pct*100:.1f}%, S3={reserve_budget_pct*100:.1f}%"
        )
        logger.info(
            f"约束: 单笔≤{max_single_reserve_pct*100:.1f}%, "
            f"在途≤{max_total_notional_pct*100:.1f}%"
        )

    def _ensure_exchange(self, exchange: str, initial_equity: float = 0.0) -> ExchangeCapital:
        """确保交易所已初始化"""
        if exchange not in self.exchanges:
            capital = ExchangeCapital(exchange=exchange)
            self.exchanges[exchange] = capital

            if initial_equity > 0:
                self.update_equity(exchange, initial_equity)

            logger.info(f"初始化交易所 {exchange}")

        return self.exchanges[exchange]

    def update_equity(self, exchange: str, equity: float) -> None:
        """
        更新交易所权益并重新分配资金池

        Args:
            exchange: 交易所名称
            equity: 新的权益值
        """
        capital = self._ensure_exchange(exchange)
        old_equity = capital.total_equity
        capital.total_equity = equity
        capital.last_update = datetime.utcnow()

        # 重新分配三层资金池预算（保持已占用不变）
        capital.wash_pool.total_budget = equity * self.wash_budget_pct
        capital.arb_pool.total_budget = equity * self.arb_budget_pct
        capital.reserve_pool.total_budget = equity * self.reserve_budget_pct

        logger.info(
            f"[{exchange}] 更新权益: {old_equity:.2f} → {equity:.2f}, "
            f"S1={capital.wash_pool.total_budget:.2f}, "
            f"S2={capital.arb_pool.total_budget:.2f}, "
            f"S3={capital.reserve_pool.total_budget:.2f}"
        )

    def reserve_for_wash(self, exchange: str, amount: float) -> tuple[bool, Optional[str]]:
        """
        从 S1 刷量池预留资金

        Args:
            exchange: 交易所
            amount: 金额

        Returns:
            (是否成功, 失败原因)
        """
        capital = self._ensure_exchange(exchange)

        # 检查安全模式
        if capital.safe_mode and PoolType.WASH not in self.safe_mode_pools:
            return False, f"[{exchange}] 安全模式下禁止使用 S1_wash 池"

        # 检查总在途限制
        if not self._check_total_notional_limit(exchange, amount):
            return False, f"[{exchange}] 总在途名义金额超限"

        # 检查单笔占用限制
        can_reserve, reason = capital.wash_pool.can_reserve(amount, self.max_single_reserve_pct)
        if not can_reserve:
            return False, f"[{exchange}] S1_wash {reason}"

        # 预留
        if capital.wash_pool.reserve(amount):
            logger.info(
                f"✅ [{exchange}] 从 S1_wash 预留 {amount:.2f}, "
                f"占用率: {capital.wash_pool.utilization_pct:.1f}%"
            )
            return True, None
        else:
            return False, f"[{exchange}] S1_wash 预留失败"

    def reserve_for_arb(self, exchange: str, amount: float) -> tuple[bool, Optional[str]]:
        """
        从 S2 套利池预留资金

        Args:
            exchange: 交易所
            amount: 金额

        Returns:
            (是否成功, 失败原因)
        """
        capital = self._ensure_exchange(exchange)

        # 检查安全模式
        if capital.safe_mode and PoolType.ARB not in self.safe_mode_pools:
            return False, f"[{exchange}] 安全模式下禁止使用 S2_arb 池"

        # 检查总在途限制
        if not self._check_total_notional_limit(exchange, amount):
            return False, f"[{exchange}] 总在途名义金额超限"

        # 检查单笔占用限制
        can_reserve, reason = capital.arb_pool.can_reserve(amount, self.max_single_reserve_pct)
        if not can_reserve:
            return False, f"[{exchange}] S2_arb {reason}"

        # 预留
        if capital.arb_pool.reserve(amount):
            logger.info(
                f"✅ [{exchange}] 从 S2_arb 预留 {amount:.2f}, "
                f"占用率: {capital.arb_pool.utilization_pct:.1f}%"
            )
            return True, None
        else:
            return False, f"[{exchange}] S2_arb 预留失败"

    def release(
        self,
        exchange: str,
        amount: float,
        pool: Literal["wash", "arb", "reserve"],
        from_in_flight: bool = True
    ) -> None:
        """
        释放资金

        Args:
            exchange: 交易所
            amount: 金额
            pool: 资金池类型
            from_in_flight: 是否从在途释放（True）还是从已使用释放（False）
        """
        if exchange not in self.exchanges:
            logger.warning(f"[{exchange}] 交易所不存在，无法释放资金")
            return

        capital = self.exchanges[exchange]
        pool_state = capital.get_pool(pool)
        pool_state.release(amount, from_in_flight)

        logger.info(
            f"✅ [{exchange}] 释放 {pool.upper()} 池资金 {amount:.2f}, "
            f"占用率: {pool_state.utilization_pct:.1f}%"
        )

    def can_reserve_for_job(self, job) -> tuple[bool, Optional[str]]:
        """
        检查是否可以为任务预留资金（不实际锁定）

        Args:
            job: HedgeJob 对象（需要有 exchanges, notional, strategy_type 字段）

        Returns:
            (是否可以, 拒绝原因)
        """
        # 确定资金池类型
        pool_type = self._get_pool_type_for_job(job)

        # 检查每个交易所
        for exchange in job.exchanges:
            capital = self._ensure_exchange(exchange)
            pool_state = capital.get_pool(pool_type)

            # 安全模式检查
            if capital.safe_mode and pool_type not in self.safe_mode_pools:
                return False, f"[{exchange}] 安全模式下禁止使用 {pool_type.value} 池"

            # 单笔占用检查
            can_reserve, reason = pool_state.can_reserve(job.notional, self.max_single_reserve_pct)
            if not can_reserve:
                return False, f"[{exchange}] {reason}"

            # 总在途检查
            if not self._check_total_notional_limit(exchange, job.notional):
                return False, f"[{exchange}] 总在途名义金额超限"

        return True, None

    def reserve_for_job(self, job) -> tuple[bool, Optional[str]]:
        """
        为任务实际锁定资金

        Args:
            job: HedgeJob 对象

        Returns:
            (是否成功, 失败原因)
        """
        pool_type = self._get_pool_type_for_job(job)
        reserved_exchanges = []

        try:
            # 为每个交易所预留资金
            for exchange in job.exchanges:
                if pool_type == PoolType.WASH:
                    success, reason = self.reserve_for_wash(exchange, job.notional)
                elif pool_type == PoolType.ARB:
                    success, reason = self.reserve_for_arb(exchange, job.notional)
                else:
                    success, reason = False, f"不支持的资金池类型: {pool_type}"

                if not success:
                    # 失败，回滚已预留的
                    for prev_ex in reserved_exchanges:
                        self.release(prev_ex, job.notional, pool_type.value, from_in_flight=True)
                    return False, reason

                reserved_exchanges.append(exchange)

            # 全部成功
            logger.info(
                f"✅ [任务 {job.job_id[:8]}] 成功预留资金: "
                f"{', '.join(reserved_exchanges)} × {job.notional:.2f} from {pool_type.value}"
            )
            return True, None

        except Exception as e:
            # 异常，回滚
            for ex in reserved_exchanges:
                self.release(ex, job.notional, pool_type.value, from_in_flight=True)
            return False, f"预留资金异常: {e}"

    def record_pnl(self, exchange: str, pnl: float, volume: float = 0.0, fees: float = 0.0) -> None:
        """
        记录交易所的 PnL 和成交量

        Args:
            exchange: 交易所
            pnl: 已实现盈亏
            volume: 成交量
            fees: 手续费
        """
        capital = self._ensure_exchange(exchange)
        capital.today_realized_pnl += pnl
        capital.today_volume += volume
        capital.today_fees += fees

        logger.info(
            f"[{exchange}] 记录 PnL: {pnl:+.4f}, 成交量: {volume:.2f}, "
            f"累计 PnL: {capital.today_realized_pnl:+.4f}, 累计成交量: {capital.today_volume:.2f}"
        )

    def set_safe_mode(self, exchange: str, enabled: bool) -> None:
        """设置交易所安全模式"""
        capital = self._ensure_exchange(exchange)
        capital.safe_mode = enabled

        if enabled:
            allowed = [p.value for p in self.safe_mode_pools]
            logger.warning(
                f"⚠️  [{exchange}] 进入安全模式，仅允许使用: {', '.join(allowed)}"
            )
        else:
            logger.info(f"✅ [{exchange}] 解除安全模式")

    def current_snapshot(self) -> Dict:
        """
        获取所有交易所的资金快照

        Returns:
            资金状态字典
        """
        snapshot = {}

        for exchange, capital in self.exchanges.items():
            snapshot[exchange] = {
                "equity": capital.total_equity,
                "safe_mode": capital.safe_mode,
                "today_pnl": capital.today_realized_pnl,
                "today_volume": capital.today_volume,
                "today_fees": capital.today_fees,
                "total_in_flight": capital.total_in_flight,
                "total_used": capital.total_used,
                "pools": {
                    "S1_wash": {
                        "budget": capital.wash_pool.total_budget,
                        "used": capital.wash_pool.used,
                        "in_flight": capital.wash_pool.in_flight,
                        "available": capital.wash_pool.available,
                        "utilization_pct": capital.wash_pool.utilization_pct,
                    },
                    "S2_arb": {
                        "budget": capital.arb_pool.total_budget,
                        "used": capital.arb_pool.used,
                        "in_flight": capital.arb_pool.in_flight,
                        "available": capital.arb_pool.available,
                        "utilization_pct": capital.arb_pool.utilization_pct,
                    },
                    "S3_reserve": {
                        "budget": capital.reserve_pool.total_budget,
                        "used": capital.reserve_pool.used,
                        "in_flight": capital.reserve_pool.in_flight,
                        "available": capital.reserve_pool.available,
                        "utilization_pct": capital.reserve_pool.utilization_pct,
                    },
                },
                "last_update": capital.last_update.isoformat(),
            }

        return snapshot

    def _get_pool_type_for_job(self, job) -> PoolType:
        """根据任务类型确定资金池"""
        strategy = getattr(job, 'strategy_type', '').lower()

        if 'wash' in strategy or 'hedge' in strategy:
            return PoolType.WASH
        elif 'arb' in strategy:
            return PoolType.ARB
        else:
            # 默认使用套利池
            return PoolType.ARB

    def _check_total_notional_limit(self, exchange: str, additional_amount: float) -> bool:
        """检查总在途名义金额限制"""
        if exchange not in self.exchanges:
            return True

        capital = self.exchanges[exchange]
        if capital.total_equity <= 0:
            return True

        current_in_flight = capital.total_in_flight
        max_allowed = capital.total_equity * self.max_total_notional_pct

        if current_in_flight + additional_amount > max_allowed:
            logger.warning(
                f"[{exchange}] 总在途超限: "
                f"{current_in_flight + additional_amount:.2f} > {max_allowed:.2f} "
                f"({self.max_total_notional_pct*100:.1f}% of {capital.total_equity:.2f})"
            )
            return False

        return True
