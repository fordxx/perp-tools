"""
FeeModel - 手续费模型

支持：
- 每个交易所不同的 maker/taker 费率
- 刷量返佣机制
- VIP 等级费率
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional


logger = logging.getLogger(__name__)


@dataclass
class ExchangeFeeConfig:
    """交易所费率配置"""
    exchange: str
    maker_fee: float = 0.0002    # 0.02% (默认，可以为负表示返佣)
    taker_fee: float = 0.0005    # 0.05% (默认)

    # 刷量返佣（可选）
    wash_rebate_pct: float = 0.0  # 刷量返佣百分比

    # VIP 等级调整（可选）
    vip_discount: float = 0.0     # VIP 折扣（0-1）

    def get_fee(self, order_type: str) -> float:
        """
        获取指定订单类型的费率

        Args:
            order_type: "maker" 或 "taker"

        Returns:
            费率（可以为负表示返佣）
        """
        if order_type == "maker":
            return self.maker_fee * (1 - self.vip_discount)
        elif order_type == "taker":
            return self.taker_fee * (1 - self.vip_discount)
        else:
            raise ValueError(f"无效的 order_type: {order_type}，必须是 'maker' 或 'taker'")


class FeeModel:
    """
    手续费模型

    管理所有交易所的手续费配置，计算交易成本
    """

    # 默认费率配置
    DEFAULT_FEES = {
        "binance": ExchangeFeeConfig(
            exchange="binance",
            maker_fee=0.0002,   # 0.02%
            taker_fee=0.0004,   # 0.04%
        ),
        "okx": ExchangeFeeConfig(
            exchange="okx",
            maker_fee=0.0002,
            taker_fee=0.0005,   # 0.05%
        ),
        "edgex": ExchangeFeeConfig(
            exchange="edgex",
            maker_fee=-0.0001,  # -0.01% (负费率，maker 返佣！)
            taker_fee=0.0003,   # 0.03%
            wash_rebate_pct=0.5,  # 50% 返佣
        ),
        "bybit": ExchangeFeeConfig(
            exchange="bybit",
            maker_fee=0.0001,
            taker_fee=0.0006,   # 0.06%
        ),
        "hyperliquid": ExchangeFeeConfig(
            exchange="hyperliquid",
            maker_fee=-0.00005, # -0.005% (maker 返佣)
            taker_fee=0.00025,  # 0.025%
        ),
    }

    def __init__(self, custom_configs: Optional[Dict[str, ExchangeFeeConfig]] = None):
        """
        初始化手续费模型

        Args:
            custom_configs: 自定义费率配置（覆盖默认值）
        """
        self.configs = self.DEFAULT_FEES.copy()

        if custom_configs:
            self.configs.update(custom_configs)

        logger.info(f"初始化手续费模型: {len(self.configs)} 个交易所")

    def get_taker_fee(self, exchange: str, symbol: Optional[str] = None) -> float:
        """
        获取 Taker 费率

        Args:
            exchange: 交易所名称
            symbol: 交易对（预留，某些交易所不同交易对费率不同）

        Returns:
            Taker 费率（小数，如 0.0005 表示 0.05%）
        """
        config = self.configs.get(exchange)

        if not config:
            logger.warning(f"交易所 {exchange} 未配置费率，使用默认 0.05%")
            return 0.0005

        # 应用 VIP 折扣
        fee = config.taker_fee * (1 - config.vip_discount)

        return fee

    def get_maker_fee(self, exchange: str, symbol: Optional[str] = None) -> float:
        """
        获取 Maker 费率

        Args:
            exchange: 交易所名称
            symbol: 交易对

        Returns:
            Maker 费率（可能为负表示返佣）
        """
        config = self.configs.get(exchange)

        if not config:
            logger.warning(f"交易所 {exchange} 未配置费率，使用默认 0.02%")
            return 0.0002

        # 应用 VIP 折扣
        fee = config.maker_fee * (1 - config.vip_discount)

        return fee

    def get_fee(
        self,
        exchange: str,
        symbol: str,
        side: str,  # "buy" or "sell"
        order_type: str,  # "maker" or "taker"
    ) -> float:
        """
        获取指定订单的费率（统一接口）

        Args:
            exchange: 交易所
            symbol: 交易对
            side: 买卖方向（"buy" 或 "sell"）
            order_type: 订单类型（"maker" 或 "taker"）

        Returns:
            费率（可能为负表示返佣）
        """
        config = self.configs.get(exchange)

        if not config:
            logger.warning(f"交易所 {exchange} 未配置费率，使用默认值")
            return 0.0005 if order_type == "taker" else 0.0002

        return config.get_fee(order_type)

    def calculate_fee_cost(
        self,
        exchange: str,
        notional: float,
        is_taker: bool = True,
        is_wash_trade: bool = False,
    ) -> float:
        """
        计算手续费成本

        Args:
            exchange: 交易所
            notional: 名义金额
            is_taker: 是否为 Taker 单
            is_wash_trade: 是否为刷量交易（可能有返佣）

        Returns:
            手续费成本（USDT）
        """
        config = self.configs.get(exchange)

        if not config:
            # 默认费率
            fee_rate = 0.0005 if is_taker else 0.0002
        else:
            fee_rate = config.taker_fee if is_taker else config.maker_fee
            fee_rate *= (1 - config.vip_discount)

        # 计算基础手续费
        fee_cost = notional * fee_rate

        # 刷量返佣
        if is_wash_trade and config and config.wash_rebate_pct > 0:
            rebate = fee_cost * config.wash_rebate_pct
            fee_cost -= rebate
            logger.debug(
                f"刷量返佣: {exchange}, 原始费用={notional*fee_rate:.4f}, "
                f"返佣={rebate:.4f}, 净费用={fee_cost:.4f}"
            )

        return fee_cost

    def calculate_round_trip_fee(
        self,
        exchange: str,
        notional: float,
        both_taker: bool = True,
    ) -> float:
        """
        计算往返手续费（买入+卖出）

        Args:
            exchange: 交易所
            notional: 单边名义金额
            both_taker: 是否买卖都是 Taker

        Returns:
            往返手续费总成本
        """
        if both_taker:
            # 买入 + 卖出都是 taker
            return self.calculate_fee_cost(exchange, notional, is_taker=True) * 2
        else:
            # 买入 maker + 卖出 taker (或反过来)
            maker_cost = self.calculate_fee_cost(exchange, notional, is_taker=False)
            taker_cost = self.calculate_fee_cost(exchange, notional, is_taker=True)
            return maker_cost + taker_cost

    def calculate_cross_exchange_fee(
        self,
        buy_exchange: str,
        sell_exchange: str,
        notional: float,
    ) -> float:
        """
        计算跨交易所套利手续费

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            notional: 名义金额

        Returns:
            总手续费
        """
        buy_fee = self.calculate_fee_cost(buy_exchange, notional, is_taker=True)
        sell_fee = self.calculate_fee_cost(sell_exchange, notional, is_taker=True)

        return buy_fee + sell_fee

    def set_vip_discount(self, exchange: str, discount: float):
        """
        设置 VIP 折扣

        Args:
            exchange: 交易所
            discount: 折扣率（0-1，如 0.1 表示 10% 折扣）
        """
        if exchange in self.configs:
            self.configs[exchange].vip_discount = discount
            logger.info(f"设置 {exchange} VIP 折扣: {discount*100:.1f}%")
        else:
            logger.warning(f"交易所 {exchange} 未配置")

    def set_wash_rebate(self, exchange: str, rebate_pct: float):
        """
        设置刷量返佣比例

        Args:
            exchange: 交易所
            rebate_pct: 返佣比例（0-1，如 0.5 表示 50% 返佣）
        """
        if exchange in self.configs:
            self.configs[exchange].wash_rebate_pct = rebate_pct
            logger.info(f"设置 {exchange} 刷量返佣: {rebate_pct*100:.1f}%")
        else:
            logger.warning(f"交易所 {exchange} 未配置")

    def get_config(self, exchange: str) -> Optional[ExchangeFeeConfig]:
        """获取交易所费率配置"""
        return self.configs.get(exchange)

    def get_all_exchanges(self) -> list:
        """获取所有配置的交易所"""
        return list(self.configs.keys())
