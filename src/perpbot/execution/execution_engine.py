"""
ExecutionEngine - 执行引擎

实现三种执行模式：
- SAFE_TAKER_ONLY: 双边 taker
- HYBRID_HEDGE_TAKER: 对冲腿 taker + 返佣腿 maker（推荐）
- DOUBLE_MAKER_OPPORTUNISTIC: 双边 maker（高风险）

包含：
- 填单风险管理
- 自动降级机制
- 超时 fallback
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from perpbot.execution.execution_mode import (
    ExecutionConfig,
    ExecutionMode,
    OrderTypeDecision,
    decide_order_types,
    validate_execution_constraints,
)
from perpbot.execution.maker_fill_estimator import MakerFillEstimator
from perpbot.execution.maker_tracker import MakerTracker
from perpbot.scoring.fee_model import FeeModel
from perpbot.scoring.slippage_model import OrderbookDepth, SlippageModel


logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """订单状态"""

    PENDING = "pending"  # 待提交
    SUBMITTED = "submitted"  # 已提交
    PARTIAL = "partial"  # 部分成交
    FILLED = "filled"  # 已成交
    CANCELLED = "cancelled"  # 已取消
    FAILED = "failed"  # 失败


@dataclass
class OrderResult:
    """订单执行结果"""

    # 订单 ID
    order_id: str

    # 交易所
    exchange: str

    # 交易对
    symbol: str

    # 方向
    side: str  # "buy" or "sell"

    # 订单类型
    order_type: str  # "maker" or "taker"

    # 名义金额
    notional: float

    # 成交价格
    fill_price: float

    # 订单状态
    status: OrderStatus

    # 实际手续费
    actual_fee: float

    # 是否 fallback
    is_fallback: bool = False

    # 执行时间（毫秒）
    execution_time_ms: float = 0.0

    # 错误信息
    error: Optional[str] = None


@dataclass
class HedgeExecutionResult:
    """对冲执行结果"""

    # 开仓结果
    open_result: OrderResult

    # 平仓结果
    close_result: OrderResult

    # 是否成功
    success: bool

    # 总手续费
    total_fee: float

    # 总执行时间
    total_execution_time_ms: float

    # 未对冲时间（毫秒）
    unhedged_time_ms: float

    # 未对冲金额峰值（USDT）
    peak_unhedged_notional: float

    # 是否发生 fallback
    had_fallback: bool

    # 备注
    note: str = ""


class ExecutionEngine:
    """
    执行引擎

    负责执行对冲任务，管理 maker/taker 订单，处理填单风险
    """

    def __init__(
        self,
        fee_model: FeeModel,
        slippage_model: SlippageModel,
        config: ExecutionConfig,
        maker_tracker: Optional[MakerTracker] = None,
        fill_estimator: Optional[MakerFillEstimator] = None,
    ):
        """
        初始化执行引擎

        Args:
            fee_model: 费率模型
            slippage_model: 滑点模型
            config: 执行配置
            maker_tracker: Maker 跟踪器（可选）
            fill_estimator: 填单概率估计器（可选）
        """
        self.fee_model = fee_model
        self.slippage_model = slippage_model
        self.config = config

        self.maker_tracker = maker_tracker or MakerTracker()
        self.fill_estimator = fill_estimator or MakerFillEstimator()

        logger.info(
            f"初始化执行引擎: mode={config.mode.value}, "
            f"max_unhedged={config.max_unhedged_notional_usd} USDT, "
            f"max_time={config.max_unhedged_time_ms}ms"
        )

    async def execute_hedge(
        self,
        # 交易信息
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        buy_price: float,
        sell_price: float,
        # 流动性信息
        buy_liquidity_score: float = 0.8,
        sell_liquidity_score: float = 0.8,
        # 盘口信息（可选）
        buy_orderbook: Optional[OrderbookDepth] = None,
        sell_orderbook: Optional[OrderbookDepth] = None,
        # 预期收益（用于验证）
        expected_pnl: Optional[float] = None,
    ) -> HedgeExecutionResult:
        """
        执行对冲任务

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            notional: 名义金额
            buy_price: 买入价格
            sell_price: 卖出价格
            buy_liquidity_score: 买入流动性评分
            sell_liquidity_score: 卖出流动性评分
            buy_orderbook: 买入盘口
            sell_orderbook: 卖出盘口
            expected_pnl: 预期收益

        Returns:
            执行结果
        """
        start_time = time.time()

        # 1. 检查是否已降级
        execution_mode = self.config.mode
        if self.maker_tracker.is_degraded(buy_exchange, sell_exchange):
            logger.warning(
                f"交易所对 {buy_exchange}<->{sell_exchange} 已降级，"
                f"强制使用 SAFE_TAKER_ONLY"
            )
            execution_mode = ExecutionMode.SAFE_TAKER_ONLY

        # 2. 决定订单类型
        buy_maker_fee = self.fee_model.get_fee(buy_exchange, symbol, "buy", "maker")
        sell_maker_fee = self.fee_model.get_fee(sell_exchange, symbol, "sell", "maker")
        buy_taker_fee = self.fee_model.get_fee(buy_exchange, symbol, "buy", "taker")
        sell_taker_fee = self.fee_model.get_fee(sell_exchange, symbol, "sell", "taker")

        decision = decide_order_types(
            execution_mode=execution_mode,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            buy_liquidity_score=buy_liquidity_score,
            sell_liquidity_score=sell_liquidity_score,
            buy_maker_fee=buy_maker_fee,
            sell_maker_fee=sell_maker_fee,
            buy_taker_fee=buy_taker_fee,
            sell_taker_fee=sell_taker_fee,
            notional=notional,
        )

        # 3. 验证执行约束
        valid, reason = validate_execution_constraints(
            execution_mode=execution_mode,
            notional=notional,
            expected_pnl=expected_pnl or 0.0,
            is_wash_mode=self.config.is_wash_mode,
            config=self.config,
        )

        if not valid:
            logger.error(f"执行约束验证失败: {reason}")
            # 返回失败结果
            return self._create_failed_result(buy_exchange, sell_exchange, symbol, notional, reason)

        # 4. 执行订单
        logger.info(
            f"执行对冲: {buy_exchange} 买入 / {sell_exchange} 卖出, "
            f"notional={notional:.2f}, mode={execution_mode.value}, "
            f"open={decision.open_order_type}, close={decision.close_order_type}"
        )

        if execution_mode == ExecutionMode.SAFE_TAKER_ONLY:
            # 双边 taker
            result = await self._execute_double_taker(
                buy_exchange, sell_exchange, symbol, notional,
                buy_price, sell_price, decision
            )
        elif execution_mode == ExecutionMode.HYBRID_HEDGE_TAKER:
            # 混合模式
            result = await self._execute_hybrid_hedge_taker(
                buy_exchange, sell_exchange, symbol, notional,
                buy_price, sell_price, decision,
                buy_orderbook, sell_orderbook
            )
        else:
            # DOUBLE_MAKER（暂不实现，返回失败）
            logger.error(f"不支持的执行模式: {execution_mode}")
            return self._create_failed_result(
                buy_exchange, sell_exchange, symbol, notional,
                "DOUBLE_MAKER 模式暂未实现"
            )

        # 5. 记录到 MakerTracker
        if decision.may_fallback:
            self.maker_tracker.record_maker_attempt(
                buy_exchange,
                sell_exchange,
                is_filled=result.success,
                is_timeout=not result.success,
                is_fallback=result.had_fallback,
            )

        total_time = (time.time() - start_time) * 1000
        logger.info(
            f"对冲执行完成: success={result.success}, "
            f"fee={result.total_fee:.4f}, time={total_time:.0f}ms, "
            f"fallback={result.had_fallback}"
        )

        return result

    async def _execute_double_taker(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        buy_price: float,
        sell_price: float,
        decision: OrderTypeDecision,
    ) -> HedgeExecutionResult:
        """
        执行双边 taker 模式

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            notional: 名义金额
            buy_price: 买入价格
            sell_price: 卖出价格
            decision: 订单类型决策

        Returns:
            执行结果
        """
        start_time = time.time()

        # 并行执行双边 taker
        buy_task = self._submit_taker_order(
            buy_exchange, symbol, "buy", notional, buy_price
        )
        sell_task = self._submit_taker_order(
            sell_exchange, symbol, "sell", notional, sell_price
        )

        buy_result, sell_result = await asyncio.gather(buy_task, sell_task)

        total_time = (time.time() - start_time) * 1000

        success = (
            buy_result.status == OrderStatus.FILLED
            and sell_result.status == OrderStatus.FILLED
        )

        return HedgeExecutionResult(
            open_result=buy_result,
            close_result=sell_result,
            success=success,
            total_fee=buy_result.actual_fee + sell_result.actual_fee,
            total_execution_time_ms=total_time,
            unhedged_time_ms=0.0,  # 双边同时执行，无未对冲时间
            peak_unhedged_notional=0.0,
            had_fallback=False,
            note="双边 taker，无填单风险",
        )

    async def _execute_hybrid_hedge_taker(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        buy_price: float,
        sell_price: float,
        decision: OrderTypeDecision,
        buy_orderbook: Optional[OrderbookDepth],
        sell_orderbook: Optional[OrderbookDepth],
    ) -> HedgeExecutionResult:
        """
        执行混合模式：对冲腿 taker + 返佣腿 maker

        Args:
            buy_exchange: 买入交易所
            sell_exchange: 卖出交易所
            symbol: 交易对
            notional: 名义金额
            buy_price: 买入价格
            sell_price: 卖出价格
            decision: 订单类型决策
            buy_orderbook: 买入盘口
            sell_orderbook: 卖出盘口

        Returns:
            执行结果
        """
        start_time = time.time()
        had_fallback = False
        unhedged_start = 0.0

        # 确定对冲腿和返佣腿
        if decision.hedge_leg == "open":
            # 买入是对冲腿（taker），卖出是返佣腿（maker）
            hedge_exchange = buy_exchange
            hedge_side = "buy"
            hedge_price = buy_price
            rebate_exchange = sell_exchange
            rebate_side = "sell"
            rebate_price = sell_price
            rebate_orderbook = sell_orderbook
        else:
            # 卖出是对冲腿（taker），买入是返佣腿（maker）
            hedge_exchange = sell_exchange
            hedge_side = "sell"
            hedge_price = sell_price
            rebate_exchange = buy_exchange
            rebate_side = "buy"
            rebate_price = buy_price
            rebate_orderbook = buy_orderbook

        # 1. 先执行对冲腿（taker，立即成交）
        logger.info(f"[对冲腿] {hedge_exchange} {hedge_side} taker")
        hedge_result = await self._submit_taker_order(
            hedge_exchange, symbol, hedge_side, notional, hedge_price
        )

        if hedge_result.status != OrderStatus.FILLED:
            # 对冲腿失败，放弃整个任务
            logger.error(f"对冲腿执行失败: {hedge_result.error}")
            return self._create_failed_result(
                buy_exchange, sell_exchange, symbol, notional,
                f"对冲腿失败: {hedge_result.error}"
            )

        # 记录未对冲开始时间
        unhedged_start = time.time()

        # 2. 执行返佣腿（maker，可能需要等待）
        logger.info(f"[返佣腿] {rebate_exchange} {rebate_side} maker (post-only)")

        # 估算填单概率
        mid_price = (buy_price + sell_price) / 2
        fill_probability = self.fill_estimator.estimate_fill_probability(
            order_price=rebate_price,
            mid_price=mid_price,
            side=rebate_side,
            notional=notional,
            orderbook_depth=rebate_orderbook,
        )

        logger.info(f"Maker 填单概率估计: {fill_probability:.1%}")

        # 提交 maker 订单
        rebate_result = await self._submit_maker_order(
            rebate_exchange, symbol, rebate_side, notional, rebate_price,
            timeout_ms=self.config.maker_order_timeout_ms
        )

        unhedged_time_ms = (time.time() - unhedged_start) * 1000

        # 3. 检查是否需要 fallback
        if rebate_result.status != OrderStatus.FILLED:
            # Maker 未成交，检查是否超过阈值
            if (
                unhedged_time_ms > self.config.max_unhedged_time_ms
                or notional > self.config.max_unhedged_notional_usd
            ):
                logger.warning(
                    f"Maker 订单超时或金额过大，fallback 到 taker: "
                    f"time={unhedged_time_ms:.0f}ms, notional={notional:.2f}"
                )

                # 取消 maker 订单
                await self._cancel_order(rebate_result.order_id)

                # 使用 taker 对冲
                rebate_result = await self._submit_taker_order(
                    rebate_exchange, symbol, rebate_side, notional, rebate_price
                )
                had_fallback = True

        total_time = (time.time() - start_time) * 1000

        # 4. 构造结果
        if decision.hedge_leg == "open":
            open_result = hedge_result
            close_result = rebate_result
        else:
            open_result = rebate_result
            close_result = hedge_result

        success = (
            open_result.status == OrderStatus.FILLED
            and close_result.status == OrderStatus.FILLED
        )

        return HedgeExecutionResult(
            open_result=open_result,
            close_result=close_result,
            success=success,
            total_fee=open_result.actual_fee + close_result.actual_fee,
            total_execution_time_ms=total_time,
            unhedged_time_ms=unhedged_time_ms,
            peak_unhedged_notional=notional,
            had_fallback=had_fallback,
            note=f"混合模式, fillback={had_fallback}",
        )

    async def _submit_taker_order(
        self, exchange: str, symbol: str, side: str, notional: float, price: float
    ) -> OrderResult:
        """
        提交 taker 订单（模拟）

        Args:
            exchange: 交易所
            symbol: 交易对
            side: 方向
            notional: 名义金额
            price: 价格

        Returns:
            订单结果
        """
        start = time.time()

        # 模拟延迟
        await asyncio.sleep(0.05)  # 50ms

        # 计算手续费
        fee_rate = self.fee_model.get_fee(exchange, symbol, side, "taker")
        actual_fee = notional * fee_rate

        execution_time = (time.time() - start) * 1000

        logger.debug(
            f"Taker 订单成交: {exchange} {symbol} {side}, "
            f"notional={notional:.2f}, fee={actual_fee:.4f}, time={execution_time:.0f}ms"
        )

        return OrderResult(
            order_id=f"taker_{exchange}_{int(time.time()*1000)}",
            exchange=exchange,
            symbol=symbol,
            side=side,
            order_type="taker",
            notional=notional,
            fill_price=price,
            status=OrderStatus.FILLED,
            actual_fee=actual_fee,
            is_fallback=False,
            execution_time_ms=execution_time,
        )

    async def _submit_maker_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        notional: float,
        price: float,
        timeout_ms: float = 3000.0,
    ) -> OrderResult:
        """
        提交 maker 订单（模拟，可能不成交）

        Args:
            exchange: 交易所
            symbol: 交易对
            side: 方向
            notional: 名义金额
            price: 价格
            timeout_ms: 超时时间（毫秒）

        Returns:
            订单结果
        """
        start = time.time()
        order_id = f"maker_{exchange}_{int(time.time()*1000)}"

        # 模拟填单过程（简化：50% 概率成交）
        wait_time = min(timeout_ms / 1000, 1.0)
        await asyncio.sleep(wait_time)

        # 简单模拟：50% 成交概率
        import random
        is_filled = random.random() > 0.5

        execution_time = (time.time() - start) * 1000

        if is_filled:
            # 成交
            fee_rate = self.fee_model.get_fee(exchange, symbol, side, "maker")
            actual_fee = notional * fee_rate

            logger.debug(
                f"Maker 订单成交: {exchange} {symbol} {side}, "
                f"notional={notional:.2f}, fee={actual_fee:.4f}, time={execution_time:.0f}ms"
            )

            return OrderResult(
                order_id=order_id,
                exchange=exchange,
                symbol=symbol,
                side=side,
                order_type="maker",
                notional=notional,
                fill_price=price,
                status=OrderStatus.FILLED,
                actual_fee=actual_fee,
                is_fallback=False,
                execution_time_ms=execution_time,
            )
        else:
            # 未成交
            logger.debug(
                f"Maker 订单未成交: {exchange} {symbol} {side}, "
                f"time={execution_time:.0f}ms"
            )

            return OrderResult(
                order_id=order_id,
                exchange=exchange,
                symbol=symbol,
                side=side,
                order_type="maker",
                notional=notional,
                fill_price=0.0,
                status=OrderStatus.PENDING,
                actual_fee=0.0,
                is_fallback=False,
                execution_time_ms=execution_time,
            )

    async def _cancel_order(self, order_id: str):
        """取消订单（模拟）"""
        logger.debug(f"取消订单: {order_id}")
        await asyncio.sleep(0.01)

    def _create_failed_result(
        self,
        buy_exchange: str,
        sell_exchange: str,
        symbol: str,
        notional: float,
        reason: str,
    ) -> HedgeExecutionResult:
        """创建失败结果"""
        failed_order = OrderResult(
            order_id="failed",
            exchange=buy_exchange,
            symbol=symbol,
            side="buy",
            order_type="taker",
            notional=notional,
            fill_price=0.0,
            status=OrderStatus.FAILED,
            actual_fee=0.0,
            error=reason,
        )

        return HedgeExecutionResult(
            open_result=failed_order,
            close_result=failed_order,
            success=False,
            total_fee=0.0,
            total_execution_time_ms=0.0,
            unhedged_time_ms=0.0,
            peak_unhedged_notional=0.0,
            had_fallback=False,
            note=f"执行失败: {reason}",
        )
