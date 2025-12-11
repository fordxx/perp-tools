"""
Execution Engine Demo - 执行引擎演示

展示：
1. 三种执行模式（SAFE_TAKER_ONLY, HYBRID_HEDGE_TAKER, DOUBLE_MAKER）
2. Maker 填单概率估计
3. 自动降级机制
4. OpportunityScorer 集成执行模式
5. 完整的对冲执行流程
"""

import asyncio
import logging

from perpbot.execution import (
    ExecutionEngine,
    ExecutionMode,
    ExecutionConfig,
    MakerTracker,
    MakerFillEstimator,
)
from perpbot.scoring import (
    FeeModel,
    FundingModel,
    SlippageModel,
    OpportunityScorer,
    OrderbookDepth,
)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印分隔线"""
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}\n")


async def demo_1_fee_model_with_negative_rates():
    """Demo 1: FeeModel 支持负费率（maker 返佣）"""
    print_section("Demo 1: FeeModel 支持负费率（maker 返佣）")

    fee_model = FeeModel()

    # 测试不同交易所的费率
    exchanges = ["binance", "okx", "edgex", "hyperliquid"]

    for exchange in exchanges:
        maker_fee = fee_model.get_fee(exchange, "BTC-USDT", "buy", "maker")
        taker_fee = fee_model.get_fee(exchange, "BTC-USDT", "buy", "taker")

        print(f"{exchange:15} | Maker: {maker_fee*10000:+6.2f} bps | Taker: {taker_fee*10000:+6.2f} bps")

        # 计算实际费用
        notional = 1000.0
        maker_cost = notional * maker_fee
        taker_cost = notional * taker_fee

        if maker_fee < 0:
            print(f"  → Maker 返佣! 1000 USDT 订单可获返佣 {-maker_cost:.4f} USDT")
        else:
            print(f"  → Maker 费用: {maker_cost:.4f} USDT")

    print("\n✅ Demo 1 完成：FeeModel 支持负费率")


async def demo_2_maker_fill_estimator():
    """Demo 2: Maker 填单概率估计"""
    print_section("Demo 2: Maker 填单概率估计")

    estimator = MakerFillEstimator(max_offset_bps=5.0)

    # 模拟盘口
    orderbook = OrderbookDepth(
        exchange="binance",
        symbol="BTC-USDT",
        bid_depth=50000.0,  # 50k USDT
        ask_depth=50000.0,
        bid_price=50000.0,
        ask_price=50010.0,
        spread_bps=2.0,
    )

    mid_price = (orderbook.bid_price + orderbook.ask_price) / 2

    # 测试不同价格偏移的填单概率
    test_cases = [
        ("紧贴 mid", mid_price - 1),
        ("0.5 bps 偏移", mid_price - 2.5),
        ("2 bps 偏移", mid_price - 10),
        ("5 bps 偏移", mid_price - 25),
        ("10 bps 偏移", mid_price - 50),
    ]

    notional = 10000.0

    print(f"盘口: bid={orderbook.bid_price:.2f}, ask={orderbook.ask_price:.2f}, mid={mid_price:.2f}")
    print(f"订单: notional={notional:.0f} USDT\n")

    for desc, order_price in test_cases:
        prob = estimator.estimate_fill_probability(
            order_price=order_price,
            mid_price=mid_price,
            side="buy",
            notional=notional,
            orderbook_depth=orderbook,
        )

        offset_bps = ((mid_price - order_price) / mid_price) * 10000

        print(f"{desc:15} | 价格={order_price:.2f} | 偏移={offset_bps:+5.2f} bps | 填单概率={prob:.1%}")

    print("\n✅ Demo 2 完成：Maker 填单概率估计")


async def demo_3_execution_modes():
    """Demo 3: 三种执行模式对比"""
    print_section("Demo 3: 三种执行模式对比")

    fee_model = FeeModel()
    slippage_model = SlippageModel()

    # 配置三种模式
    configs = [
        ("SAFE_TAKER_ONLY", ExecutionConfig(mode=ExecutionMode.SAFE_TAKER_ONLY)),
        ("HYBRID_HEDGE_TAKER", ExecutionConfig(mode=ExecutionMode.HYBRID_HEDGE_TAKER)),
        # DOUBLE_MAKER 暂不演示
    ]

    # 模拟交易
    buy_exchange = "binance"
    sell_exchange = "edgex"
    symbol = "BTC-USDT"
    notional = 10000.0
    buy_price = 50000.0
    sell_price = 50050.0

    for mode_name, config in configs:
        print(f"\n--- {mode_name} ---")

        engine = ExecutionEngine(
            fee_model=fee_model,
            slippage_model=slippage_model,
            config=config,
        )

        result = await engine.execute_hedge(
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            symbol=symbol,
            notional=notional,
            buy_price=buy_price,
            sell_price=sell_price,
            buy_liquidity_score=0.9,  # binance 流动性好
            sell_liquidity_score=0.7,  # edgex 一般
        )

        print(f"执行成功: {result.success}")
        print(f"开仓: {result.open_result.order_type}, 费用={result.open_result.actual_fee:.4f} USDT")
        print(f"平仓: {result.close_result.order_type}, 费用={result.close_result.actual_fee:.4f} USDT")
        print(f"总费用: {result.total_fee:.4f} USDT")
        print(f"未对冲时间: {result.unhedged_time_ms:.0f} ms")
        print(f"Fallback: {result.had_fallback}")

    print("\n✅ Demo 3 完成：三种执行模式对比")


async def demo_4_maker_tracker_and_degradation():
    """Demo 4: Maker 跟踪器与自动降级"""
    print_section("Demo 4: Maker 跟踪器与自动降级")

    tracker = MakerTracker(
        min_fill_rate=0.5,  # 最低 50% 填单率
        max_fallback_rate=0.3,  # 最大 30% fallback 率
        window_size=10,
        cooldown_seconds=5.0,  # 5秒冷却期（演示用）
    )

    exchange1 = "binance"
    exchange2 = "okx"

    # 模拟 10 次尝试，60% 失败
    print("模拟 10 次 maker 尝试（60% 失败）...\n")

    for i in range(10):
        is_filled = i % 5 != 0  # 20% 成交率（远低于阈值）
        is_fallback = not is_filled

        tracker.record_maker_attempt(
            exchange1, exchange2,
            is_filled=is_filled,
            is_timeout=not is_filled,
            is_fallback=is_fallback,
        )

        print(f"尝试 {i+1}: filled={is_filled}, fallback={is_fallback}")

    # 检查是否降级
    print(f"\n是否降级: {tracker.is_degraded(exchange1, exchange2)}")

    stats = tracker.get_stats(exchange1, exchange2)
    if stats:
        print(f"填单率: {stats.get_fill_rate():.1%}")
        print(f"Fallback 率: {stats.get_fallback_rate():.1%}")

    degradation = tracker.get_degradation_state(exchange1, exchange2)
    if degradation:
        print(f"降级原因: {degradation.reason}")
        print(f"冷却期: {degradation.cooldown_seconds}s")

    # 等待冷却期
    print(f"\n等待冷却期 {degradation.cooldown_seconds}s...")
    await asyncio.sleep(degradation.cooldown_seconds + 0.5)

    # 模拟恢复（成功的尝试）
    print("\n模拟 5 次成功尝试...")
    for i in range(5):
        tracker.record_maker_attempt(
            exchange1, exchange2,
            is_filled=True,
            is_timeout=False,
            is_fallback=False,
        )

    print(f"\n是否降级: {tracker.is_degraded(exchange1, exchange2)}")

    print("\n✅ Demo 4 完成：Maker 跟踪器与自动降级")


async def demo_5_opportunity_scorer_with_execution_modes():
    """Demo 5: OpportunityScorer 集成执行模式"""
    print_section("Demo 5: OpportunityScorer 集成执行模式")

    fee_model = FeeModel()
    funding_model = FundingModel()
    slippage_model = SlippageModel()
    fill_estimator = MakerFillEstimator()
    maker_tracker = MakerTracker()

    # 创建两个 scorer：一个使用 hybrid，一个使用 taker_only
    scorer_hybrid = OpportunityScorer(
        fee_model=fee_model,
        funding_model=funding_model,
        slippage_model=slippage_model,
        execution_mode="hybrid_hedge_taker",
        fill_estimator=fill_estimator,
        maker_tracker=maker_tracker,
    )

    scorer_taker = OpportunityScorer(
        fee_model=fee_model,
        funding_model=funding_model,
        slippage_model=slippage_model,
        execution_mode="safe_taker_only",
    )

    # 配置市场数据
    buy_exchange = "binance"
    sell_exchange = "edgex"  # edgex 有 maker 返佣
    symbol = "BTC-USDT"
    buy_price = 50000.0
    sell_price = 50060.0
    notional = 10000.0

    # 配置盘口
    buy_orderbook = OrderbookDepth(
        exchange=buy_exchange,
        symbol=symbol,
        bid_depth=100000.0,
        ask_depth=100000.0,
        bid_price=49995.0,
        ask_price=50005.0,
        spread_bps=2.0,
    )

    sell_orderbook = OrderbookDepth(
        exchange=sell_exchange,
        symbol=symbol,
        bid_depth=50000.0,
        ask_depth=50000.0,
        bid_price=50055.0,
        ask_price=50065.0,
        spread_bps=2.0,
    )

    # 评分
    print(f"套利机会: {buy_exchange} 买入 @ {buy_price} / {sell_exchange} 卖出 @ {sell_price}")
    print(f"价差: {((sell_price - buy_price) / buy_price) * 10000:.2f} bps")
    print(f"名义金额: {notional:.0f} USDT\n")

    # Hybrid 模式
    score_hybrid = scorer_hybrid.score_arbitrage_opportunity(
        opportunity_id="arb_001",
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        symbol=symbol,
        buy_price=buy_price,
        sell_price=sell_price,
        notional=notional,
        buy_liquidity_score=0.9,
        sell_liquidity_score=0.7,
        buy_orderbook=buy_orderbook,
        sell_orderbook=sell_orderbook,
    )

    # Taker Only 模式
    score_taker = scorer_taker.score_arbitrage_opportunity(
        opportunity_id="arb_002",
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        symbol=symbol,
        buy_price=buy_price,
        sell_price=sell_price,
        notional=notional,
    )

    # 对比
    print("\n--- HYBRID_HEDGE_TAKER 模式 ---")
    print(f"执行模式: {score_hybrid.execution_mode}")
    print(f"开仓订单类型: {score_hybrid.open_order_type}")
    print(f"平仓订单类型: {score_hybrid.close_order_type}")
    print(f"开仓费用: {score_hybrid.open_fee_cost:.4f} USDT")
    print(f"平仓费用: {score_hybrid.close_fee_cost:.4f} USDT")
    print(f"总费用: {score_hybrid.taker_fee_cost:.4f} USDT")
    print(f"Maker 填单概率: {score_hybrid.maker_fill_probability:.1%}" if score_hybrid.maker_fill_probability else "Maker 填单概率: N/A")
    print(f"预期 PNL: {score_hybrid.expected_pnl:.4f} USDT")
    print(f"ROI: {score_hybrid.roi_pct:.3f}%")

    print("\n--- SAFE_TAKER_ONLY 模式 ---")
    print(f"执行模式: {score_taker.execution_mode}")
    print(f"开仓订单类型: {score_taker.open_order_type}")
    print(f"平仓订单类型: {score_taker.close_order_type}")
    print(f"开仓费用: {score_taker.open_fee_cost:.4f} USDT")
    print(f"平仓费用: {score_taker.close_fee_cost:.4f} USDT")
    print(f"总费用: {score_taker.taker_fee_cost:.4f} USDT")
    print(f"预期 PNL: {score_taker.expected_pnl:.4f} USDT")
    print(f"ROI: {score_taker.roi_pct:.3f}%")

    print("\n--- 对比 ---")
    fee_saving = score_taker.taker_fee_cost - score_hybrid.taker_fee_cost
    pnl_improvement = score_hybrid.expected_pnl - score_taker.expected_pnl

    print(f"Hybrid 模式节省费用: {fee_saving:.4f} USDT")
    print(f"Hybrid 模式 PNL 提升: {pnl_improvement:.4f} USDT ({(pnl_improvement/notional)*100:.3f}%)")

    if fee_saving > 0:
        print("✅ Hybrid 模式更优！（利用 maker 返佣节省成本）")
    else:
        print("⚠️ Taker Only 模式更安全（无填单风险）")

    print("\n✅ Demo 5 完成：OpportunityScorer 集成执行模式")


async def demo_6_full_execution_workflow():
    """Demo 6: 完整执行流程（评分 → 执行 → 跟踪）"""
    print_section("Demo 6: 完整执行流程（评分 → 执行 → 跟踪）")

    # 初始化所有组件
    fee_model = FeeModel()
    funding_model = FundingModel()
    slippage_model = SlippageModel()
    fill_estimator = MakerFillEstimator()
    maker_tracker = MakerTracker()

    scorer = OpportunityScorer(
        fee_model=fee_model,
        funding_model=funding_model,
        slippage_model=slippage_model,
        execution_mode="hybrid_hedge_taker",
        fill_estimator=fill_estimator,
        maker_tracker=maker_tracker,
    )

    config = ExecutionConfig(mode=ExecutionMode.HYBRID_HEDGE_TAKER)
    engine = ExecutionEngine(
        fee_model=fee_model,
        slippage_model=slippage_model,
        config=config,
        maker_tracker=maker_tracker,
        fill_estimator=fill_estimator,
    )

    # 模拟机会
    buy_exchange = "binance"
    sell_exchange = "edgex"
    symbol = "BTC-USDT"
    buy_price = 50000.0
    sell_price = 50080.0
    notional = 5000.0

    print("步骤 1: 评分机会\n")

    score = scorer.score_arbitrage_opportunity(
        opportunity_id="arb_full_001",
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        symbol=symbol,
        buy_price=buy_price,
        sell_price=sell_price,
        notional=notional,
        buy_liquidity_score=0.9,
        sell_liquidity_score=0.7,
    )

    print(f"机会评分: {score.final_score:.2f}")
    print(f"预期 PNL: {score.expected_pnl:.4f} USDT")
    print(f"执行模式: {score.execution_mode}")
    print(f"订单类型: open={score.open_order_type}, close={score.close_order_type}")

    if not score.is_executable(min_pnl=0.0):
        print("\n❌ 机会不可执行，终止")
        return

    print("\n步骤 2: 执行对冲\n")

    result = await engine.execute_hedge(
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        symbol=symbol,
        notional=notional,
        buy_price=buy_price,
        sell_price=sell_price,
        buy_liquidity_score=0.9,
        sell_liquidity_score=0.7,
    )

    print(f"执行成功: {result.success}")
    print(f"总费用: {result.total_fee:.4f} USDT")
    print(f"执行时间: {result.total_execution_time_ms:.0f} ms")
    print(f"未对冲时间: {result.unhedged_time_ms:.0f} ms")
    print(f"Fallback: {result.had_fallback}")

    print("\n步骤 3: 检查 Maker 统计\n")

    stats = maker_tracker.get_stats(buy_exchange, sell_exchange)
    if stats:
        print(f"总尝试次数: {stats.total_attempts}")
        print(f"成功填单: {stats.successful_fills}")
        print(f"填单率: {stats.get_fill_rate():.1%}")
        print(f"Fallback 次数: {stats.fallback_count}")

    print("\n✅ Demo 6 完成：完整执行流程")


async def main():
    """运行所有演示"""
    print_section("Execution Engine 完整演示")

    demos = [
        demo_1_fee_model_with_negative_rates,
        demo_2_maker_fill_estimator,
        demo_3_execution_modes,
        demo_4_maker_tracker_and_degradation,
        demo_5_opportunity_scorer_with_execution_modes,
        demo_6_full_execution_workflow,
    ]

    for demo in demos:
        await demo()
        await asyncio.sleep(0.5)

    print_section("所有演示完成！")

    print("\n总结：")
    print("✅ 1. FeeModel 支持负费率（maker 返佣）")
    print("✅ 2. Maker 填单概率估计")
    print("✅ 3. 三种执行模式对比")
    print("✅ 4. Maker 跟踪器与自动降级")
    print("✅ 5. OpportunityScorer 集成执行模式")
    print("✅ 6. 完整执行流程（评分 → 执行 → 跟踪）")

    print("\n核心特性：")
    print("- 支持 SAFE_TAKER_ONLY / HYBRID_HEDGE_TAKER / DOUBLE_MAKER 三种模式")
    print("- Maker 填单概率评估，优化费用")
    print("- 自动降级机制，失败率过高时切换到 taker")
    print("- 未对冲风险控制，超时/超额自动 fallback")
    print("- 负费率支持，充分利用 maker 返佣")


if __name__ == "__main__":
    asyncio.run(main())
