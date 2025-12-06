"""
HedgeJob 模型定义

对冲任务的统一抽象，支持多交易所、多腿交易：
- wash_trade: 刷量交易
- arbitrage: 套利交易
- hedge_rebalance: 对冲再平衡
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional, Set
import uuid


@dataclass
class Leg:
    """
    交易腿定义

    一个 HedgeJob 由多个 Leg 组成，每个 Leg 代表一个交易所上的一个操作
    """
    exchange: str                    # 交易所名称
    side: Literal["buy", "sell"]    # 买入或卖出
    quantity: float                  # 数量
    instrument: str = "perp"         # 合约类型 (perp/spot/future)

    def __post_init__(self):
        """验证腿数据"""
        if self.quantity <= 0:
            raise ValueError(f"Leg quantity must be positive, got {self.quantity}")
        if not self.exchange:
            raise ValueError("Leg exchange cannot be empty")


@dataclass
class HedgeJob:
    """
    对冲任务定义

    统一的任务抽象，包含：
    - 多个交易腿 (Leg)
    - 策略类型 (wash/arb/hedge)
    - 预期收益和成交量
    - 元数据
    """
    # 核心标识
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_type: str = ""          # "wash", "arb", "hedge_rebalance"
    symbol: str = ""                 # "BTC/USDT"

    # 交易腿
    legs: List[Leg] = field(default_factory=list)

    # 财务指标
    notional: float = 0.0            # 名义金额 (USD)
    expected_edge_bps: float = 0.0   # 预期收益 (basis points)
    est_volume: float = 0.0          # 预估成交量 (USD)

    # 时间戳
    created_at: datetime = field(default_factory=datetime.utcnow)

    # 扩展元数据
    metadata: Dict = field(default_factory=dict)

    @property
    def exchanges(self) -> Set[str]:
        """从交易腿中提取所有交易所"""
        return {leg.exchange for leg in self.legs}

    @property
    def is_cross_exchange(self) -> bool:
        """是否为跨交易所任务"""
        return len(self.exchanges) > 1

    @property
    def total_buy_quantity(self) -> float:
        """总买入数量"""
        return sum(leg.quantity for leg in self.legs if leg.side == "buy")

    @property
    def total_sell_quantity(self) -> float:
        """总卖出数量"""
        return sum(leg.quantity for leg in self.legs if leg.side == "sell")

    @property
    def is_balanced(self) -> bool:
        """买卖是否平衡（套利/对冲任务应该平衡）"""
        return abs(self.total_buy_quantity - self.total_sell_quantity) < 1e-6

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        验证任务合法性

        Returns:
            (is_valid, error_message)
        """
        # 检查基础字段
        if not self.strategy_type:
            return False, "strategy_type is required"

        if not self.symbol:
            return False, "symbol is required"

        if self.notional <= 0:
            return False, f"notional must be positive, got {self.notional}"

        # 检查交易腿
        if not self.legs:
            return False, "at least one leg is required"

        # 验证每个腿
        for i, leg in enumerate(self.legs):
            try:
                leg.__post_init__()
            except ValueError as e:
                return False, f"leg[{i}] validation failed: {e}"

        # 套利和对冲任务应该买卖平衡
        if self.strategy_type in ["arb", "arbitrage", "hedge_rebalance"]:
            if not self.is_balanced:
                return False, (
                    f"Arbitrage/hedge job must be balanced: "
                    f"buy={self.total_buy_quantity:.6f}, sell={self.total_sell_quantity:.6f}"
                )

        return True, None

    def __str__(self) -> str:
        """人类可读的任务描述"""
        exchanges_str = ", ".join(sorted(self.exchanges))
        return (
            f"HedgeJob({self.job_id[:8]}..., "
            f"type={self.strategy_type}, "
            f"symbol={self.symbol}, "
            f"exchanges=[{exchanges_str}], "
            f"notional=${self.notional:,.0f}, "
            f"legs={len(self.legs)})"
        )


# 辅助函数

def create_wash_job(
    exchange: str,
    symbol: str,
    quantity: float,
    notional: float,
    expected_edge_bps: float = 0.0,
    metadata: Optional[Dict] = None,
) -> HedgeJob:
    """
    创建刷量任务

    刷量任务通常是单边的，只在一个交易所上进行
    """
    return HedgeJob(
        strategy_type="wash",
        symbol=symbol,
        legs=[
            Leg(exchange=exchange, side="buy", quantity=quantity / 2),
            Leg(exchange=exchange, side="sell", quantity=quantity / 2),
        ],
        notional=notional,
        expected_edge_bps=expected_edge_bps,
        est_volume=notional * 2,  # 买+卖
        metadata=metadata or {},
    )


def create_arb_job(
    buy_exchange: str,
    sell_exchange: str,
    symbol: str,
    quantity: float,
    notional: float,
    expected_edge_bps: float,
    metadata: Optional[Dict] = None,
) -> HedgeJob:
    """
    创建套利任务

    套利任务跨两个交易所，买入低价卖出高价
    """
    return HedgeJob(
        strategy_type="arb",
        symbol=symbol,
        legs=[
            Leg(exchange=buy_exchange, side="buy", quantity=quantity),
            Leg(exchange=sell_exchange, side="sell", quantity=quantity),
        ],
        notional=notional,
        expected_edge_bps=expected_edge_bps,
        est_volume=notional * 2,  # 双边成交
        metadata=metadata or {},
    )


def create_hedge_rebalance_job(
    legs: List[Leg],
    symbol: str,
    notional: float,
    metadata: Optional[Dict] = None,
) -> HedgeJob:
    """
    创建对冲再平衡任务

    支持多交易所、多腿的复杂对冲操作
    """
    return HedgeJob(
        strategy_type="hedge_rebalance",
        symbol=symbol,
        legs=legs,
        notional=notional,
        expected_edge_bps=0.0,  # 对冲再平衡通常不追求收益
        est_volume=notional * len(legs),
        metadata=metadata or {},
    )
