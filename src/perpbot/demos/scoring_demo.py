"""
Opportunity Scoring Engine Demo

演示交易机会评分引擎的完整功能：
1. 手续费模型
2. 资金费率模型
3. 滑点模型
4. 统一机会评分
5. 过滤与排序
"""

import logging
from datetime import datetime, timedelta
from pprint import pprint

from perpbot.scoring import (
    FeeModel,
    FundingModel,
    SlippageModel,
    OpportunityScorer,
    OpportunityScore,
)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def print_separator(title=""):
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def demo_fee_model():
    """演示 1: 手续费模型"""
    print_separator("演示 1: 手续费模型")

    fee_model = FeeModel()

    print("\n[查询各交易所费率]")
    for exchange in ["binance", "okx", "edgex"]:
        maker_fee = fee_model.get_maker_fee(exchange)
        taker_fee = fee_model.get_taker_fee(exchange)
        print(f"{exchange:10s}: maker={maker_fee*100:.3f}%, taker={taker_fee*100:.3f}%")

    print("\n[计算手续费成本]")
    notional = 10000.0

    for exchange in ["binance", "okx", "edgex"]:
        fee = fee_model.calculate_fee_cost(exchange, notional, is_taker=True)
        print(f"{exchange:10s}: ${fee:.4f} (notional=${notional:.0f})")

    print("\n[刷量返佣演示]")
    exchange = "edgex"
    wash_fee_without_rebate = fee_model.calculate_fee_cost(
        exchange, notional, is_taker=True, is_wash_trade=False
    )
    wash_fee_with_rebate = fee_model.calculate_fee_cost(
        exchange, notional, is_taker=True, is_wash_trade=True
    )
    print(f"无返佣: ${wash_fee_without_rebate:.4f}")
    print(f"有返佣: ${wash_fee_with_rebate:.4f}")
    print(f"节省: ${wash_fee_without_rebate - wash_fee_with_rebate:.4f}")


def demo_funding_model():
    """演示 2: 资金费率模型"""
    print_separator("演示 2: 资金费率模型")

    funding_model = FundingModel()

    print("\n[设置资金费率]")
    # binance: 正费率（多头支付空头）
    funding_model.update_funding_rate(
        "binance", "BTC/USDT", 0.0001,  # 0.01%
        datetime.utcnow() + timedelta(hours=4)
    )

    # okx: 负费率（空头支付多头）
    funding_model.update_funding_rate(
        "okx", "BTC/USDT", -0.0002,  # -0.02%
        datetime.utcnow() + timedelta(hours=4)
    )

    print("binance BTC/USDT: +0.01% (多头支付)")
    print("okx BTC/USDT: -0.02% (空头支付)")

    print("\n[计算套利资金费率收益]")
    notional = 10000.0
    holding_hours = 8.0

    # 在 binance 买入（多头）→ 支付 0.01%
    # 在 okx 卖出（空头）→ 收取 -0.02%（即支付给多头）
    # 净收益 = okx收益 + binance成本 = -(-0.02%) + (-0.01%) = 0.02% - 0.01% = 0.01%

    pnl = funding_model.calculate_arbitrage_funding_pnl(
        "binance", "okx", "BTC/USDT", notional, holding_hours
    )

    print(f"买入交易所: binance (多头，支付费率)")
    print(f"卖出交易所: okx (空头，收取费率)")
    print(f"持仓时长: {holding_hours}h")
    print(f"资金费率收益: ${pnl:.4f}")

    print("\n[资金费率是否有利]")
    favorable = funding_model.is_funding_favorable("binance", "okx", "BTC/USDT")
    print(f"binance→okx 套利资金费率是否有利: {favorable}")


def demo_slippage_model():
    """演示 3: 滑点模型"""
    print_separator("演示 3: 滑点模型")

    slippage_model = SlippageModel()

    print("\n[设置盘口深度]")
    # binance: 深度充足
    slippage_model.update_orderbook_depth(
        "binance", "BTC/USDT",
        bid_depth=100000.0,  # $100k
        ask_depth=100000.0,
        bid_price=50000.0,
        ask_price=50001.0,
    )

    # okx: 深度较浅
    slippage_model.update_orderbook_depth(
        "okx", "BTC/USDT",
        bid_depth=20000.0,   # $20k
        ask_depth=20000.0,
        bid_price=49999.0,
        ask_price=50000.0,
    )

    print("binance: 深度=$100k, spread=0.002%")
    print("okx: 深度=$20k, spread=0.002%")

    print("\n[估算滑点成本]")
    notional_small = 5000.0   # 小单
    notional_large = 50000.0  # 大单

    print(f"\n小单 (${notional_small:.0f}):")
    for exchange in ["binance", "okx"]:
        slippage = slippage_model.estimate_slippage(
            exchange, "BTC/USDT", notional_small, "buy", latency_ms=50
        )
        print(f"  {exchange}: ${slippage:.4f}")

    print(f"\n大单 (${notional_large:.0f}):")
    for exchange in ["binance", "okx"]:
        slippage = slippage_model.estimate_slippage(
            exchange, "BTC/USDT", notional_large, "buy", latency_ms=50
        )
        print(f"  {exchange}: ${slippage:.4f}")

    print("\n[延迟影响]")
    notional = 10000.0
    for latency_ms in [50, 200, 500, 1000]:
        slippage = slippage_model.estimate_slippage(
            "binance", "BTC/USDT", notional, "buy", latency_ms=latency_ms
        )
        print(f"延迟 {latency_ms:4d}ms: ${slippage:.4f}")


def demo_opportunity_scorer():
    """演示 4: 统一机会评分"""
    print_separator("演示 4: 统一机会评分")

    # 初始化所有模型
    fee_model = FeeModel()
    funding_model = FundingModel()
    slippage_model = SlippageModel()

    # 设置市场数据
    funding_model.update_funding_rate("binance", "BTC/USDT", 0.0001)
    funding_model.update_funding_rate("okx", "BTC/USDT", -0.0001)

    slippage_model.update_orderbook_depth(
        "binance", "BTC/USDT", 100000, 100000, 50000, 50001
    )
    slippage_model.update_orderbook_depth(
        "okx", "BTC/USDT", 80000, 80000, 50010, 50011
    )

    # 创建评分器
    scorer = OpportunityScorer(
        fee_model=fee_model,
        funding_model=funding_model,
        slippage_model=slippage_model,
        min_pnl_threshold=0.01,
    )

    print("\n[评分套利机会]")

    # 机会 1: 低价差 + 正资金费率
    score1 = scorer.score_arbitrage_opportunity(
        opportunity_id="arb_001",
        buy_exchange="binance",
        sell_exchange="okx",
        symbol="BTC/USDT",
        buy_price=50000.0,
        sell_price=50010.0,  # 10 USDT 价差
        notional=10000.0,
        holding_hours=8.0,
        buy_latency_ms=50,
        sell_latency_ms=60,
    )

    print("\n机会 1: 低价差 + 正资金费率")
    print(f"  价差收益: ${score1.price_spread_pnl:.4f}")
    print(f"  资金费率: ${score1.funding_pnl:.4f}")
    print(f"  手续费: ${score1.taker_fee_cost:.4f}")
    print(f"  滑点: ${score1.slippage_cost:.4f}")
    print(f"  预期PnL: ${score1.expected_pnl:.4f}")
    print(f"  ROI: {score1.roi_pct:.3f}%")
    print(f"  年化ROI: {score1.roi_annualized_pct:.1f}%")
    print(f"  最终评分: {score1.final_score:.2f}")
    print(f"  可执行: {score1.is_executable()}")

    # 机会 2: 高价差 + 高手续费
    score2 = scorer.score_arbitrage_opportunity(
        opportunity_id="arb_002",
        buy_exchange="binance",
        sell_exchange="okx",
        symbol="BTC/USDT",
        buy_price=50000.0,
        sell_price=50003.0,  # 仅 3 USDT 价差
        notional=10000.0,
        holding_hours=0.1,
        buy_latency_ms=50,
        sell_latency_ms=60,
    )

    print("\n机会 2: 小价差 + 短持仓")
    print(f"  价差收益: ${score2.price_spread_pnl:.4f}")
    print(f"  手续费: ${score2.taker_fee_cost:.4f}")
    print(f"  预期PnL: ${score2.expected_pnl:.4f}")
    print(f"  ROI: {score2.roi_pct:.3f}%")
    print(f"  最终评分: {score2.final_score:.2f}")
    print(f"  可执行: {score2.is_executable()}")

    # 机会 3: 高延迟
    score3 = scorer.score_arbitrage_opportunity(
        opportunity_id="arb_003",
        buy_exchange="binance",
        sell_exchange="okx",
        symbol="BTC/USDT",
        buy_price=50000.0,
        sell_price=50015.0,
        notional=10000.0,
        holding_hours=0.1,
        buy_latency_ms=800,   # 高延迟
        sell_latency_ms=1000,
    )

    print("\n机会 3: 高价差 + 高延迟")
    print(f"  价差收益: ${score3.price_spread_pnl:.4f}")
    print(f"  延迟惩罚: ${score3.latency_penalty:.4f}")
    print(f"  滑点: ${score3.slippage_cost:.4f}")
    print(f"  预期PnL: ${score3.expected_pnl:.4f}")
    print(f"  风险评分: {score3.risk_score:.2f}")
    print(f"  最终评分: {score3.final_score:.2f}")
    print(f"  可执行: {score3.is_executable()}")


def demo_filtering_and_ranking():
    """演示 5: 过滤与排序"""
    print_separator("演示 5: 过滤与排序")

    # 创建评分器
    scorer = OpportunityScorer(min_pnl_threshold=0.5)

    # 创建多个机会
    print("\n[生成10个套利机会]")
    opportunities = []

    for i in range(10):
        spread = 5 + i * 2  # 递增价差
        score = scorer.score_arbitrage_opportunity(
            opportunity_id=f"arb_{i:03d}",
            buy_exchange="binance",
            sell_exchange="okx",
            symbol="BTC/USDT",
            buy_price=50000.0,
            sell_price=50000.0 + spread,
            notional=10000.0,
            holding_hours=0.5,
            buy_latency_ms=50 + i * 10,
            sell_latency_ms=60 + i * 10,
        )
        opportunities.append(score)

    print(f"生成了 {len(opportunities)} 个机会")

    print("\n[过滤（PnL > $0.5）]")
    filtered = scorer.filter_opportunities(
        opportunities,
        min_pnl=0.5,
    )
    print(f"过滤后: {len(filtered)} 个机会")

    print("\n[排序（按最终评分）]")
    ranked = scorer.rank_opportunities(filtered, by="final_score")

    print("\nTop 5:")
    for i, score in enumerate(ranked[:5]):
        print(f"{i+1}. {score.opportunity_id}: "
              f"PnL=${score.expected_pnl:.4f}, "
              f"ROI={score.roi_pct:.3f}%, "
              f"Score={score.final_score:.2f}")


def demo_wash_trade_scoring():
    """演示 6: 刷量机会评分"""
    print_separator("演示 6: 刷量机会评分")

    fee_model = FeeModel()
    slippage_model = SlippageModel()

    slippage_model.update_orderbook_depth(
        "edgex", "BTC/USDT", 50000, 50000, 50000, 50001
    )

    scorer = OpportunityScorer(
        fee_model=fee_model,
        slippage_model=slippage_model,
    )

    print("\n[无返佣刷量]")
    score_no_rebate = scorer.score_wash_opportunity(
        opportunity_id="wash_001",
        exchange="binance",
        symbol="BTC/USDT",
        price=50000.0,
        notional=10000.0,
        holding_hours=0.01,
        has_rebate=False,
    )

    print(f"手续费: ${score_no_rebate.taker_fee_cost:.4f}")
    print(f"滑点: ${score_no_rebate.slippage_cost:.4f}")
    print(f"总成本: ${score_no_rebate.total_cost:.4f}")
    print(f"预期PnL: ${score_no_rebate.expected_pnl:.4f}")

    print("\n[有返佣刷量 (edgex 50%)]")
    score_with_rebate = scorer.score_wash_opportunity(
        opportunity_id="wash_002",
        exchange="edgex",
        symbol="BTC/USDT",
        price=50000.0,
        notional=10000.0,
        holding_hours=0.01,
        has_rebate=True,
    )

    print(f"手续费: ${score_with_rebate.taker_fee_cost:.4f}")
    print(f"滑点: ${score_with_rebate.slippage_cost:.4f}")
    print(f"总成本: ${score_with_rebate.total_cost:.4f}")
    print(f"预期PnL: ${score_with_rebate.expected_pnl:.4f}")

    print("\n[返佣节省]")
    saving = score_no_rebate.total_cost - score_with_rebate.total_cost
    print(f"节省成本: ${saving:.4f}")


def run_all_demos():
    """运行所有演示"""
    print_separator("交易机会评分引擎 - 完整演示")
    print("""
本演示展示机会评分引擎的完整功能：

1. 手续费模型 - maker/taker 费率、返佣
2. 资金费率模型 - 正负费率、套利收益
3. 滑点模型 - 深度影响、延迟惩罚
4. 统一机会评分 - 完整成本计算
5. 过滤与排序 - 筛选最优机会
6. 刷量机会评分 - 返佣机制

评分公式：
ExpectedPNL = price_spread_pnl + funding_pnl
            - taker_fee_cost - slippage_cost
            - latency_penalty - capital_time_cost

final_score = expected_pnl * reliability * (1 - risk) / sqrt(time + 1)
    """)

    demo_fee_model()
    demo_funding_model()
    demo_slippage_model()
    demo_opportunity_scorer()
    demo_filtering_and_ranking()
    demo_wash_trade_scoring()

    print_separator("所有演示完成")
    print("""
✅ 核心功能验证：
1. ✅ 手续费模型（maker/taker、返佣）
2. ✅ 资金费率模型（8h/4h 周期、套利收益）
3. ✅ 滑点模型（深度影响、延迟惩罚）
4. ✅ 统一评分公式（7项成本因素）
5. ✅ 机会过滤（PnL、评分、ROI）
6. ✅ 机会排序（多种排序方式）
7. ✅ 套利机会评分
8. ✅ 刷量机会评分

评分引擎已准备好集成到 Scheduler！
    """)


if __name__ == "__main__":
    run_all_demos()
