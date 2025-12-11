"""
UnifiedMonitoringState - 统一监控状态

负责聚合系统各模块的状态信息，供监控面板和 API 查询使用。

状态层级：
1. GlobalStats: 全局统计（总PnL、成交量、活跃任务等）
2. ExchangeCapitalStats: 交易所资金状态（从 CoreCapitalOrchestrator 获取）
3. ExchangeStats: 交易所运行状态（延迟、连接状态等）
4. JobsStats: 任务统计（从 UnifiedHedgeScheduler 获取）
5. RiskStats: 风控统计（从 EnhancedRiskManager 获取）
6. MarketStats: 市场数据快照

更新机制：
- 定时拉取各模块状态 (pull)
- 各模块主动推送更新 (push)
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

from perpbot.core_capital_orchestrator import CoreCapitalOrchestrator
from perpbot.enhanced_risk_manager import EnhancedRiskManager, RiskMode
from perpbot.unified_hedge_scheduler import UnifiedHedgeScheduler


logger = logging.getLogger(__name__)


@dataclass
class GlobalStats:
    """全局统计"""
    # 时间戳
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # 总览
    total_equity: float = 0.0          # 总权益
    total_pnl: float = 0.0             # 总盈亏
    total_volume_24h: float = 0.0      # 24h成交量
    total_fees_24h: float = 0.0        # 24h手续费

    # 任务统计
    active_jobs_count: int = 0         # 活跃任务数
    pending_jobs_count: int = 0        # 待调度任务数
    completed_jobs_24h: int = 0        # 24h完成任务数
    failed_jobs_24h: int = 0           # 24h失败任务数

    # 风控状态
    risk_mode: str = "balanced"        # 风控模式
    is_daily_loss_limit_hit: bool = False  # 是否触发日亏限制
    consecutive_failures: int = 0      # 连续失败次数

    # 系统状态
    exchanges_online: int = 0          # 在线交易所数
    exchanges_total: int = 0           # 总交易所数


@dataclass
class ExchangeCapitalStats:
    """交易所资金状态"""
    exchange: str
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # 基础权益
    total_equity: float = 0.0          # 总权益

    # 三层池状态
    wash_pool_total: float = 0.0       # S1 刷量池总额
    wash_pool_available: float = 0.0   # S1 可用
    wash_pool_in_flight: float = 0.0   # S1 在途

    arb_pool_total: float = 0.0        # S2 套利池总额
    arb_pool_available: float = 0.0    # S2 可用
    arb_pool_in_flight: float = 0.0    # S2 在途

    reserve_pool_total: float = 0.0    # S3 储备池总额
    reserve_pool_available: float = 0.0 # S3 可用
    reserve_pool_in_flight: float = 0.0 # S3 在途

    # PnL
    total_pnl: float = 0.0             # 总盈亏
    total_volume: float = 0.0          # 总成交量
    total_fees: float = 0.0            # 总手续费

    # 模式
    is_safe_mode: bool = False         # 安全模式


@dataclass
class ExchangeStats:
    """交易所运行状态"""
    exchange: str
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # 连接状态
    is_connected: bool = False         # 是否连接
    last_ping_ms: float = 0.0          # 最后一次 ping 延迟

    # 并发状态
    active_jobs_count: int = 0         # 活跃任务数
    max_concurrent: int = 10           # 最大并发

    # 错误统计
    errors_last_hour: int = 0          # 最近1小时错误数


@dataclass
class JobsStats:
    """任务统计（从调度器获取）"""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # 队列状态
    pending_jobs_count: int = 0        # 待调度
    running_jobs_count: int = 0        # 运行中

    # 累计统计
    total_submitted: int = 0           # 总提交
    total_completed: int = 0           # 总完成
    total_failed: int = 0              # 总失败
    total_rejected: int = 0            # 总拒绝

    # 并发限制
    global_concurrent_limit: int = 50  # 全局并发限制
    global_concurrent_usage: int = 0   # 全局并发使用

    # 分交易所并发
    exchange_concurrent: Dict[str, int] = field(default_factory=dict)

    # 运行中任务详情（可选）
    running_jobs: List[Dict] = field(default_factory=list)


@dataclass
class RiskStats:
    """风控统计（从风控管理器获取）"""
    updated_at: datetime = field(default_factory=datetime.utcnow)

    # 风控模式
    risk_mode: str = "balanced"        # conservative/balanced/aggressive

    # 限制
    daily_loss_limit_pct: float = 0.01 # 日亏限制百分比
    daily_loss_limit_abs: float = 0.0  # 日亏限制绝对值
    max_consecutive_failures: int = 5  # 最大连续失败

    # 当前状态
    current_daily_loss: float = 0.0    # 当前日亏
    current_consecutive_failures: int = 0  # 当前连续失败
    is_daily_loss_limit_hit: bool = False  # 是否触发限制

    # Override 状态
    manual_override_enabled: bool = False  # 人工 override 是否启用


@dataclass
class MarketStats:
    """市场数据快照"""
    symbol: str
    exchange: str
    updated_at: datetime = field(default_factory=datetime.utcnow)

    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread_bps: float = 0.0            # 点差 (bps)


class UnifiedMonitoringState:
    """
    统一监控状态管理器

    聚合所有模块的状态信息，提供统一的查询接口
    """

    def __init__(
        self,
        capital: Optional[CoreCapitalOrchestrator] = None,
        risk_manager: Optional[EnhancedRiskManager] = None,
        scheduler: Optional[UnifiedHedgeScheduler] = None,
    ):
        """
        初始化监控状态管理器

        Args:
            capital: 资金调度器
            risk_manager: 风控管理器
            scheduler: 任务调度器
        """
        self.capital = capital
        self.risk_manager = risk_manager
        self.scheduler = scheduler

        # 状态数据
        self.global_stats = GlobalStats()
        self.exchange_capital_stats: Dict[str, ExchangeCapitalStats] = {}
        self.exchange_stats: Dict[str, ExchangeStats] = {}
        self.jobs_stats = JobsStats()
        self.risk_stats = RiskStats()
        self.market_stats: Dict[str, Dict[str, MarketStats]] = {}  # {symbol: {exchange: MarketStats}}

        logger.info("UnifiedMonitoringState initialized")

    def update_all(self):
        """
        更新所有状态（从各模块拉取）

        调用顺序：
        1. 更新资金状态
        2. 更新任务状态
        3. 更新风控状态
        4. 汇总全局状态
        """
        self.update_from_capital()
        self.update_from_scheduler()
        self.update_from_risk_manager()
        self.aggregate_global_stats()

        logger.debug("All monitoring states updated")

    def update_from_capital(self):
        """从资金调度器更新状态"""
        if not self.capital:
            return

        snapshot = self.capital.current_snapshot()

        # 更新各交易所资金状态
        for exchange, data in snapshot.items():
            pools = data["pools"]

            self.exchange_capital_stats[exchange] = ExchangeCapitalStats(
                exchange=exchange,
                updated_at=datetime.utcnow(),
                total_equity=data["equity"],

                wash_pool_total=pools["S1_wash"]["budget"],
                wash_pool_available=pools["S1_wash"]["available"],
                wash_pool_in_flight=pools["S1_wash"]["in_flight"],

                arb_pool_total=pools["S2_arb"]["budget"],
                arb_pool_available=pools["S2_arb"]["available"],
                arb_pool_in_flight=pools["S2_arb"]["in_flight"],

                reserve_pool_total=pools["S3_reserve"]["budget"],
                reserve_pool_available=pools["S3_reserve"]["available"],
                reserve_pool_in_flight=pools["S3_reserve"]["in_flight"],

                total_pnl=data["today_pnl"],
                total_volume=data["today_volume"],
                total_fees=data["today_fees"],

                is_safe_mode=data["safe_mode"],
            )

        logger.debug(f"Updated capital stats for {len(self.exchange_capital_stats)} exchanges")

    def update_from_scheduler(self):
        """从任务调度器更新状态"""
        if not self.scheduler:
            return

        state = self.scheduler.get_state()

        self.jobs_stats = JobsStats(
            updated_at=datetime.utcnow(),
            pending_jobs_count=state["pending_jobs_count"],
            running_jobs_count=state["running_jobs_count"],
            total_submitted=state["total_submitted"],
            total_completed=state["total_completed"],
            total_failed=state["total_failed"],
            total_rejected=state["total_rejected"],
            global_concurrent_limit=state["global_concurrent_limit"],
            global_concurrent_usage=state["global_concurrent_usage"],
            exchange_concurrent=state["exchange_concurrent"],
            running_jobs=state["running_jobs"],
        )

        logger.debug(
            f"Updated scheduler stats: {state['running_jobs_count']} running, "
            f"{state['pending_jobs_count']} pending"
        )

    def update_from_risk_manager(self):
        """从风控管理器更新状态"""
        if not self.risk_manager:
            return

        rm = self.risk_manager

        # 检查是否触发日亏限制
        is_daily_loss_hit = False
        if rm.daily_loss_limit_pct > 0 and rm.today_pnl < 0:
            if abs(rm.today_pnl) >= rm.daily_loss_limit_pct * 10000:
                is_daily_loss_hit = True
        if rm.daily_loss_limit_abs > 0 and rm.today_pnl < 0:
            if abs(rm.today_pnl) >= rm.daily_loss_limit_abs:
                is_daily_loss_hit = True

        self.risk_stats = RiskStats(
            updated_at=datetime.utcnow(),
            risk_mode=rm.risk_mode.value,
            daily_loss_limit_pct=rm.daily_loss_limit_pct,
            daily_loss_limit_abs=rm.daily_loss_limit_abs,
            max_consecutive_failures=rm.max_consecutive_failures,
            current_daily_loss=rm.today_pnl,
            current_consecutive_failures=rm.consecutive_failures,
            is_daily_loss_limit_hit=is_daily_loss_hit,
            manual_override_enabled=rm.manual_override,
        )

        logger.debug(
            f"Updated risk stats: mode={rm.risk_mode.value}, "
            f"today_pnl={rm.today_pnl:.2f}"
        )

    def aggregate_global_stats(self):
        """汇总全局统计"""
        # 汇总资金
        total_equity = sum(
            stats.total_equity
            for stats in self.exchange_capital_stats.values()
        )
        total_pnl = sum(
            stats.total_pnl
            for stats in self.exchange_capital_stats.values()
        )
        total_volume = sum(
            stats.total_volume
            for stats in self.exchange_capital_stats.values()
        )
        total_fees = sum(
            stats.total_fees
            for stats in self.exchange_capital_stats.values()
        )

        # 统计在线交易所
        exchanges_online = sum(
            1 for stats in self.exchange_stats.values()
            if stats.is_connected
        )
        exchanges_total = len(self.exchange_capital_stats)

        self.global_stats = GlobalStats(
            updated_at=datetime.utcnow(),
            total_equity=total_equity,
            total_pnl=total_pnl,
            total_volume_24h=total_volume,
            total_fees_24h=total_fees,
            active_jobs_count=self.jobs_stats.running_jobs_count,
            pending_jobs_count=self.jobs_stats.pending_jobs_count,
            completed_jobs_24h=self.jobs_stats.total_completed,
            failed_jobs_24h=self.jobs_stats.total_failed,
            risk_mode=self.risk_stats.risk_mode,
            is_daily_loss_limit_hit=self.risk_stats.is_daily_loss_limit_hit,
            consecutive_failures=self.risk_stats.current_consecutive_failures,
            exchanges_online=exchanges_online,
            exchanges_total=exchanges_total,
        )

        logger.debug(f"Aggregated global stats: equity=${total_equity:.2f}, pnl=${total_pnl:.2f}")

    def update_exchange_status(
        self,
        exchange: str,
        is_connected: bool,
        last_ping_ms: float = 0.0,
        errors_last_hour: int = 0,
    ):
        """
        手动更新交易所状态

        通常由交易所连接管理器调用
        """
        if exchange not in self.exchange_stats:
            self.exchange_stats[exchange] = ExchangeStats(exchange=exchange)

        stats = self.exchange_stats[exchange]
        stats.updated_at = datetime.utcnow()
        stats.is_connected = is_connected
        stats.last_ping_ms = last_ping_ms
        stats.errors_last_hour = errors_last_hour

        # 更新活跃任务数（从调度器获取）
        if self.scheduler:
            stats.active_jobs_count = self.scheduler.get_state()["exchange_concurrent"].get(exchange, 0)
            stats.max_concurrent = self.scheduler.max_concurrent_per_exchange

    def update_market_data(
        self,
        symbol: str,
        exchange: str,
        bid: float,
        ask: float,
        last: float,
    ):
        """
        更新市场数据快照

        Args:
            symbol: 交易对
            exchange: 交易所
            bid: 买价
            ask: 卖价
            last: 最新价
        """
        if symbol not in self.market_stats:
            self.market_stats[symbol] = {}

        spread_bps = ((ask - bid) / ((bid + ask) / 2)) * 10000 if bid > 0 else 0.0

        self.market_stats[symbol][exchange] = MarketStats(
            symbol=symbol,
            exchange=exchange,
            updated_at=datetime.utcnow(),
            bid=bid,
            ask=ask,
            last=last,
            spread_bps=spread_bps,
        )

    def to_dict(self) -> Dict:
        """
        导出完整状态为字典

        Returns:
            完整状态字典，可序列化为 JSON
        """
        return {
            "global": asdict(self.global_stats),
            "exchanges_capital": {
                ex: asdict(stats)
                for ex, stats in self.exchange_capital_stats.items()
            },
            "exchanges_status": {
                ex: asdict(stats)
                for ex, stats in self.exchange_stats.items()
            },
            "jobs": asdict(self.jobs_stats),
            "risk": asdict(self.risk_stats),
            "market": {
                symbol: {
                    ex: asdict(stats)
                    for ex, stats in exchanges.items()
                }
                for symbol, exchanges in self.market_stats.items()
            },
        }

    def get_summary(self) -> Dict:
        """
        获取摘要信息（精简版）

        Returns:
            摘要字典
        """
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "equity": self.global_stats.total_equity,
            "pnl": self.global_stats.total_pnl,
            "active_jobs": self.global_stats.active_jobs_count,
            "pending_jobs": self.global_stats.pending_jobs_count,
            "risk_mode": self.global_stats.risk_mode,
            "exchanges_online": f"{self.global_stats.exchanges_online}/{self.global_stats.exchanges_total}",
            "is_healthy": self._is_system_healthy(),
        }

    def _is_system_healthy(self) -> bool:
        """
        检查系统健康状态

        Returns:
            是否健康
        """
        # 检查是否触发风控限制
        if self.risk_stats.is_daily_loss_limit_hit:
            return False

        # 检查连续失败
        if self.risk_stats.current_consecutive_failures >= self.risk_stats.max_consecutive_failures:
            return False

        # 检查交易所连接
        if self.global_stats.exchanges_total > 0:
            if self.global_stats.exchanges_online < self.global_stats.exchanges_total * 0.5:
                return False  # 超过一半交易所离线

        return True

    def get_exchange_summary(self, exchange: str) -> Optional[Dict]:
        """
        获取单个交易所的摘要信息

        Args:
            exchange: 交易所名称

        Returns:
            交易所摘要，如果不存在返回 None
        """
        if exchange not in self.exchange_capital_stats:
            return None

        capital = self.exchange_capital_stats[exchange]
        status = self.exchange_stats.get(exchange)

        return {
            "exchange": exchange,
            "equity": capital.total_equity,
            "pnl": capital.total_pnl,
            "is_connected": status.is_connected if status else False,
            "is_safe_mode": capital.is_safe_mode,
            "active_jobs": status.active_jobs_count if status else 0,
            "pools": {
                "wash": {
                    "total": capital.wash_pool_total,
                    "available": capital.wash_pool_available,
                    "usage_pct": (capital.wash_pool_in_flight / capital.wash_pool_total * 100)
                    if capital.wash_pool_total > 0 else 0.0,
                },
                "arb": {
                    "total": capital.arb_pool_total,
                    "available": capital.arb_pool_available,
                    "usage_pct": (capital.arb_pool_in_flight / capital.arb_pool_total * 100)
                    if capital.arb_pool_total > 0 else 0.0,
                },
                "reserve": {
                    "total": capital.reserve_pool_total,
                    "available": capital.reserve_pool_available,
                    "usage_pct": (capital.reserve_pool_in_flight / capital.reserve_pool_total * 100)
                    if capital.reserve_pool_total > 0 else 0.0,
                },
            },
        }
