"""
多对冲任务调度器模块 - 统一调度多交易所、多交易对的对冲成交与套利任务

该模块负责：
1. 接收来自不同策略模块（刷量、套利、做市）提交的对冲任务
2. 根据收益、风险、成交量等多维度指标计算任务优先级
3. 在资金、并发、风险约束下选择最优任务组合执行
4. 协调 CapitalOrchestrator 进行资金预留与释放
5. 提供实时调度状态监控接口
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from perpbot.capital_orchestrator import CapitalOrchestrator


class JobStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"        # 待调度
    RUNNING = "running"        # 执行中
    COMPLETED = "completed"    # 已完成
    FAILED = "failed"          # 失败
    CANCELLED = "cancelled"    # 已取消


class JobSource(Enum):
    """任务来源策略类型"""
    HEDGE_VOLUME = "hedge_volume"      # 对冲刷量
    ARBITRAGE = "arbitrage"            # 跨所套利
    MARKET_MAKING = "market_making"    # 做市
    MANUAL = "manual"                  # 手动提交


class RiskMode(Enum):
    """风险模式 - 决定评分权重"""
    CONSERVATIVE = "conservative"  # 保守：风险优先
    BALANCED = "balanced"          # 均衡：收益与风险平衡
    AGGRESSIVE = "aggressive"      # 激进：收益优先
    VOLUME_FOCUSED = "volume_focused"  # 刷量优先：成交量优先


@dataclass
class HedgeJob:
    """
    对冲任务统一数据模型

    所有策略模块通过此模型提交任务到调度器
    """
    # 基础标识
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""                    # 交易对，如 "BTC/USDT"
    exchanges: Set[str] = field(default_factory=set)  # 涉及的交易所集合

    # 资金与收益
    notional: float = 0.0               # 名义金额 (USDT)
    expected_edge_bps: float = 0.0      # 预期收益（基点，1bps = 0.01%）
    expected_pnl: float = 0.0           # 预期绝对收益 (USDT)

    # 风险与评分指标
    risk_score: float = 50.0            # 风险评分 (0-100, 越低越安全)
    latency_score: float = 50.0         # 延迟评分 (0-100, 越高执行越快)
    vol_score: float = 50.0             # 成交量贡献评分 (0-100)
    funding_score: float = 50.0         # 资金费率影响评分 (0-100, 越高越优)
    liquidity_score: float = 50.0       # 流动性评分 (0-100)

    # 任务状态
    status: JobStatus = JobStatus.PENDING
    source: JobSource = JobSource.MANUAL
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # 元数据
    metadata: Dict = field(default_factory=dict)  # 保存策略特定参数
    priority_override: Optional[float] = None     # 手动优先级覆盖

    # 执行结果
    actual_pnl: Optional[float] = None
    actual_volume: Optional[float] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        """确保 exchanges 是 set 类型"""
        if not isinstance(self.exchanges, set):
            self.exchanges = set(self.exchanges)

    def calculate_final_score(
        self,
        risk_mode: RiskMode = RiskMode.BALANCED,
        custom_weights: Optional[Dict[str, float]] = None
    ) -> float:
        """
        根据风险模式计算任务的最终评分

        Args:
            risk_mode: 风险模式，决定各指标权重
            custom_weights: 自定义权重字典，可覆盖默认值

        Returns:
            最终评分 (0-100)
        """
        # 如果有手动优先级覆盖，直接返回
        if self.priority_override is not None:
            return self.priority_override

        # 不同风险模式的默认权重配置
        weight_presets = {
            RiskMode.CONSERVATIVE: {
                "edge": 0.15,
                "pnl": 0.10,
                "risk": 0.40,      # 保守模式：风险权重最高
                "latency": 0.10,
                "volume": 0.05,
                "funding": 0.10,
                "liquidity": 0.10,
            },
            RiskMode.BALANCED: {
                "edge": 0.25,
                "pnl": 0.20,
                "risk": 0.20,
                "latency": 0.10,
                "volume": 0.10,
                "funding": 0.10,
                "liquidity": 0.05,
            },
            RiskMode.AGGRESSIVE: {
                "edge": 0.35,      # 激进模式：收益权重最高
                "pnl": 0.30,
                "risk": 0.05,
                "latency": 0.10,
                "volume": 0.05,
                "funding": 0.10,
                "liquidity": 0.05,
            },
            RiskMode.VOLUME_FOCUSED: {
                "edge": 0.10,
                "pnl": 0.05,
                "risk": 0.15,
                "latency": 0.15,
                "volume": 0.40,    # 刷量模式：成交量权重最高
                "funding": 0.10,
                "liquidity": 0.05,
            },
        }

        # 获取权重配置
        weights = weight_presets.get(risk_mode, weight_presets[RiskMode.BALANCED])
        if custom_weights:
            weights.update(custom_weights)

        # 归一化各项指标到 0-100
        edge_norm = min(100, max(0, self.expected_edge_bps * 2))  # 50bps -> 100分
        pnl_norm = min(100, max(0, self.expected_pnl / 100))      # 10000 USDT -> 100分
        risk_norm = 100 - self.risk_score  # 风险分数取反（越低风险越好）
        latency_norm = self.latency_score
        volume_norm = self.vol_score
        funding_norm = self.funding_score
        liquidity_norm = self.liquidity_score

        # 加权求和
        final_score = (
            edge_norm * weights["edge"] +
            pnl_norm * weights["pnl"] +
            risk_norm * weights["risk"] +
            latency_norm * weights["latency"] +
            volume_norm * weights["volume"] +
            funding_norm * weights["funding"] +
            liquidity_norm * weights["liquidity"]
        )

        return final_score


@dataclass
class SchedulerConfig:
    """调度器配置参数"""
    # 全局并发限制
    max_global_concurrent_jobs: int = 10
    max_concurrent_per_exchange: int = 3

    # 资金限制
    max_notional_per_exchange: float = 50000.0  # 单交易所最大在途名义金额

    # 风险模式
    risk_mode: RiskMode = RiskMode.BALANCED
    custom_weights: Optional[Dict[str, float]] = None

    # 调度策略
    min_score_threshold: float = 30.0   # 最低评分门槛
    enable_greedy_selection: bool = True  # 启用贪心选择

    # 交易所黑名单
    exchange_blacklist: Set[str] = field(default_factory=set)

    # 符号黑名单（快市/异常波动）
    symbol_blacklist: Set[str] = field(default_factory=set)


@dataclass
class SchedulerState:
    """调度器运行状态"""
    pending_jobs: List[HedgeJob] = field(default_factory=list)
    running_jobs: Dict[str, HedgeJob] = field(default_factory=dict)
    completed_jobs: List[HedgeJob] = field(default_factory=list)
    failed_jobs: List[HedgeJob] = field(default_factory=list)

    # 统计数据
    total_submitted: int = 0
    total_completed: int = 0
    total_failed: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0

    # 交易所并发计数
    exchange_running_count: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    exchange_notional: Dict[str, float] = field(default_factory=lambda: defaultdict(float))


class HedgeScheduler:
    """
    多对冲任务调度器

    核心职责：
    1. 维护候选任务池
    2. 根据多维度指标计算任务优先级
    3. 在约束条件下选择最优任务组合
    4. 协调资金预留与释放
    5. 提供状态监控接口
    """

    def __init__(
        self,
        capital_orchestrator: Optional[CapitalOrchestrator] = None,
        config: Optional[SchedulerConfig] = None
    ):
        """
        初始化调度器

        Args:
            capital_orchestrator: 资金调度器实例
            config: 调度器配置
        """
        self.capital = capital_orchestrator
        self.config = config or SchedulerConfig()
        self.state = SchedulerState()

        # 执行回调函数字典 {source: executor_func}
        self.executors: Dict[JobSource, Callable] = {}

    def register_executor(self, source: JobSource, executor_func: Callable):
        """
        注册任务执行器

        Args:
            source: 任务来源类型
            executor_func: 执行函数，签名为 executor_func(job: HedgeJob) -> dict
        """
        self.executors[source] = executor_func

    def submit_job(self, job: HedgeJob) -> str:
        """
        提交新任务到调度器

        Args:
            job: 待调度的任务

        Returns:
            job_id
        """
        self.state.pending_jobs.append(job)
        self.state.total_submitted += 1
        return job.job_id

    def cancel_job(self, job_id: str) -> bool:
        """
        取消待调度任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功取消
        """
        for i, job in enumerate(self.state.pending_jobs):
            if job.job_id == job_id:
                job.status = JobStatus.CANCELLED
                self.state.pending_jobs.pop(i)
                return True
        return False

    def _check_constraints(self, job: HedgeJob) -> tuple[bool, Optional[str]]:
        """
        检查任务是否满足硬性约束

        Returns:
            (是否通过, 拒绝原因)
        """
        # 1. 检查交易所黑名单
        for exchange in job.exchanges:
            if exchange in self.config.exchange_blacklist:
                return False, f"Exchange {exchange} is blacklisted"

        # 2. 检查符号黑名单（快市/异常波动）
        if job.symbol in self.config.symbol_blacklist:
            return False, f"Symbol {job.symbol} is blacklisted (volatile/frozen)"

        # 3. 检查全局并发限制
        if len(self.state.running_jobs) >= self.config.max_global_concurrent_jobs:
            return False, "Global concurrent limit reached"

        # 4. 检查单交易所并发限制
        for exchange in job.exchanges:
            if self.state.exchange_running_count[exchange] >= self.config.max_concurrent_per_exchange:
                return False, f"Exchange {exchange} concurrent limit reached"

        # 5. 检查单交易所在途名义金额限制
        for exchange in job.exchanges:
            if self.state.exchange_notional[exchange] + job.notional > self.config.max_notional_per_exchange:
                return False, f"Exchange {exchange} notional limit exceeded"

        # 6. 检查资金可用性（如果有 CapitalOrchestrator）
        if self.capital:
            # 尝试预览资金预留（不实际占用）
            try:
                # 这里假设 CapitalOrchestrator 有一个 can_reserve 方法
                # 实际使用时需要根据 capital_orchestrator.py 的实际接口调整
                for exchange in job.exchanges:
                    # 简化检查：假设每个交易所需要 notional / len(exchanges) 的资金
                    required = job.notional / len(job.exchanges)
                    # TODO: 调用 capital.can_reserve(exchange, required, strategy)
                    # 这里暂时跳过，因为需要查看 CapitalOrchestrator 的实际接口
                    pass
            except Exception as e:
                return False, f"Capital check failed: {e}"

        return True, None

    def tick(self) -> Dict:
        """
        调度主循环 - 执行一次调度决策

        流程：
        1. 过滤掉不满足约束的任务
        2. 计算每个候选任务的 final_score
        3. 按评分排序
        4. 贪心选择任务直到达到并发上限或无合格任务
        5. 为选中任务预留资金并提交执行

        Returns:
            本轮调度统计信息
        """
        scheduled_count = 0
        rejected_count = 0
        rejected_reasons = defaultdict(int)

        # 1. 过滤和评分候选任务
        eligible_jobs: List[tuple[HedgeJob, float]] = []

        for job in self.state.pending_jobs[:]:  # 使用切片避免迭代时修改
            # 检查硬性约束
            passed, reason = self._check_constraints(job)
            if not passed:
                rejected_count += 1
                rejected_reasons[reason] += 1
                continue

            # 计算评分
            score = job.calculate_final_score(
                risk_mode=self.config.risk_mode,
                custom_weights=self.config.custom_weights
            )

            # 检查最低评分门槛
            if score < self.config.min_score_threshold:
                rejected_count += 1
                rejected_reasons["Score below threshold"] += 1
                continue

            eligible_jobs.append((job, score))

        # 2. 按评分降序排序
        eligible_jobs.sort(key=lambda x: x[1], reverse=True)

        # 3. 贪心选择任务
        for job, score in eligible_jobs:
            # 再次检查并发限制（因为前面可能已经选了一些任务）
            if len(self.state.running_jobs) >= self.config.max_global_concurrent_jobs:
                break

            # 检查单交易所并发
            can_schedule = True
            for exchange in job.exchanges:
                if self.state.exchange_running_count[exchange] >= self.config.max_concurrent_per_exchange:
                    can_schedule = False
                    break

            if not can_schedule:
                continue

            # 4. 预留资金
            if self.capital:
                try:
                    # TODO: 调用 capital.reserve_for_strategy(...)
                    # reservation = self.capital.reserve_for_strategy(
                    #     exchanges=list(job.exchanges),
                    #     amount=job.notional,
                    #     strategy=job.source.value
                    # )
                    # job.metadata["capital_reservation"] = reservation
                    pass
                except Exception as e:
                    rejected_count += 1
                    rejected_reasons[f"Capital reservation failed: {e}"] += 1
                    continue

            # 5. 提交执行
            executor = self.executors.get(job.source)
            if executor:
                try:
                    # 更新任务状态
                    job.status = JobStatus.RUNNING
                    job.started_at = datetime.utcnow()

                    # 从待调度列表移除
                    self.state.pending_jobs.remove(job)

                    # 加入运行中列表
                    self.state.running_jobs[job.job_id] = job

                    # 更新交易所计数
                    for exchange in job.exchanges:
                        self.state.exchange_running_count[exchange] += 1
                        self.state.exchange_notional[exchange] += job.notional

                    # 异步执行（这里简化为同步调用，实际应该异步）
                    # 执行器应该在完成后调用 on_job_finished
                    executor(job)

                    scheduled_count += 1

                except Exception as e:
                    # 执行失败，回滚
                    job.status = JobStatus.FAILED
                    job.error_message = str(e)
                    self.state.running_jobs.pop(job.job_id, None)
                    for exchange in job.exchanges:
                        self.state.exchange_running_count[exchange] -= 1
                        self.state.exchange_notional[exchange] -= job.notional
                    self.state.failed_jobs.append(job)
                    self.state.total_failed += 1
            else:
                rejected_count += 1
                rejected_reasons[f"No executor for {job.source.value}"] += 1

        return {
            "scheduled": scheduled_count,
            "rejected": rejected_count,
            "rejected_reasons": dict(rejected_reasons),
            "pending": len(self.state.pending_jobs),
            "running": len(self.state.running_jobs),
        }

    def on_job_finished(self, job_id: str, result: Dict):
        """
        任务完成回调

        Args:
            job_id: 任务ID
            result: 执行结果字典，应包含：
                - success: bool
                - pnl: float (可选)
                - volume: float (可选)
                - error: str (可选)
        """
        job = self.state.running_jobs.pop(job_id, None)
        if not job:
            return

        # 更新任务状态
        job.finished_at = datetime.utcnow()

        if result.get("success"):
            job.status = JobStatus.COMPLETED
            job.actual_pnl = result.get("pnl", 0.0)
            job.actual_volume = result.get("volume", 0.0)
            self.state.completed_jobs.append(job)
            self.state.total_completed += 1
            self.state.total_pnl += job.actual_pnl or 0.0
            self.state.total_volume += job.actual_volume or 0.0
        else:
            job.status = JobStatus.FAILED
            job.error_message = result.get("error", "Unknown error")
            self.state.failed_jobs.append(job)
            self.state.total_failed += 1

        # 更新交易所计数
        for exchange in job.exchanges:
            self.state.exchange_running_count[exchange] -= 1
            self.state.exchange_notional[exchange] -= job.notional

        # 释放资金
        if self.capital and "capital_reservation" in job.metadata:
            try:
                # TODO: 调用 capital.release(job.metadata["capital_reservation"])
                pass
            except Exception as e:
                print(f"Failed to release capital: {e}")

    def get_scheduler_state(self) -> Dict:
        """
        获取调度器当前状态

        Returns:
            状态字典，用于监控面板展示
        """
        return {
            "pending_count": len(self.state.pending_jobs),
            "running_count": len(self.state.running_jobs),
            "completed_count": len(self.state.completed_jobs),
            "failed_count": len(self.state.failed_jobs),
            "total_submitted": self.state.total_submitted,
            "total_pnl": self.state.total_pnl,
            "total_volume": self.state.total_volume,
            "exchange_running": dict(self.state.exchange_running_count),
            "exchange_notional": dict(self.state.exchange_notional),
            "config": {
                "risk_mode": self.config.risk_mode.value,
                "max_global_concurrent": self.config.max_global_concurrent_jobs,
                "max_per_exchange": self.config.max_concurrent_per_exchange,
                "min_score_threshold": self.config.min_score_threshold,
            },
            "top_pending_jobs": [
                {
                    "job_id": job.job_id[:8],
                    "symbol": job.symbol,
                    "exchanges": list(job.exchanges),
                    "notional": job.notional,
                    "expected_edge_bps": job.expected_edge_bps,
                    "score": job.calculate_final_score(self.config.risk_mode),
                    "source": job.source.value,
                }
                for job in sorted(
                    self.state.pending_jobs,
                    key=lambda j: j.calculate_final_score(self.config.risk_mode),
                    reverse=True
                )[:5]
            ],
            "running_jobs": [
                {
                    "job_id": job.job_id[:8],
                    "symbol": job.symbol,
                    "exchanges": list(job.exchanges),
                    "notional": job.notional,
                    "source": job.source.value,
                    "running_seconds": (datetime.utcnow() - job.started_at).total_seconds()
                    if job.started_at else 0,
                }
                for job in self.state.running_jobs.values()
            ],
        }

    def clear_history(self, keep_recent: int = 100):
        """
        清理历史任务，只保留最近N条

        Args:
            keep_recent: 保留的最近任务数
        """
        if len(self.state.completed_jobs) > keep_recent:
            self.state.completed_jobs = self.state.completed_jobs[-keep_recent:]

        if len(self.state.failed_jobs) > keep_recent:
            self.state.failed_jobs = self.state.failed_jobs[-keep_recent:]


# ============ 调度主循环伪代码示例 ============
"""
调度器主循环执行流程：

while scheduler_running:
    # 1. 收集待调度任务
    eligible_jobs = []

    for job in pending_jobs:
        # 2. 检查硬性约束
        if not check_constraints(job):
            continue

        # 3. 计算综合评分
        score = job.calculate_final_score(risk_mode)

        if score >= min_score_threshold:
            eligible_jobs.append((job, score))

    # 4. 按评分降序排序
    eligible_jobs.sort(key=lambda x: x[1], reverse=True)

    # 5. 贪心选择任务
    for job, score in eligible_jobs:
        # 检查全局并发
        if running_count >= max_global_concurrent:
            break

        # 检查单所并发
        can_schedule = True
        for exchange in job.exchanges:
            if exchange_running[exchange] >= max_per_exchange:
                can_schedule = False
                break

        if not can_schedule:
            continue

        # 6. 预留资金
        reservation = capital.reserve_for_strategy(
            exchanges=job.exchanges,
            amount=job.notional,
            strategy=job.source
        )

        if not reservation.success:
            continue

        # 7. 提交执行
        executor = get_executor(job.source)
        executor.submit(job)

        # 8. 更新状态
        move_to_running(job)
        update_counters(job.exchanges, +1)

    # 9. 等待下一轮调度
    await asyncio.sleep(tick_interval)

# 任务完成回调
def on_job_finished(job_id, result):
    job = running_jobs.pop(job_id)

    # 更新统计
    if result.success:
        total_pnl += result.pnl
        total_volume += result.volume
        completed_jobs.append(job)
    else:
        failed_jobs.append(job)

    # 释放资金
    capital.release(job.reservation)

    # 更新计数
    update_counters(job.exchanges, -1)
"""
