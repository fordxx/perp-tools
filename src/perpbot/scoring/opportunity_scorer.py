"""
OpportunityScorer - 统一机会评分引擎

整合所有成本模型，对交易机会进行数学级别的真实收益评估。

ExpectedPNL =
    price_spread_pnl
  + funding_pnl
  - taker_fee_cost
  - estimated_slippage_cost
  - latency_penalty
  - capital_time_cost

若 ExpectedPNL <= 0 → 禁止执行
"""

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from perpbot.scoring.fee_model import FeeModel
from perpbot.scoring.funding_model import FundingModel
from perpbot.scoring.slippage_model import SlippageModel


logger = logging.getLogger(__name__)


@dataclass
class OpportunityScore:
    """
    机会评分结果

    包含所有成本细节和最终评分
    """
    # 基础信息
    opportunity_id: str
    opportunity_type: str  # "arbitrage", "wash", "hedge"

    # 收益分解
    price_spread_pnl: float        # 价差收益
    funding_pnl: float             # 资金费率收益
    total_revenue: float           # 总收入

    # 成本分解
    taker_fee_cost: float          # Taker 手续费
    slippage_cost: float           # 滑点成本
    latency_penalty: float         # 延迟惩罚
    capital_time_cost: float       # 资金时间成本
    total_cost: float              # 总成本

    # 净收益
    expected_pnl: float            # 预期 PnL
    roi_pct: float                 # ROI 百分比
    roi_annualized_pct: float      # 年化 ROI

    # 时间与风险
    time_cost_sec: float           # 预期执行时间（秒）
    risk_score: float              # 风险评分（0-1）

    # 最终评分
    final_score: float             # 综合评分

    # 元数据
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def is_profitable(self) -> bool:
        """是否盈利"""
        return self.expected_pnl > 0

    def is_executable(self, min_pnl: float = 0.0, min_score: float = 0.0) -> bool:
        """是否可执行"""
        return self.expected_pnl > min_pnl and self.final_score > min_score


class OpportunityScorer:
    """
    统一机会评分引擎

    整合 FeeModel、FundingModel、SlippageModel
    """

    def __init__(
        self,
        fee_model: Optional[FeeModel] = None,
        funding_model: Optional[FundingModel] = None,
        slippage_model: Optional[SlippageModel] = None,
        capital_cost_rate_annual: float = 0.05,  # 年化资金成本 5%
        reliability_weight: float = 1.0,
        min_pnl_threshold: float = 0.01,  # 最小 PnL 阈值（USDT）
    ):
        """
        初始化评分引擎

        Args:
            fee_model: 手续费模型
            funding_model: 资金费率模型
            slippage_model: 滑点模型
            capital_cost_rate_annual: 年化资金成本率
            reliability_weight: 可靠性权重
            min_pnl_threshold: 最小 PnL 阈值
        """
        self.fee_model = fee_model or FeeModel()
        self.funding_model = funding_model or FundingModel()
        self.slippage_model = slippage_model or SlippageModel()

        self.capital_cost_rate_annual = capital_cost_rate_annual
        self.reliability_weight = reliability_weight
        self.min_pnl_threshold = min_pnl_threshold

        logger.info(
            f"初始化机会评分引擎: capital_cost={capital_cost_rate_annual*100:.1f}%, "
            f"reliability={reliability_weight}, min_pnl={min_pnl_threshold}"
        )

    def score_arbitrage_opportunity(
        self,
        opportunity_id: str,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        buy_price: float,
        sell_price: float,
        notional: float,
        holding_hours: float = 0.1,  # 预期持仓时长（默认 6 分钟）
        buy_latency_ms: Optional[float] = None,
        sell_latency_ms: Optional[float] = None,
        risk_factors: Optional[Dict] = None,
    ) -> OpportunityScore:
        """
        评分套利机会

        Args:
            opportunity_id: 机会ID
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            buy_price: 买入价格
            sell_price: 卖出价格
            notional: 名义金额
            holding_hours: 预期持仓时长（小时）
            buy_latency_ms: 买入延迟
            sell_latency_ms: 卖出延迟
            risk_factors: 额外风险因子

        Returns:
            OpportunityScore
        """
        logger.debug(
            f"评分套利机会: {buy_exchange}<->{sell_exchange} {symbol}, "
            f"buy={buy_price:.2f}, sell={sell_price:.2f}, "
            f"notional={notional:.0f}"
        )

        # 1. 价差收益
        price_spread_pnl = (sell_price - buy_price) * (notional / buy_price)

        # 2. 资金费率收益
        funding_pnl = self.funding_model.calculate_arbitrage_funding_pnl(
            buy_exchange, sell_exchange, symbol, notional, holding_hours
        )

        # 3. 手续费成本
        fee_cost = self.fee_model.calculate_cross_exchange_fee(
            buy_exchange, sell_exchange, notional
        )

        # 4. 滑点成本
        slippage_cost = self.slippage_model.estimate_cross_exchange_slippage(
            buy_exchange, sell_exchange, symbol, notional,
            buy_latency_ms, sell_latency_ms
        )

        # 5. 延迟惩罚（高延迟增加额外成本）
        latency_penalty = self._calculate_latency_penalty(
            buy_latency_ms, sell_latency_ms, notional
        )

        # 6. 资金时间成本
        capital_time_cost = self._calculate_capital_time_cost(
            notional, holding_hours
        )

        # 总收入
        total_revenue = price_spread_pnl + funding_pnl

        # 总成本
        total_cost = fee_cost + slippage_cost + latency_penalty + capital_time_cost

        # 预期 PnL
        expected_pnl = total_revenue - total_cost

        # ROI
        roi_pct = (expected_pnl / notional) * 100 if notional > 0 else 0.0
        roi_annualized_pct = (
            roi_pct * (8760 / holding_hours) if holding_hours > 0 else 0.0
        )

        # 时间成本
        time_cost_sec = holding_hours * 3600

        # 风险评分
        risk_score = self._calculate_risk_score(
            buy_exchange, sell_exchange, symbol,
            notional, buy_latency_ms, sell_latency_ms,
            risk_factors
        )

        # 最终评分
        final_score = self._calculate_final_score(
            expected_pnl, time_cost_sec, risk_score
        )

        score = OpportunityScore(
            opportunity_id=opportunity_id,
            opportunity_type="arbitrage",
            price_spread_pnl=price_spread_pnl,
            funding_pnl=funding_pnl,
            total_revenue=total_revenue,
            taker_fee_cost=fee_cost,
            slippage_cost=slippage_cost,
            latency_penalty=latency_penalty,
            capital_time_cost=capital_time_cost,
            total_cost=total_cost,
            expected_pnl=expected_pnl,
            roi_pct=roi_pct,
            roi_annualized_pct=roi_annualized_pct,
            time_cost_sec=time_cost_sec,
            risk_score=risk_score,
            final_score=final_score,
            metadata={
                "buy_exchange": buy_exchange,
                "sell_exchange": sell_exchange,
                "symbol": symbol,
                "buy_price": buy_price,
                "sell_price": sell_price,
                "notional": notional,
                "spread_bps": ((sell_price - buy_price) / buy_price) * 10000,
            },
        )

        logger.info(
            f"套利评分: {opportunity_id}, "
            f"pnl={expected_pnl:.4f}, roi={roi_pct:.3f}%, "
            f"score={final_score:.2f}, executable={score.is_executable()}"
        )

        return score

    def score_wash_opportunity(
        self,
        opportunity_id: str,
        exchange: str,
        symbol: str,
        price: float,
        notional: float,
        holding_hours: float = 0.01,  # 刷量通常很快
        latency_ms: Optional[float] = None,
        has_rebate: bool = False,
    ) -> OpportunityScore:
        """
        评分刷量机会

        Args:
            opportunity_id: 机会ID
            exchange: 交易所
            symbol: 交易对
            price: 价格
            notional: 名义金额
            holding_hours: 持仓时长
            latency_ms: 延迟
            has_rebate: 是否有返佣

        Returns:
            OpportunityScore
        """
        logger.debug(
            f"评分刷量机会: {exchange} {symbol}, "
            f"notional={notional:.0f}, rebate={has_rebate}"
        )

        # 1. 价差收益（刷量没有价差收益）
        price_spread_pnl = 0.0

        # 2. 资金费率（刷量通常不持仓）
        funding_pnl = 0.0

        # 3. 手续费（往返）
        fee_cost = self.fee_model.calculate_round_trip_fee(
            exchange, notional, both_taker=True
        )

        # 如果有返佣，减少成本
        if has_rebate:
            config = self.fee_model.get_config(exchange)
            if config and config.wash_rebate_pct > 0:
                fee_cost *= (1 - config.wash_rebate_pct)

        # 4. 滑点成本
        slippage_cost = self.slippage_model.estimate_round_trip_slippage(
            exchange, symbol, notional, latency_ms
        )

        # 5. 延迟惩罚
        latency_penalty = self._calculate_latency_penalty(
            latency_ms, None, notional
        )

        # 6. 资金时间成本
        capital_time_cost = self._calculate_capital_time_cost(
            notional, holding_hours
        )

        # 总收入（刷量通常没有直接收入）
        total_revenue = 0.0

        # 总成本
        total_cost = fee_cost + slippage_cost + latency_penalty + capital_time_cost

        # 预期 PnL（刷量通常为负，除非有足够返佣）
        expected_pnl = total_revenue - total_cost

        # ROI
        roi_pct = (expected_pnl / notional) * 100 if notional > 0 else 0.0
        roi_annualized_pct = (
            roi_pct * (8760 / holding_hours) if holding_hours > 0 else 0.0
        )

        # 时间成本
        time_cost_sec = holding_hours * 3600

        # 风险评分（刷量风险较低）
        risk_score = 0.1

        # 最终评分（刷量主要看成交量而非利润）
        # 这里简化处理，实际可能需要考虑成交量目标
        final_score = self._calculate_final_score(
            expected_pnl, time_cost_sec, risk_score
        )

        score = OpportunityScore(
            opportunity_id=opportunity_id,
            opportunity_type="wash",
            price_spread_pnl=price_spread_pnl,
            funding_pnl=funding_pnl,
            total_revenue=total_revenue,
            taker_fee_cost=fee_cost,
            slippage_cost=slippage_cost,
            latency_penalty=latency_penalty,
            capital_time_cost=capital_time_cost,
            total_cost=total_cost,
            expected_pnl=expected_pnl,
            roi_pct=roi_pct,
            roi_annualized_pct=roi_annualized_pct,
            time_cost_sec=time_cost_sec,
            risk_score=risk_score,
            final_score=final_score,
            metadata={
                "exchange": exchange,
                "symbol": symbol,
                "price": price,
                "notional": notional,
                "has_rebate": has_rebate,
            },
        )

        logger.info(
            f"刷量评分: {opportunity_id}, "
            f"pnl={expected_pnl:.4f}, cost={total_cost:.4f}, "
            f"score={final_score:.2f}"
        )

        return score

    def filter_opportunities(
        self,
        scores: List[OpportunityScore],
        min_pnl: Optional[float] = None,
        min_score: Optional[float] = None,
        min_roi_pct: Optional[float] = None,
    ) -> List[OpportunityScore]:
        """
        过滤机会

        Args:
            scores: 机会评分列表
            min_pnl: 最小 PnL
            min_score: 最小评分
            min_roi_pct: 最小 ROI

        Returns:
            过滤后的列表
        """
        if min_pnl is None:
            min_pnl = self.min_pnl_threshold

        filtered = []

        for score in scores:
            # PnL 过滤
            if score.expected_pnl <= min_pnl:
                logger.debug(
                    f"过滤机会 {score.opportunity_id}: "
                    f"pnl={score.expected_pnl:.4f} <= {min_pnl}"
                )
                continue

            # 评分过滤
            if min_score and score.final_score < min_score:
                logger.debug(
                    f"过滤机会 {score.opportunity_id}: "
                    f"score={score.final_score:.2f} < {min_score}"
                )
                continue

            # ROI 过滤
            if min_roi_pct and score.roi_pct < min_roi_pct:
                logger.debug(
                    f"过滤机会 {score.opportunity_id}: "
                    f"roi={score.roi_pct:.3f}% < {min_roi_pct}%"
                )
                continue

            filtered.append(score)

        logger.info(
            f"机会过滤: {len(scores)} → {len(filtered)} "
            f"(min_pnl={min_pnl}, min_score={min_score}, min_roi={min_roi_pct})"
        )

        return filtered

    def rank_opportunities(
        self,
        scores: List[OpportunityScore],
        by: str = "final_score",  # "final_score", "expected_pnl", "roi_pct"
    ) -> List[OpportunityScore]:
        """
        排序机会

        Args:
            scores: 机会列表
            by: 排序依据

        Returns:
            排序后的列表
        """
        if by == "final_score":
            sorted_scores = sorted(scores, key=lambda s: s.final_score, reverse=True)
        elif by == "expected_pnl":
            sorted_scores = sorted(scores, key=lambda s: s.expected_pnl, reverse=True)
        elif by == "roi_pct":
            sorted_scores = sorted(scores, key=lambda s: s.roi_pct, reverse=True)
        else:
            raise ValueError(f"Invalid sort key: {by}")

        return sorted_scores

    # ==================== 内部方法 ====================

    def _calculate_latency_penalty(
        self,
        latency1_ms: Optional[float],
        latency2_ms: Optional[float],
        notional: float,
    ) -> float:
        """计算延迟惩罚"""
        max_latency = 0.0

        if latency1_ms:
            max_latency = max(max_latency, latency1_ms)
        if latency2_ms:
            max_latency = max(max_latency, latency2_ms)

        if max_latency > 500:  # 超过 500ms
            # 高延迟时增加额外惩罚
            penalty = notional * 0.0001 * (max_latency / 1000)
            return penalty

        return 0.0

    def _calculate_capital_time_cost(
        self,
        notional: float,
        holding_hours: float,
    ) -> float:
        """计算资金时间成本"""
        # 年化成本率转换为小时成本率
        hourly_rate = self.capital_cost_rate_annual / 8760

        cost = notional * hourly_rate * holding_hours

        return cost

    def _calculate_risk_score(
        self,
        buy_exchange: Optional[str],
        sell_exchange: Optional[str],
        symbol: str,
        notional: float,
        buy_latency_ms: Optional[float],
        sell_latency_ms: Optional[float],
        risk_factors: Optional[Dict],
    ) -> float:
        """
        计算风险评分（0-1，越高越危险）

        考虑因素：
        - 延迟
        - 盘口深度
        - 额外风险因子
        """
        risk_score = 0.0

        # 1. 延迟风险
        max_latency = 0.0
        if buy_latency_ms:
            max_latency = max(max_latency, buy_latency_ms)
        if sell_latency_ms:
            max_latency = max(max_latency, sell_latency_ms)

        if max_latency > 1000:  # >1s
            risk_score += 0.5
        elif max_latency > 500:  # >500ms
            risk_score += 0.3
        elif max_latency > 200:  # >200ms
            risk_score += 0.1

        # 2. 深度风险（简化）
        # 这里可以扩展检查盘口深度

        # 3. 额外风险因子
        if risk_factors:
            if risk_factors.get("high_volatility"):
                risk_score += 0.2
            if risk_factors.get("low_liquidity"):
                risk_score += 0.3

        # 限制在 [0, 1]
        risk_score = min(1.0, risk_score)

        return risk_score

    def _calculate_final_score(
        self,
        expected_pnl: float,
        time_cost_sec: float,
        risk_score: float,
    ) -> float:
        """
        计算最终评分

        公式：
        final_score = expected_pnl * reliability_weight * (1 - risk_score) / sqrt(time_cost_sec + 1)

        越高越好
        """
        if expected_pnl <= 0:
            return 0.0

        # 时间因子（越快越好）
        time_factor = 1.0 / math.sqrt(time_cost_sec + 1)

        # 可靠性因子
        reliability_factor = self.reliability_weight * (1 - risk_score)

        # 最终评分
        final_score = expected_pnl * reliability_factor * time_factor

        return max(0.0, final_score)
