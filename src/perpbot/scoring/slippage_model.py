"""
SlippageModel - 滑点与延迟模型

结合：
- 盘口深度
- 下单规模
- 网络延迟
计算预期滑点成本
"""

import logging
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class OrderbookDepth:
    """盘口深度信息"""
    exchange: str
    symbol: str
    bid_depth: float     # 买一档深度（USDT）
    ask_depth: float     # 卖一档深度（USDT）
    bid_price: float
    ask_price: float
    spread_bps: float    # 点差（bps）


class SlippageModel:
    """
    滑点与延迟模型

    估算实际成交时的滑点成本
    """

    def __init__(
        self,
        base_slippage_bps: float = 1.0,  # 基础滑点 1bps
        depth_impact_factor: float = 0.5,  # 深度影响因子
        latency_penalty_factor: float = 0.001,  # 延迟惩罚因子
    ):
        """
        初始化滑点模型

        Args:
            base_slippage_bps: 基础滑点（bps）
            depth_impact_factor: 深度影响因子（0-1）
            latency_penalty_factor: 延迟惩罚因子
        """
        self.base_slippage_bps = base_slippage_bps
        self.depth_impact_factor = depth_impact_factor
        self.latency_penalty_factor = latency_penalty_factor

        # 存储盘口深度数据
        # {(exchange, symbol): OrderbookDepth}
        self.orderbook_depths: Dict[Tuple[str, str], OrderbookDepth] = {}

        logger.info(
            f"初始化滑点模型: base={base_slippage_bps}bps, "
            f"depth_factor={depth_impact_factor}, "
            f"latency_factor={latency_penalty_factor}"
        )

    def update_orderbook_depth(
        self,
        exchange: str,
        symbol: str,
        bid_depth: float,
        ask_depth: float,
        bid_price: float,
        ask_price: float,
    ):
        """
        更新盘口深度

        Args:
            exchange: 交易所
            symbol: 交易对
            bid_depth: 买一档深度（USDT）
            ask_depth: 卖一档深度（USDT）
            bid_price: 买一价
            ask_price: 卖一价
        """
        mid_price = (bid_price + ask_price) / 2
        spread_bps = ((ask_price - bid_price) / mid_price) * 10000

        depth = OrderbookDepth(
            exchange=exchange,
            symbol=symbol,
            bid_depth=bid_depth,
            ask_depth=ask_depth,
            bid_price=bid_price,
            ask_price=ask_price,
            spread_bps=spread_bps,
        )

        self.orderbook_depths[(exchange, symbol)] = depth

        logger.debug(
            f"更新盘口: {exchange} {symbol}, "
            f"bid_depth={bid_depth:.0f}, ask_depth={ask_depth:.0f}, "
            f"spread={spread_bps:.2f}bps"
        )

    def estimate_slippage(
        self,
        exchange: str,
        symbol: str,
        notional: float,
        side: str = "buy",  # "buy" or "sell"
        latency_ms: Optional[float] = None,
    ) -> float:
        """
        估算滑点成本

        Args:
            exchange: 交易所
            symbol: 交易对
            notional: 下单金额（USDT）
            side: 买入或卖出
            latency_ms: 网络延迟（毫秒）

        Returns:
            滑点成本（USDT）
        """
        key = (exchange, symbol)
        depth = self.orderbook_depths.get(key)

        # 1. 基础滑点
        base_slippage = notional * (self.base_slippage_bps / 10000)

        # 2. 深度影响
        depth_slippage = 0.0
        if depth:
            # 判断深度是否足够
            available_depth = depth.ask_depth if side == "buy" else depth.bid_depth

            if available_depth > 0:
                # 深度不足时增加滑点
                depth_ratio = notional / available_depth
                if depth_ratio > 1.0:
                    # 超过深度，按比例增加滑点
                    depth_slippage = (
                        notional * self.depth_impact_factor *
                        math.sqrt(depth_ratio - 1.0) / 100
                    )
                    logger.debug(
                        f"深度不足: {exchange} {symbol}, "
                        f"notional={notional:.0f}, depth={available_depth:.0f}, "
                        f"ratio={depth_ratio:.2f}, slippage={depth_slippage:.4f}"
                    )
        else:
            # 没有深度数据，使用保守估计
            depth_slippage = notional * 0.001  # 0.1%
            logger.warning(
                f"盘口深度未配置: {exchange} {symbol}，使用保守滑点估计"
            )

        # 3. 延迟惩罚
        latency_penalty = 0.0
        if latency_ms and latency_ms > 100:  # 延迟超过 100ms
            # 延迟越高，滑点越大（市场可能已经变化）
            latency_penalty = (
                notional * self.latency_penalty_factor *
                (latency_ms - 100) / 1000
            )
            logger.debug(
                f"延迟惩罚: {exchange}, latency={latency_ms:.0f}ms, "
                f"penalty={latency_penalty:.4f}"
            )

        # 总滑点
        total_slippage = base_slippage + depth_slippage + latency_penalty

        logger.debug(
            f"滑点估算: {exchange} {symbol} {side}, "
            f"notional={notional:.0f}, "
            f"base={base_slippage:.4f}, depth={depth_slippage:.4f}, "
            f"latency={latency_penalty:.4f}, total={total_slippage:.4f}"
        )

        return total_slippage

    def estimate_round_trip_slippage(
        self,
        exchange: str,
        symbol: str,
        notional: float,
        latency_ms: Optional[float] = None,
    ) -> float:
        """
        估算往返滑点（买入+卖出）

        Args:
            exchange: 交易所
            symbol: 交易对
            notional: 单边金额
            latency_ms: 延迟

        Returns:
            往返滑点总成本
        """
        buy_slippage = self.estimate_slippage(
            exchange, symbol, notional, "buy", latency_ms
        )
        sell_slippage = self.estimate_slippage(
            exchange, symbol, notional, "sell", latency_ms
        )

        return buy_slippage + sell_slippage

    def estimate_cross_exchange_slippage(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        buy_latency_ms: Optional[float] = None,
        sell_latency_ms: Optional[float] = None,
    ) -> float:
        """
        估算跨交易所套利滑点

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            notional: 名义金额
            buy_latency_ms: 买入交易所延迟
            sell_latency_ms: 卖出交易所延迟

        Returns:
            总滑点成本
        """
        buy_slippage = self.estimate_slippage(
            buy_exchange, symbol, notional, "buy", buy_latency_ms
        )
        sell_slippage = self.estimate_slippage(
            sell_exchange, symbol, notional, "sell", sell_latency_ms
        )

        return buy_slippage + sell_slippage

    def get_spread(self, exchange: str, symbol: str) -> Optional[float]:
        """
        获取点差（bps）

        Args:
            exchange: 交易所
            symbol: 交易对

        Returns:
            点差（bps），None 如果未配置
        """
        key = (exchange, symbol)
        depth = self.orderbook_depths.get(key)

        if depth:
            return depth.spread_bps

        return None

    def get_depth_info(
        self,
        exchange: str,
        symbol: str,
    ) -> Optional[OrderbookDepth]:
        """获取盘口深度信息"""
        return self.orderbook_depths.get((exchange, symbol))

    def calculate_price_impact(
        self,
        exchange: str,
        symbol: str,
        notional: float,
        side: str = "buy",
    ) -> float:
        """
        计算价格冲击（bps）

        Args:
            exchange: 交易所
            symbol: 交易对
            notional: 下单金额
            side: 买入或卖出

        Returns:
            价格冲击（bps）
        """
        key = (exchange, symbol)
        depth = self.orderbook_depths.get(key)

        if not depth:
            # 默认估计
            return self.base_slippage_bps

        available_depth = depth.ask_depth if side == "buy" else depth.bid_depth

        if available_depth <= 0:
            return self.base_slippage_bps * 10  # 保守估计

        depth_ratio = notional / available_depth

        if depth_ratio <= 0.1:
            # 小单，影响很小
            return self.base_slippage_bps
        elif depth_ratio <= 0.5:
            # 中等单，线性增加
            return self.base_slippage_bps * (1 + depth_ratio)
        else:
            # 大单，指数增加
            return self.base_slippage_bps * (1 + depth_ratio ** 2)

    def set_base_slippage(self, slippage_bps: float):
        """设置基础滑点"""
        self.base_slippage_bps = slippage_bps
        logger.info(f"设置基础滑点: {slippage_bps}bps")

    def set_depth_impact_factor(self, factor: float):
        """设置深度影响因子"""
        self.depth_impact_factor = factor
        logger.info(f"设置深度影响因子: {factor}")

    def set_latency_penalty_factor(self, factor: float):
        """设置延迟惩罚因子"""
        self.latency_penalty_factor = factor
        logger.info(f"设置延迟惩罚因子: {factor}")
