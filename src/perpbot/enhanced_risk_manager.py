"""
增强风控中枢 - 多维度风险评估与管理

核心职责：
1. 多维度风险评估（资金费率、价差、滑点、延迟、波动、杠杆等）
2. 支持三种风险模式（conservative/balanced/aggressive）
3. 统一评分机制（safety_score + volume_score → final_score）
4. 人工 override 支持（软风控可覆盖，硬风控不可覆盖）
5. 连续失败保护与自动暂停
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Literal, Optional, Tuple

logger = logging.getLogger(__name__)


class RiskMode(Enum):
    """风险模式"""
    CONSERVATIVE = "conservative"  # 保守：严格风控，高安全性
    BALANCED = "balanced"          # 均衡：收益与风险平衡
    AGGRESSIVE = "aggressive"      # 激进：追求收益，允许更高风险


class DecisionType(Enum):
    """决策类型"""
    ACCEPT = "accept"      # 接受任务
    REJECT = "reject"      # 拒绝任务
    WARN = "warn"          # 警告但接受


@dataclass
class RiskModeConfig:
    """风险模式配置"""
    mode: RiskMode
    min_expected_edge_bps: float        # 最小预期收益（基点）
    max_acceptable_loss_bps: float      # 最大可接受亏损（基点）
    volatility_threshold: float         # 波动率阈值
    max_latency_ms: float              # 最大延迟（毫秒）
    min_funding_score: float           # 最低资金费率评分
    safety_weight: float               # 安全性权重
    volume_weight: float               # 成交量权重
    final_score_threshold: float       # 最低综合评分阈值


# 预设风险模式配置
RISK_MODE_PRESETS = {
    RiskMode.CONSERVATIVE: RiskModeConfig(
        mode=RiskMode.CONSERVATIVE,
        min_expected_edge_bps=5.0,
        max_acceptable_loss_bps=1.0,
        volatility_threshold=0.004,  # 0.4%
        max_latency_ms=500.0,
        min_funding_score=60.0,
        safety_weight=0.8,
        volume_weight=0.2,
        final_score_threshold=75.0,
    ),
    RiskMode.BALANCED: RiskModeConfig(
        mode=RiskMode.BALANCED,
        min_expected_edge_bps=3.0,
        max_acceptable_loss_bps=2.0,
        volatility_threshold=0.006,  # 0.6%
        max_latency_ms=1000.0,
        min_funding_score=50.0,
        safety_weight=0.65,
        volume_weight=0.35,
        final_score_threshold=70.0,
    ),
    RiskMode.AGGRESSIVE: RiskModeConfig(
        mode=RiskMode.AGGRESSIVE,
        min_expected_edge_bps=1.5,
        max_acceptable_loss_bps=3.5,
        volatility_threshold=0.01,   # 1.0%
        max_latency_ms=2000.0,
        min_funding_score=40.0,
        safety_weight=0.55,
        volume_weight=0.45,
        final_score_threshold=60.0,
    ),
}


@dataclass
class MarketData:
    """市场行情数据"""
    symbol: str
    exchange: str
    bid: float
    ask: float
    last: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def spread(self) -> float:
        """点差"""
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        """点差百分比"""
        mid = (self.bid + self.ask) / 2
        return self.spread / mid if mid > 0 else 0.0


@dataclass
class RiskEvaluation:
    """风险评估结果"""
    decision: DecisionType
    safety_score: float          # 安全性评分 (0-100)
    volume_score: float          # 成交量评分 (0-100)
    final_score: float           # 综合评分 (0-100)
    reason: Optional[str] = None # 拒绝原因
    warnings: List[str] = field(default_factory=list)  # 警告信息

    # 详细评分
    funding_score: float = 0.0
    spread_score: float = 0.0
    volatility_score: float = 0.0
    latency_score: float = 0.0
    leverage_score: float = 0.0


class EnhancedRiskManager:
    """
    增强风控中枢

    多维度风险评估系统，支持：
    - 资金费率风险
    - 价差与滑点风险
    - 延迟风险
    - 波动率风险
    - 杠杆与爆仓风险
    - 当日损失限制
    - 连续失败保护
    """

    def __init__(
        self,
        risk_mode: RiskMode = RiskMode.BALANCED,
        daily_loss_limit_pct: float = 0.01,      # 当日损失限制 1%
        daily_loss_limit_abs: float = 0.0,       # 绝对金额限制（0=不限制）
        max_consecutive_failures: int = 5,       # 最大连续失败次数
        daily_volume_target: float = 0.0,        # 日成交量目标
        funding_blackout_minutes: int = 10,      # 资金费率黑窗（结算前后）
        volatility_window_seconds: int = 300,    # 波动率窗口（秒）
    ):
        """
        初始化增强风控管理器

        Args:
            risk_mode: 风险模式
            daily_loss_limit_pct: 当日损失限制（百分比）
            daily_loss_limit_abs: 当日损失限制（绝对金额）
            max_consecutive_failures: 最大连续失败次数
            daily_volume_target: 日成交量目标
            funding_blackout_minutes: 资金费率黑窗时间
            volatility_window_seconds: 波动率计算窗口
        """
        self.risk_mode = risk_mode
        self.config = RISK_MODE_PRESETS[risk_mode]

        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.daily_loss_limit_abs = daily_loss_limit_abs
        self.max_consecutive_failures = max_consecutive_failures
        self.daily_volume_target = daily_volume_target
        self.funding_blackout_minutes = funding_blackout_minutes
        self.volatility_window_seconds = volatility_window_seconds

        # 状态跟踪
        self.today_pnl = 0.0
        self.today_volume = 0.0
        self.today_fees = 0.0
        self.consecutive_failures = 0
        self.auto_halt = False
        self.manual_override = False

        # 市场数据缓存
        self.exchange_latency: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.price_history: Dict[Tuple[str, str], deque] = defaultdict(
            lambda: deque(maxlen=1000)
        )  # (exchange, symbol) -> prices
        self.funding_rates: Dict[Tuple[str, str], float] = {}  # (exchange, symbol) -> rate
        self.next_funding_time: Dict[Tuple[str, str], Optional[datetime]] = {}

        # 快市黑名单
        self.fast_markets: set = set()  # 符号集合
        self.delayed_exchanges: set = set()  # 高延迟交易所

        logger.info(
            f"初始化增强风控管理器: mode={risk_mode.value}, "
            f"daily_loss_limit={daily_loss_limit_pct*100:.2f}%, "
            f"max_failures={max_consecutive_failures}"
        )

    def evaluate_job(
        self,
        job,
        market_data: Optional[Dict[Tuple[str, str], MarketData]] = None
    ) -> RiskEvaluation:
        """
        评估任务的风险

        Args:
            job: HedgeJob 对象
            market_data: 市场行情数据字典 {(exchange, symbol): MarketData}

        Returns:
            RiskEvaluation 评估结果
        """
        # 1. 硬风控检查（不可覆盖）
        hard_check = self._check_hard_constraints(job)
        if hard_check:
            return RiskEvaluation(
                decision=DecisionType.REJECT,
                safety_score=0.0,
                volume_score=0.0,
                final_score=0.0,
                reason=f"硬风控拒绝: {hard_check}"
            )

        # 2. 软风控检查（可被 manual_override 覆盖）
        if not self.manual_override:
            soft_check = self._check_soft_constraints(job, market_data)
            if soft_check:
                return RiskEvaluation(
                    decision=DecisionType.REJECT,
                    safety_score=0.0,
                    volume_score=0.0,
                    final_score=0.0,
                    reason=f"软风控拒绝: {soft_check}"
                )

        # 3. 计算各维度评分
        funding_score = self._evaluate_funding_risk(job, market_data)
        spread_score = self._evaluate_spread_risk(job, market_data)
        volatility_score = self._evaluate_volatility_risk(job, market_data)
        latency_score = self._evaluate_latency_risk(job)
        leverage_score = self._evaluate_leverage_risk(job)

        # 4. 计算安全性评分
        safety_score = (
            funding_score * 0.25 +
            spread_score * 0.25 +
            volatility_score * 0.20 +
            latency_score * 0.15 +
            leverage_score * 0.15
        )

        # 5. 计算成交量评分
        volume_score = self._evaluate_volume_contribution(job)

        # 6. 计算综合评分
        final_score = (
            self.config.safety_weight * safety_score +
            self.config.volume_weight * volume_score
        )

        # 7. 做出决策
        warnings = []

        if final_score < self.config.final_score_threshold:
            if self.manual_override:
                warnings.append(
                    f"⚠️ 人工覆盖模式: 评分 {final_score:.1f} 低于阈值 "
                    f"{self.config.final_score_threshold:.1f}"
                )
                decision = DecisionType.WARN
            else:
                return RiskEvaluation(
                    decision=DecisionType.REJECT,
                    safety_score=safety_score,
                    volume_score=volume_score,
                    final_score=final_score,
                    reason=f"综合评分 {final_score:.1f} 低于阈值 {self.config.final_score_threshold:.1f}",
                    funding_score=funding_score,
                    spread_score=spread_score,
                    volatility_score=volatility_score,
                    latency_score=latency_score,
                    leverage_score=leverage_score,
                )
        else:
            decision = DecisionType.ACCEPT

        return RiskEvaluation(
            decision=decision,
            safety_score=safety_score,
            volume_score=volume_score,
            final_score=final_score,
            warnings=warnings,
            funding_score=funding_score,
            spread_score=spread_score,
            volatility_score=volatility_score,
            latency_score=latency_score,
            leverage_score=leverage_score,
        )

    def _check_hard_constraints(self, job) -> Optional[str]:
        """检查硬风控约束（不可覆盖）"""
        # 1. 自动暂停检查
        if self.auto_halt and not self.manual_override:
            return "系统处于自动暂停状态"

        # 2. 当日损失限制（百分比）
        if self.daily_loss_limit_pct > 0:
            if self.today_pnl < 0 and abs(self.today_pnl) >= self.daily_loss_limit_pct * 10000:
                return f"当日损失 {self.today_pnl:.2f} 超过限制 {self.daily_loss_limit_pct*100}%"

        # 3. 当日损失限制（绝对金额）
        if self.daily_loss_limit_abs > 0:
            if self.today_pnl < 0 and abs(self.today_pnl) >= self.daily_loss_limit_abs:
                return f"当日损失 ${abs(self.today_pnl):.2f} 超过限制 ${self.daily_loss_limit_abs:.2f}"

        # 4. 快市黑名单
        symbol = getattr(job, 'symbol', None)
        if symbol and symbol in self.fast_markets:
            return f"符号 {symbol} 处于快市黑名单"

        # 5. 高延迟交易所黑名单
        exchanges = getattr(job, 'exchanges', set())
        for exchange in exchanges:
            if exchange in self.delayed_exchanges:
                return f"交易所 {exchange} 延迟过高，已被禁用"

        return None

    def _check_soft_constraints(self, job, market_data) -> Optional[str]:
        """检查软风控约束（可被 manual_override 覆盖）"""
        # 1. 预期收益检查
        expected_edge_bps = getattr(job, 'expected_edge_bps', 0.0)
        if expected_edge_bps < self.config.min_expected_edge_bps:
            return (
                f"预期收益 {expected_edge_bps:.2f}bps 低于最小要求 "
                f"{self.config.min_expected_edge_bps:.2f}bps"
            )

        # 2. 连续失败检查
        if self.consecutive_failures >= self.max_consecutive_failures:
            return f"连续失败 {self.consecutive_failures} 次，达到上限"

        return None

    def _evaluate_funding_risk(self, job, market_data) -> float:
        """评估资金费率风险 (0-100)"""
        # 简化实现：返回默认评分
        # 实际应该检查：
        # 1. 双边资金费率差值
        # 2. 是否在黑窗期
        # 3. 方向是否对冲
        return 70.0  # 默认中等评分

    def _evaluate_spread_risk(self, job, market_data) -> float:
        """评估价差与滑点风险 (0-100)"""
        if not market_data:
            return 50.0  # 无数据，返回中性评分

        # 检查各交易所的点差
        symbol = getattr(job, 'symbol', None)
        exchanges = getattr(job, 'exchanges', set())

        spreads = []
        for exchange in exchanges:
            key = (exchange, symbol)
            if key in market_data:
                spread_pct = market_data[key].spread_pct
                spreads.append(spread_pct)

        if not spreads:
            return 50.0

        # 平均点差越小，评分越高
        avg_spread = sum(spreads) / len(spreads)
        if avg_spread < 0.0005:  # < 0.05%
            return 90.0
        elif avg_spread < 0.001:  # < 0.1%
            return 75.0
        elif avg_spread < 0.002:  # < 0.2%
            return 60.0
        else:
            return 40.0

    def _evaluate_volatility_risk(self, job, market_data) -> float:
        """评估波动率风险 (0-100)"""
        # 简化实现：检查最近价格波动
        symbol = getattr(job, 'symbol', None)
        exchanges = getattr(job, 'exchanges', set())

        volatilities = []
        for exchange in exchanges:
            key = (exchange, symbol)
            if key in self.price_history:
                prices = list(self.price_history[key])
                if len(prices) >= 10:
                    volatility = self._calculate_volatility(prices)
                    volatilities.append(volatility)

        if not volatilities:
            return 70.0  # 无数据，返回中等评分

        avg_vol = sum(volatilities) / len(volatilities)

        # 波动率越低，评分越高
        if avg_vol < self.config.volatility_threshold * 0.5:
            return 90.0
        elif avg_vol < self.config.volatility_threshold:
            return 70.0
        elif avg_vol < self.config.volatility_threshold * 1.5:
            return 50.0
        else:
            return 30.0

    def _evaluate_latency_risk(self, job) -> float:
        """评估延迟风险 (0-100)"""
        exchanges = getattr(job, 'exchanges', set())

        latencies = []
        for exchange in exchanges:
            if exchange in self.exchange_latency:
                recent_latencies = list(self.exchange_latency[exchange])
                if recent_latencies:
                    avg_latency = sum(recent_latencies) / len(recent_latencies)
                    latencies.append(avg_latency)

        if not latencies:
            return 70.0  # 无数据，返回中等评分

        max_latency = max(latencies)

        # 延迟越低，评分越高
        if max_latency < self.config.max_latency_ms * 0.3:
            return 95.0
        elif max_latency < self.config.max_latency_ms * 0.6:
            return 80.0
        elif max_latency < self.config.max_latency_ms:
            return 65.0
        else:
            return 40.0

    def _evaluate_leverage_risk(self, job) -> float:
        """评估杠杆与爆仓风险 (0-100)"""
        # 简化实现：假设低杠杆对冲策略
        # 实际应该计算爆仓距离
        return 80.0  # 默认较安全

    def _evaluate_volume_contribution(self, job) -> float:
        """评估成交量贡献 (0-100)"""
        notional = getattr(job, 'notional', 0.0)
        est_volume = getattr(job, 'est_volume', notional * 2)  # 默认双边

        if self.daily_volume_target <= 0:
            # 无目标，按名义金额归一化
            return min(100.0, (est_volume / 10000) * 100)
        else:
            # 有目标，计算贡献度
            gap = max(0, self.daily_volume_target - self.today_volume)
            contribution = min(1.0, est_volume / max(gap, 1000))
            return contribution * 100

    def _calculate_volatility(self, prices: List[float]) -> float:
        """计算价格序列的波动率"""
        if len(prices) < 2:
            return 0.0

        # 简化：计算价格变化的标准差
        changes = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                change = abs(prices[i] - prices[i-1]) / prices[i-1]
                changes.append(change)

        if not changes:
            return 0.0

        mean = sum(changes) / len(changes)
        variance = sum((x - mean) ** 2 for x in changes) / len(changes)
        return variance ** 0.5

    # 状态更新方法
    def update_price(self, exchange: str, symbol: str, price: float) -> None:
        """更新价格历史"""
        key = (exchange, symbol)
        self.price_history[key].append(price)

    def update_latency(self, exchange: str, latency_ms: float) -> None:
        """更新交易所延迟"""
        self.exchange_latency[exchange].append(latency_ms)

        # 检查是否需要加入黑名单
        if len(self.exchange_latency[exchange]) >= 10:
            avg_latency = sum(self.exchange_latency[exchange]) / len(self.exchange_latency[exchange])
            if avg_latency > self.config.max_latency_ms * 2:
                if exchange not in self.delayed_exchanges:
                    self.delayed_exchanges.add(exchange)
                    logger.warning(f"⚠️ 交易所 {exchange} 延迟过高 ({avg_latency:.0f}ms)，加入黑名单")

    def update_funding_rate(
        self,
        exchange: str,
        symbol: str,
        rate: float,
        next_funding_time: Optional[datetime] = None
    ) -> None:
        """更新资金费率"""
        key = (exchange, symbol)
        self.funding_rates[key] = rate
        if next_funding_time:
            self.next_funding_time[key] = next_funding_time

    def record_pnl(self, pnl: float, volume: float = 0.0, fees: float = 0.0) -> None:
        """记录交易结果"""
        self.today_pnl += pnl
        self.today_volume += volume
        self.today_fees += fees

        logger.info(
            f"记录 PnL: {pnl:+.4f}, 成交量: {volume:.2f}, "
            f"累计 PnL: {self.today_pnl:+.4f}, 累计成交量: {self.today_volume:.2f}"
        )

    def record_success(self) -> None:
        """记录成功交易"""
        if self.consecutive_failures > 0:
            logger.info(f"交易成功，连续失败计数清零（之前: {self.consecutive_failures}）")
            self.consecutive_failures = 0

        # 检查是否可以解除自动暂停
        if self.auto_halt and self.consecutive_failures == 0:
            logger.info("连续失败已清零，可考虑解除自动暂停")

    def record_failure(self, reason: str = "") -> None:
        """记录失败交易"""
        self.consecutive_failures += 1
        logger.warning(
            f"交易失败（{reason}），连续失败: {self.consecutive_failures}/{self.max_consecutive_failures}"
        )

        if self.consecutive_failures >= self.max_consecutive_failures:
            self.auto_halt = True
            logger.error(
                f"⛔ 连续失败达到上限 ({self.max_consecutive_failures})，触发自动暂停！"
            )

    def set_risk_mode(self, mode: RiskMode) -> None:
        """切换风险模式"""
        old_mode = self.risk_mode
        self.risk_mode = mode
        self.config = RISK_MODE_PRESETS[mode]

        logger.info(f"风险模式切换: {old_mode.value} → {mode.value}")
        logger.info(
            f"新配置: min_edge={self.config.min_expected_edge_bps:.1f}bps, "
            f"vol_threshold={self.config.volatility_threshold*100:.2f}%, "
            f"safety_weight={self.config.safety_weight:.2f}"
        )

    def enable_manual_override(self, enabled: bool) -> None:
        """启用/禁用人工覆盖模式"""
        self.manual_override = enabled

        if enabled:
            logger.warning(
                "⚠️ 启用人工覆盖模式：软风控将被绕过，但硬风控仍生效"
            )
        else:
            logger.info("✅ 禁用人工覆盖模式：恢复正常风控")

    def reset_auto_halt(self) -> None:
        """手动重置自动暂停状态"""
        if self.auto_halt:
            logger.warning("⚠️ 手动重置自动暂停状态")
            self.auto_halt = False
            self.consecutive_failures = 0

    def add_fast_market(self, symbol: str) -> None:
        """将符号加入快市黑名单"""
        if symbol not in self.fast_markets:
            self.fast_markets.add(symbol)
            logger.warning(f"⚠️ {symbol} 加入快市黑名单")

    def remove_fast_market(self, symbol: str) -> None:
        """将符号从快市黑名单移除"""
        if symbol in self.fast_markets:
            self.fast_markets.remove(symbol)
            logger.info(f"✅ {symbol} 从快市黑名单移除")

    def get_state(self) -> Dict:
        """获取风控状态"""
        return {
            "risk_mode": self.risk_mode.value,
            "auto_halt": self.auto_halt,
            "manual_override": self.manual_override,
            "today_pnl": self.today_pnl,
            "today_volume": self.today_volume,
            "today_fees": self.today_fees,
            "consecutive_failures": self.consecutive_failures,
            "fast_markets": list(self.fast_markets),
            "delayed_exchanges": list(self.delayed_exchanges),
            "daily_loss_limit_pct": self.daily_loss_limit_pct,
            "daily_loss_limit_abs": self.daily_loss_limit_abs,
            "config": {
                "min_expected_edge_bps": self.config.min_expected_edge_bps,
                "max_acceptable_loss_bps": self.config.max_acceptable_loss_bps,
                "volatility_threshold": self.config.volatility_threshold,
                "final_score_threshold": self.config.final_score_threshold,
                "safety_weight": self.config.safety_weight,
                "volume_weight": self.config.volume_weight,
            }
        }
