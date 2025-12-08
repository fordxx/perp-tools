"""
MakerFillEstimator - Maker 填单概率估计

评估因素：
- 挂单价离 mid 的距离
- 盘口深度
- 近期挂单成交情况
"""

import logging
from typing import Optional

from perpbot.scoring.slippage_model import OrderbookDepth


logger = logging.getLogger(__name__)


class MakerFillEstimator:
    """
    Maker 填单概率估计器

    估算 maker 订单的填单概率，用于优化执行策略
    """

    def __init__(
        self,
        # 价格偏移阈值
        max_offset_bps: float = 5.0,  # 最大偏移 5bps
        # 深度影响因子
        depth_importance: float = 0.3,  # 深度权重
        # 历史成交率权重
        history_weight: float = 0.3,  # 历史权重
    ):
        """
        初始化填单概率估计器

        Args:
            max_offset_bps: 最大价格偏移（bps）
            depth_importance: 深度重要性（0-1）
            history_weight: 历史成交率权重（0-1）
        """
        self.max_offset_bps = max_offset_bps
        self.depth_importance = depth_importance
        self.history_weight = history_weight

        logger.info(
            f"初始化 MakerFillEstimator: max_offset={max_offset_bps}bps, "
            f"depth_weight={depth_importance}, history_weight={history_weight}"
        )

    def estimate_fill_probability(
        self,
        # 订单信息
        order_price: float,  # 挂单价格
        mid_price: float,  # 市场中间价
        side: str,  # "buy" 或 "sell"
        notional: float,  # 名义金额
        # 盘口信息
        orderbook_depth: Optional[OrderbookDepth] = None,
        # 历史成交率
        recent_fill_rate: Optional[float] = None,
    ) -> float:
        """
        估计填单概率

        Args:
            order_price: 挂单价格
            mid_price: 市场中间价
            side: 买卖方向
            notional: 名义金额
            orderbook_depth: 盘口深度信息
            recent_fill_rate: 近期填单成功率（0-1）

        Returns:
            填单概率（0-1）
        """
        # 1. 价格偏移因子（最重要）
        price_factor = self._calculate_price_factor(
            order_price, mid_price, side
        )

        # 2. 深度因子
        depth_factor = 1.0
        if orderbook_depth:
            depth_factor = self._calculate_depth_factor(
                notional, orderbook_depth, side
            )

        # 3. 历史成交率因子
        history_factor = 1.0
        if recent_fill_rate is not None:
            history_factor = recent_fill_rate

        # 综合概率（加权平均）
        # 价格是主导因素，深度和历史是修正因素
        base_weight = 1.0 - self.depth_importance - self.history_weight

        probability = (
            base_weight * price_factor
            + self.depth_importance * depth_factor
            + self.history_weight * history_factor
        )

        # 限制在 [0, 1] 范围内
        probability = max(0.0, min(1.0, probability))

        logger.debug(
            f"Maker 填单概率: {probability:.2%} "
            f"(price={price_factor:.2f}, depth={depth_factor:.2f}, "
            f"history={history_factor:.2f})"
        )

        return probability

    def _calculate_price_factor(
        self, order_price: float, mid_price: float, side: str
    ) -> float:
        """
        计算价格偏移因子

        挂单价越接近 mid，填单概率越高
        - buy: order_price >= mid → 概率 100%（立即成交）
        - sell: order_price <= mid → 概率 100%
        - 偏离越多，概率越低

        Args:
            order_price: 挂单价
            mid_price: 中间价
            side: 方向

        Returns:
            价格因子（0-1）
        """
        # 计算偏移（bps）
        if side == "buy":
            # 买单：挂单价 < mid 才是 maker
            # 偏移 = (mid - order_price) / mid * 10000
            offset_bps = ((mid_price - order_price) / mid_price) * 10000
        elif side == "sell":
            # 卖单：挂单价 > mid 才是 maker
            # 偏移 = (order_price - mid) / mid * 10000
            offset_bps = ((order_price - mid_price) / mid_price) * 10000
        else:
            raise ValueError(f"无效的 side: {side}")

        # 如果偏移为负（即会立即成交），概率为 1.0
        if offset_bps <= 0:
            return 1.0

        # 如果偏移超过最大阈值，概率很低
        if offset_bps > self.max_offset_bps:
            # 线性衰减到 0
            return max(0.0, 1.0 - (offset_bps - self.max_offset_bps) / self.max_offset_bps)

        # 在阈值内，线性衰减
        # offset_bps = 0 → factor = 1.0
        # offset_bps = max_offset_bps → factor = 0.3
        factor = 1.0 - (offset_bps / self.max_offset_bps) * 0.7

        return factor

    def _calculate_depth_factor(
        self,
        notional: float,
        orderbook_depth: OrderbookDepth,
        side: str,
    ) -> float:
        """
        计算深度因子

        深度越厚，填单概率越高（市场活跃）

        Args:
            notional: 名义金额
            orderbook_depth: 盘口深度
            side: 方向

        Returns:
            深度因子（0-1）
        """
        # 获取相关深度
        if side == "buy":
            # 买单：关注 bid 深度（竞争者）
            available_depth = orderbook_depth.bid_depth
        elif side == "sell":
            # 卖单：关注 ask 深度
            available_depth = orderbook_depth.ask_depth
        else:
            raise ValueError(f"无效的 side: {side}")

        if available_depth <= 0:
            # 深度为 0，概率很低
            return 0.1

        # 深度比率
        depth_ratio = available_depth / notional

        if depth_ratio >= 10.0:
            # 深度非常充足，高概率
            return 1.0
        elif depth_ratio >= 3.0:
            # 深度较好
            return 0.8
        elif depth_ratio >= 1.0:
            # 深度一般
            return 0.6
        else:
            # 深度不足
            return 0.3 + depth_ratio * 0.3

    def estimate_expected_wait_time_ms(
        self,
        fill_probability: float,
        avg_fill_time_ms: float = 1000.0,
    ) -> float:
        """
        估计预期等待时间

        Args:
            fill_probability: 填单概率
            avg_fill_time_ms: 平均填单时间（毫秒）

        Returns:
            预期等待时间（毫秒）
        """
        if fill_probability <= 0:
            # 无法填单，返回一个很大的数
            return 10000.0

        # 简单模型：预期时间 = 平均时间 / 概率
        expected_time = avg_fill_time_ms / fill_probability

        return expected_time

    def should_use_maker(
        self,
        fill_probability: float,
        maker_fee_saving: float,  # 使用 maker 相比 taker 节省的费用
        min_probability: float = 0.5,  # 最小概率阈值
        min_fee_saving: float = 1.0,  # 最小费用节省（USDT）
    ) -> bool:
        """
        判断是否应该使用 maker 订单

        Args:
            fill_probability: 填单概率
            maker_fee_saving: 使用 maker 节省的费用
            min_probability: 最小概率阈值
            min_fee_saving: 最小费用节省

        Returns:
            是否应该使用 maker
        """
        # 概率太低，不值得冒险
        if fill_probability < min_probability:
            return False

        # 节省的费用太少，不值得
        if maker_fee_saving < min_fee_saving:
            return False

        return True

    def adjust_for_market_volatility(
        self,
        base_probability: float,
        volatility_factor: float,  # 波动率因子（0-1，越高越波动）
    ) -> float:
        """
        根据市场波动率调整填单概率

        市场波动大时，填单概率降低

        Args:
            base_probability: 基础概率
            volatility_factor: 波动率因子（0-1）

        Returns:
            调整后的概率
        """
        # 波动率越高，概率越低
        adjusted = base_probability * (1 - volatility_factor * 0.3)

        return max(0.0, min(1.0, adjusted))
