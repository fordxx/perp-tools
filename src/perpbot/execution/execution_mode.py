"""
ExecutionMode - 执行模式枚举

定义三种执行模式：
- SAFE_TAKER_ONLY: 安全模式，双边 taker
- HYBRID_HEDGE_TAKER: 混合模式，对冲腿 taker + 返佣腿 maker（推荐）
- DOUBLE_MAKER_OPPORTUNISTIC: 双边 maker 机会主义（高风险，默认不用）
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ExecutionMode(Enum):
    """执行模式枚举"""

    # 安全模式：双边 taker，无填单风险
    SAFE_TAKER_ONLY = "safe_taker_only"

    # 混合模式：对冲腿 taker + 返佣腿 maker（推荐主模式）
    HYBRID_HEDGE_TAKER = "hybrid_hedge_taker"

    # 双边 maker 机会主义模式（高风险，仅用于小额测试）
    DOUBLE_MAKER_OPPORTUNISTIC = "double_maker_opportunistic"


@dataclass
class ExecutionConfig:
    """执行配置"""

    # 执行模式
    mode: ExecutionMode = ExecutionMode.HYBRID_HEDGE_TAKER

    # === HYBRID 模式参数 ===
    # 最大未对冲名义金额（USDT）
    max_unhedged_notional_usd: float = 100.0

    # 最大未对冲时间（毫秒）
    max_unhedged_time_ms: float = 500.0

    # === DOUBLE_MAKER 模式参数 ===
    # DOUBLE_MAKER 模式允许的最大 notional（USDT）
    double_maker_max_notional: float = 50.0

    # DOUBLE_MAKER 模式的最大未对冲时间（更严格）
    double_maker_max_unhedged_time_ms: float = 200.0

    # === Maker 填单参数 ===
    # Maker 订单超时时间（毫秒）
    maker_order_timeout_ms: float = 3000.0

    # Maker 订单价格离 mid 的最大偏移（bps）
    # 如果挂单价离 mid 太远，填单概率太低
    maker_max_offset_bps: float = 5.0

    # === 刷量模式参数 ===
    # 是否为刷量模式
    is_wash_mode: bool = False

    # 刷量模式是否允许双边 taker + 负收益
    wash_allow_negative_pnl: bool = False


@dataclass
class OrderTypeDecision:
    """订单类型决策结果"""

    # 开仓交易所
    open_exchange: str

    # 开仓订单类型（"maker" 或 "taker"）
    open_order_type: str

    # 平仓交易所
    close_exchange: str

    # 平仓订单类型
    close_order_type: str

    # 对冲腿（哪个是对冲腿？）
    hedge_leg: str  # "open" or "close"

    # 返佣腿（哪个是返佣腿？）
    rebate_leg: str  # "open" or "close"

    # 预期手续费成本（开仓）
    open_fee_cost: float

    # 预期手续费成本（平仓）
    close_fee_cost: float

    # 总手续费成本
    total_fee_cost: float

    # 是否可能发生 maker → taker fallback
    may_fallback: bool = False

    # Maker 填单概率估计（0-1）
    maker_fill_probability: Optional[float] = None

    # 备注
    note: str = ""


def decide_order_types(
    execution_mode: ExecutionMode,
    buy_exchange: str,
    sell_exchange: str,
    buy_liquidity_score: float,  # 买入方流动性评分（0-1）
    sell_liquidity_score: float,  # 卖出方流动性评分
    buy_maker_fee: float,  # 买入方 maker 费率（可能为负）
    sell_maker_fee: float,  # 卖出方 maker 费率
    buy_taker_fee: float,  # 买入方 taker 费率
    sell_taker_fee: float,  # 卖出方 taker 费率
    notional: float,  # 名义金额
) -> OrderTypeDecision:
    """
    根据执行模式决定订单类型

    Args:
        execution_mode: 执行模式
        buy_exchange: 买入交易所
        sell_exchange: 卖出交易所
        buy_liquidity_score: 买入方流动性评分（0-1，越高越好）
        sell_liquidity_score: 卖出方流动性评分
        buy_maker_fee: 买入方 maker 费率
        sell_maker_fee: 卖出方 maker 费率
        buy_taker_fee: 买入方 taker 费率
        sell_taker_fee: 卖出方 taker 费率
        notional: 名义金额

    Returns:
        OrderTypeDecision
    """
    if execution_mode == ExecutionMode.SAFE_TAKER_ONLY:
        # 安全模式：双边 taker
        return OrderTypeDecision(
            open_exchange=buy_exchange,
            open_order_type="taker",
            close_exchange=sell_exchange,
            close_order_type="taker",
            hedge_leg="both",
            rebate_leg="none",
            open_fee_cost=notional * buy_taker_fee,
            close_fee_cost=notional * sell_taker_fee,
            total_fee_cost=notional * (buy_taker_fee + sell_taker_fee),
            may_fallback=False,
            note="双边 taker，无填单风险",
        )

    elif execution_mode == ExecutionMode.HYBRID_HEDGE_TAKER:
        # 混合模式：对冲腿 taker + 返佣腿 maker
        # 选择流动性更好的一侧作为对冲腿
        if buy_liquidity_score >= sell_liquidity_score:
            # 买入方流动性好 → 买入用 taker，卖出用 maker
            hedge_leg = "open"
            rebate_leg = "close"
            open_order_type = "taker"
            close_order_type = "maker"
            open_fee_cost = notional * buy_taker_fee
            close_fee_cost = notional * sell_maker_fee
        else:
            # 卖出方流动性好 → 卖出用 taker，买入用 maker
            hedge_leg = "close"
            rebate_leg = "open"
            open_order_type = "maker"
            close_order_type = "taker"
            open_fee_cost = notional * buy_maker_fee
            close_fee_cost = notional * sell_taker_fee

        return OrderTypeDecision(
            open_exchange=buy_exchange,
            open_order_type=open_order_type,
            close_exchange=sell_exchange,
            close_order_type=close_order_type,
            hedge_leg=hedge_leg,
            rebate_leg=rebate_leg,
            open_fee_cost=open_fee_cost,
            close_fee_cost=close_fee_cost,
            total_fee_cost=open_fee_cost + close_fee_cost,
            may_fallback=True,  # maker 可能 fallback 到 taker
            maker_fill_probability=None,  # 需要后续计算
            note=f"对冲腿={hedge_leg}, 返佣腿={rebate_leg}",
        )

    elif execution_mode == ExecutionMode.DOUBLE_MAKER_OPPORTUNISTIC:
        # 双边 maker 机会主义
        return OrderTypeDecision(
            open_exchange=buy_exchange,
            open_order_type="maker",
            close_exchange=sell_exchange,
            close_order_type="maker",
            hedge_leg="none",
            rebate_leg="both",
            open_fee_cost=notional * buy_maker_fee,
            close_fee_cost=notional * sell_maker_fee,
            total_fee_cost=notional * (buy_maker_fee + sell_maker_fee),
            may_fallback=True,  # 双边都可能 fallback
            maker_fill_probability=None,
            note="双边 maker，高风险",
        )

    else:
        raise ValueError(f"未知的执行模式: {execution_mode}")


def validate_execution_constraints(
    execution_mode: ExecutionMode,
    notional: float,
    expected_pnl: float,
    is_wash_mode: bool,
    config: ExecutionConfig,
) -> tuple[bool, str]:
    """
    验证执行约束

    Args:
        execution_mode: 执行模式
        notional: 名义金额
        expected_pnl: 预期收益
        is_wash_mode: 是否为刷量模式
        config: 执行配置

    Returns:
        (是否通过, 拒绝原因)
    """
    # 刷量模式约束
    if is_wash_mode:
        # 禁止"双边 taker + 预期负收益"
        if execution_mode == ExecutionMode.SAFE_TAKER_ONLY and expected_pnl < 0:
            return False, "刷量模式禁止双边 taker + 负收益"

    # DOUBLE_MAKER 约束
    if execution_mode == ExecutionMode.DOUBLE_MAKER_OPPORTUNISTIC:
        if notional > config.double_maker_max_notional:
            return (
                False,
                f"DOUBLE_MAKER 模式 notional 超限: "
                f"{notional:.2f} > {config.double_maker_max_notional:.2f}",
            )

    return True, ""
