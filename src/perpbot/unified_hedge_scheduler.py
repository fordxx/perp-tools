"""
UnifiedHedgeScheduler - 统一对冲任务调度器

核心职责：
1. 多任务调度：管理 pending/running/completed 任务队列
2. 资金协调：与 CoreCapitalOrchestrator 集成，检查和预留资金
3. 风控集成：与 EnhancedRiskManager 集成，评估任务风险
4. 并发控制：全局并发限制 + 单交易所并发限制
5. 贪心选择：按 final_score 优先级调度任务

调度流程：
1. 从 pending_jobs 获取候选任务
2. 调用 risk_manager.evaluate_job() 评估风险
3. 调用 capital.can_reserve_for_job() 检查资金
4. 按 final_score 降序排序
5. 贪心选择，检查并发限制
6. 预留资金，移入 running_jobs
7. 调用执行器（外部提供）
8. 等待 on_job_finished() 回调
"""

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set
from enum import Enum

from perpbot.core_capital_orchestrator import CoreCapitalOrchestrator
from perpbot.enhanced_risk_manager import EnhancedRiskManager, DecisionType, MarketData
from perpbot.models.hedge_job import HedgeJob


logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """任务状态"""
    PENDING = "pending"      # 等待调度
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 完成
    FAILED = "failed"        # 失败
    REJECTED = "rejected"    # 被拒绝


@dataclass
class JobResult:
    """任务执行结果"""
    job_id: str
    status: JobStatus
    pnl: float = 0.0         # 实际盈亏
    volume: float = 0.0      # 实际成交量
    fees: float = 0.0        # 实际手续费
    error: Optional[str] = None
    completed_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict = field(default_factory=dict)


@dataclass
class RunningJobInfo:
    """运行中任务信息"""
    job: HedgeJob
    started_at: datetime
    final_score: float       # 调度时的评分
    reserved_capital: Dict[str, float]  # {exchange: amount}


class UnifiedHedgeScheduler:
    """
    统一对冲任务调度器

    集成资金中枢和风控中枢，实现多任务调度
    """

    def __init__(
        self,
        capital: CoreCapitalOrchestrator,
        risk_manager: EnhancedRiskManager,
        max_global_concurrent: int = 50,
        max_concurrent_per_exchange: int = 10,
        enable_auto_schedule: bool = True,
    ):
        """
        初始化调度器

        Args:
            capital: 资金调度器
            risk_manager: 风险管理器
            max_global_concurrent: 全局最大并发任务数
            max_concurrent_per_exchange: 单交易所最大并发任务数
            enable_auto_schedule: 是否启用自动调度（tick时自动调度）
        """
        self.capital = capital
        self.risk_manager = risk_manager

        self.max_global_concurrent = max_global_concurrent
        self.max_concurrent_per_exchange = max_concurrent_per_exchange
        self.enable_auto_schedule = enable_auto_schedule

        # 任务队列
        self.pending_jobs: deque[HedgeJob] = deque()
        self.running_jobs: Dict[str, RunningJobInfo] = {}
        self.completed_jobs: deque[JobResult] = deque(maxlen=1000)  # 保留最近1000个结果

        # 统计
        self.total_submitted = 0
        self.total_completed = 0
        self.total_failed = 0
        self.total_rejected = 0

        # 执行器回调（由外部提供）
        self.executor_callback: Optional[Callable[[HedgeJob], None]] = None

        logger.info(
            f"UnifiedHedgeScheduler initialized: "
            f"max_global={max_global_concurrent}, "
            f"max_per_exchange={max_concurrent_per_exchange}"
        )

    def set_executor(self, executor: Callable[[HedgeJob], None]):
        """
        设置任务执行器

        executor 应该是一个异步函数，接收 HedgeJob 并执行，
        完成后调用 on_job_finished()
        """
        self.executor_callback = executor
        logger.info("Executor callback registered")

    def submit_job(self, job: HedgeJob) -> tuple[bool, Optional[str]]:
        """
        提交任务到调度队列

        Args:
            job: HedgeJob 实例

        Returns:
            (success, error_message)
        """
        # 验证任务
        is_valid, error = job.validate()
        if not is_valid:
            logger.warning(f"Job validation failed: {error}")
            self.total_rejected += 1
            return False, f"Validation failed: {error}"

        # 加入队列
        self.pending_jobs.append(job)
        self.total_submitted += 1

        logger.info(
            f"Job submitted: {job.job_id[:8]}... "
            f"({job.strategy_type}, {job.symbol}, {len(job.legs)} legs)"
        )

        return True, None

    def tick(self, market_data: Optional[Dict[str, Dict[str, MarketData]]] = None) -> Dict:
        """
        调度主循环（单次调度）

        每次调用会尝试调度 pending_jobs 中的任务

        Args:
            market_data: {symbol: {exchange: MarketData}}

        Returns:
            调度结果统计
        """
        if not self.enable_auto_schedule:
            return {"skipped": True, "reason": "auto_schedule disabled"}

        if not market_data:
            market_data = {}

        # 统计
        scheduled_count = 0
        rejected_count = 0
        skipped_count = 0

        # 获取当前并发状态
        current_global = len(self.running_jobs)
        exchange_concurrent = self._get_exchange_concurrent_counts()

        # 如果全局并发已满，跳过调度
        if current_global >= self.max_global_concurrent:
            logger.debug(f"Global concurrent limit reached: {current_global}/{self.max_global_concurrent}")
            return {
                "scheduled": 0,
                "rejected": 0,
                "skipped": len(self.pending_jobs),
                "reason": "global_concurrent_limit",
            }

        # 评估所有待调度任务
        candidates = []

        for job in list(self.pending_jobs):
            # 风险评估
            job_market_data = market_data.get(job.symbol, {})
            evaluation = self.risk_manager.evaluate_job(job, job_market_data)

            # 硬拒绝（风控不通过）
            if evaluation.decision == DecisionType.REJECT:
                logger.info(
                    f"Job {job.job_id[:8]}... rejected by risk manager: {evaluation.reason}"
                )
                self.pending_jobs.remove(job)
                self.completed_jobs.append(JobResult(
                    job_id=job.job_id,
                    status=JobStatus.REJECTED,
                    error=evaluation.reason,
                ))
                self.total_rejected += 1
                rejected_count += 1
                continue

            # 资金检查
            can_reserve, reason = self.capital.can_reserve_for_job(job)
            if not can_reserve:
                logger.debug(f"Job {job.job_id[:8]}... skipped: {reason}")
                skipped_count += 1
                continue

            # 加入候选列表
            candidates.append((job, evaluation.final_score))

        # 按 final_score 降序排序
        candidates.sort(key=lambda x: x[1], reverse=True)

        # 贪心选择
        for job, score in candidates:
            # 检查全局并发
            if len(self.running_jobs) >= self.max_global_concurrent:
                break

            # 检查交易所并发
            if not self._can_run_on_exchanges(job.exchanges, exchange_concurrent):
                logger.debug(
                    f"Job {job.job_id[:8]}... skipped: exchange concurrent limit"
                )
                skipped_count += 1
                continue

            # 预留资金（再次检查，因为之前的任务可能已经占用）
            success, reason = self.capital.reserve_for_job(job)
            if not success:
                logger.debug(f"Job {job.job_id[:8]}... reservation failed: {reason}")
                skipped_count += 1
                continue

            # 移入 running_jobs
            self.pending_jobs.remove(job)
            self.running_jobs[job.job_id] = RunningJobInfo(
                job=job,
                started_at=datetime.utcnow(),
                final_score=score,
                reserved_capital={ex: job.notional for ex in job.exchanges},
            )

            # 更新交易所并发计数
            for exchange in job.exchanges:
                exchange_concurrent[exchange] += 1

            scheduled_count += 1

            logger.info(
                f"Job {job.job_id[:8]}... scheduled: "
                f"score={score:.2f}, exchanges={job.exchanges}"
            )

            # 调用执行器
            if self.executor_callback:
                try:
                    self.executor_callback(job)
                except Exception as e:
                    logger.error(f"Executor callback failed for {job.job_id[:8]}...: {e}")
                    # 如果执行器失败，标记为失败并释放资金
                    self.on_job_finished(job.job_id, JobResult(
                        job_id=job.job_id,
                        status=JobStatus.FAILED,
                        error=f"Executor error: {e}",
                    ))

        return {
            "scheduled": scheduled_count,
            "rejected": rejected_count,
            "skipped": skipped_count,
            "pending_remaining": len(self.pending_jobs),
            "running_total": len(self.running_jobs),
        }

    def on_job_finished(self, job_id: str, result: JobResult):
        """
        任务完成回调

        由执行器调用，通知调度器任务已完成

        Args:
            job_id: 任务ID
            result: 执行结果
        """
        if job_id not in self.running_jobs:
            logger.warning(f"on_job_finished called for unknown job: {job_id}")
            return

        job_info = self.running_jobs.pop(job_id)
        job = job_info.job

        # 释放资金
        for exchange in job.exchanges:
            pool = "wash" if job.strategy_type in ["wash", "hedge_rebalance"] else "arb"
            self.capital.release(exchange, job.notional, pool, from_in_flight=True)

        # 记录 PnL
        if result.status == JobStatus.COMPLETED:
            for exchange in job.exchanges:
                self.capital.record_pnl(exchange, result.pnl, result.volume, result.fees)
            self.total_completed += 1
            self.risk_manager.record_success()
            logger.info(
                f"Job {job_id[:8]}... completed: "
                f"pnl=${result.pnl:.2f}, volume=${result.volume:.0f}"
            )
        else:
            self.total_failed += 1
            self.risk_manager.record_failure(result.error or "Unknown error")
            logger.warning(f"Job {job_id[:8]}... failed: {result.error}")

        # 保存结果
        self.completed_jobs.append(result)

    def get_state(self) -> Dict:
        """
        获取调度器状态

        Returns:
            状态字典
        """
        exchange_concurrent = self._get_exchange_concurrent_counts()

        return {
            "pending_jobs_count": len(self.pending_jobs),
            "running_jobs_count": len(self.running_jobs),
            "completed_jobs_count": len(self.completed_jobs),
            "total_submitted": self.total_submitted,
            "total_completed": self.total_completed,
            "total_failed": self.total_failed,
            "total_rejected": self.total_rejected,
            "global_concurrent_limit": self.max_global_concurrent,
            "global_concurrent_usage": len(self.running_jobs),
            "exchange_concurrent": dict(exchange_concurrent),
            "running_jobs": [
                {
                    "job_id": job_id,
                    "strategy_type": info.job.strategy_type,
                    "symbol": info.job.symbol,
                    "exchanges": list(info.job.exchanges),
                    "notional": info.job.notional,
                    "score": info.final_score,
                    "started_at": info.started_at.isoformat(),
                }
                for job_id, info in self.running_jobs.items()
            ],
        }

    def _get_exchange_concurrent_counts(self) -> Dict[str, int]:
        """获取各交易所当前并发任务数"""
        counts = defaultdict(int)
        for info in self.running_jobs.values():
            for exchange in info.job.exchanges:
                counts[exchange] += 1
        return counts

    def _can_run_on_exchanges(
        self,
        exchanges: Set[str],
        current_counts: Dict[str, int],
    ) -> bool:
        """
        检查是否可以在指定交易所上运行任务

        Args:
            exchanges: 任务涉及的交易所
            current_counts: 当前各交易所并发数

        Returns:
            是否可以运行
        """
        for exchange in exchanges:
            if current_counts.get(exchange, 0) >= self.max_concurrent_per_exchange:
                return False
        return True

    def pause_auto_schedule(self):
        """暂停自动调度"""
        self.enable_auto_schedule = False
        logger.info("Auto schedule paused")

    def resume_auto_schedule(self):
        """恢复自动调度"""
        self.enable_auto_schedule = True
        logger.info("Auto schedule resumed")

    def cancel_pending_job(self, job_id: str) -> bool:
        """
        取消待调度任务

        Args:
            job_id: 任务ID

        Returns:
            是否成功
        """
        for job in list(self.pending_jobs):
            if job.job_id == job_id:
                self.pending_jobs.remove(job)
                logger.info(f"Pending job {job_id[:8]}... cancelled")
                return True
        return False

    def clear_completed_jobs(self):
        """清空已完成任务历史"""
        count = len(self.completed_jobs)
        self.completed_jobs.clear()
        logger.info(f"Cleared {count} completed jobs")
