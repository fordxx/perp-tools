"""
调度器与资金系统联动演示

展示 HedgeScheduler 如何与 SimpleCapitalOrchestrator 协同工作：
1. 根据任务类型自动选择资金池（S1/S2/S3）
2. 刷量任务使用 S1_wash 池
3. 套利任务使用 S2_arb 池
4. 任务完成后自动释放资金
5. 资金不足时拒绝任务
"""

import logging
import time
from pprint import pprint

from perpbot.capital.simple_capital_orchestrator import SimpleCapitalOrchestrator
from perpbot.hedge_scheduler import (
    HedgeJob,
    HedgeScheduler,
    JobSource,
    RiskMode,
    SchedulerConfig,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def print_separator(title=""):
    """打印分隔线"""
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def mock_wash_executor(job: HedgeJob):
    """模拟刷量执行器"""
    print(f"  [执行器] 刷量任务 {job.job_id[:8]} - {job.symbol} 正在执行...")
    time.sleep(0.05)
    # 注意：实际应该异步执行，完成后调用 scheduler.on_job_finished


def mock_arb_executor(job: HedgeJob):
    """模拟套利执行器"""
    print(f"  [执行器] 套利任务 {job.job_id[:8]} - {job.symbol} 正在执行...")
    time.sleep(0.05)


def create_wash_jobs():
    """创建刷量任务"""
    jobs = []

    jobs.append(HedgeJob(
        symbol="BTC/USDT",
        exchanges={"binance"},
        notional=3000.0,
        expected_edge_bps=0.0,
        expected_pnl=0.0,
        risk_score=20.0,
        latency_score=90.0,
        vol_score=95.0,  # 高成交量贡献
        funding_score=70.0,
        liquidity_score=90.0,
        source=JobSource.HEDGE_VOLUME,
        metadata={"note": "BTC 刷量任务"}
    ))

    jobs.append(HedgeJob(
        symbol="ETH/USDT",
        exchanges={"okx"},
        notional=2500.0,
        expected_edge_bps=0.0,
        expected_pnl=0.0,
        risk_score=25.0,
        latency_score=85.0,
        vol_score=90.0,
        funding_score=75.0,
        liquidity_score=85.0,
        source=JobSource.HEDGE_VOLUME,
        metadata={"note": "ETH 刷量任务"}
    ))

    return jobs


def create_arb_jobs():
    """创建套利任务"""
    jobs = []

    jobs.append(HedgeJob(
        symbol="BTC/USDT",
        exchanges={"binance", "okx"},
        notional=1500.0,
        expected_edge_bps=25.0,
        expected_pnl=3.75,
        risk_score=30.0,
        latency_score=80.0,
        vol_score=60.0,
        funding_score=65.0,
        liquidity_score=90.0,
        source=JobSource.ARBITRAGE,
        metadata={"note": "BTC 跨所套利"}
    ))

    jobs.append(HedgeJob(
        symbol="ETH/USDT",
        exchanges={"edgex", "paradex"},
        notional=1200.0,
        expected_edge_bps=18.0,
        expected_pnl=2.16,
        risk_score=35.0,
        latency_score=75.0,
        vol_score=55.0,
        funding_score=60.0,
        liquidity_score=80.0,
        source=JobSource.ARBITRAGE,
        metadata={"note": "ETH 跨所套利"}
    ))

    return jobs


def demo_basic_integration():
    """演示基础集成"""
    print_separator("演示 1: 调度器与资金系统基础集成")

    # 创建资金调度器
    capital = SimpleCapitalOrchestrator(
        wu_size=10_000.0,
        s1_wash_pct=0.70,   # S1: 7000
        s2_arb_pct=0.20,    # S2: 2000
        s3_reserve_pct=0.10 # S3: 1000
    )

    # 初始化交易所
    for ex in ["binance", "okx", "edgex", "paradex"]:
        capital._ensure_exchange(ex)

    print("\n[初始资金状态]")
    snapshot = capital.get_snapshot()
    for ex in ["binance", "okx"]:
        print(f"\n{ex}:")
        print(f"  S1_wash: ${snapshot[ex]['pools']['S1_wash']['available']:,.2f} 可用")
        print(f"  S2_arb:  ${snapshot[ex]['pools']['S2_arb']['available']:,.2f} 可用")

    # 创建调度器
    config = SchedulerConfig(
        max_global_concurrent_jobs=4,
        max_concurrent_per_exchange=2,
        risk_mode=RiskMode.VOLUME_FOCUSED,  # 刷量优先模式
        min_score_threshold=30.0,
    )
    scheduler = HedgeScheduler(capital_orchestrator=capital, config=config)

    # 注册执行器
    scheduler.register_executor(JobSource.HEDGE_VOLUME, mock_wash_executor)
    scheduler.register_executor(JobSource.ARBITRAGE, mock_arb_executor)

    # 提交任务
    print_separator("提交任务到调度器")

    wash_jobs = create_wash_jobs()
    arb_jobs = create_arb_jobs()

    print("\n[刷量任务] (使用 S1_wash 池):")
    for job in wash_jobs:
        scheduler.submit_job(job)
        print(f"  • {job.symbol} @ {list(job.exchanges)[0]}: ${job.notional:,.2f}")

    print("\n[套利任务] (使用 S2_arb 池):")
    for job in arb_jobs:
        scheduler.submit_job(job)
        print(f"  • {job.symbol} @ {'/'.join(sorted(job.exchanges))}: ${job.notional:,.2f}")

    # 执行调度
    print_separator("执行第 1 轮调度")

    result = scheduler.tick()
    print(f"\n调度结果:")
    print(f"  成功调度: {result['scheduled']}")
    print(f"  拒绝: {result['rejected']}")
    print(f"  待调度: {result['pending']}")
    print(f"  运行中: {result['running']}")

    # 查看资金池状态
    print("\n[资金池状态] (调度后):")
    snapshot = capital.get_snapshot()
    for ex in ["binance", "okx"]:
        print(f"\n{ex}:")
        s1 = snapshot[ex]['pools']['S1_wash']
        s2 = snapshot[ex]['pools']['S2_arb']
        print(f"  S1_wash: ${s1['allocated']:,.2f} 占用 / ${s1['available']:,.2f} 可用 ({s1['utilization_pct']:.1f}%)")
        print(f"  S2_arb:  ${s2['allocated']:,.2f} 占用 / ${s2['available']:,.2f} 可用 ({s2['utilization_pct']:.1f}%)")

    # 模拟任务完成
    print_separator("模拟任务完成并释放资金")

    completed = list(scheduler.state.running_jobs.values())[:2]
    for job in completed:
        print(f"\n任务 {job.job_id[:8]} ({job.source.value}) 完成")
        scheduler.on_job_finished(job.job_id, {
            "success": True,
            "pnl": job.expected_pnl * 0.9,
            "volume": job.notional * 2,
        })

    # 查看资金池状态
    print("\n[资金池状态] (任务完成后):")
    snapshot = capital.get_snapshot()
    for ex in ["binance", "okx"]:
        print(f"\n{ex}:")
        s1 = snapshot[ex]['pools']['S1_wash']
        s2 = snapshot[ex]['pools']['S2_arb']
        print(f"  S1_wash: ${s1['allocated']:,.2f} 占用 / ${s1['available']:,.2f} 可用")
        print(f"  S2_arb:  ${s2['allocated']:,.2f} 占用 / ${s2['available']:,.2f} 可用")


def demo_capital_constraint():
    """演示资金约束"""
    print_separator("演示 2: 资金不足时的任务拒绝")

    # 创建小额资金池
    capital = SimpleCapitalOrchestrator(
        wu_size=5_000.0,  # 只有 5000
        s1_wash_pct=0.70,  # S1: 3500
        s2_arb_pct=0.20,   # S2: 1000
        s3_reserve_pct=0.10
    )

    for ex in ["binance", "okx"]:
        capital._ensure_exchange(ex)

    config = SchedulerConfig(
        max_global_concurrent_jobs=10,
        risk_mode=RiskMode.BALANCED,
        min_score_threshold=20.0,
    )
    scheduler = HedgeScheduler(capital_orchestrator=capital, config=config)
    scheduler.register_executor(JobSource.HEDGE_VOLUME, mock_wash_executor)
    scheduler.register_executor(JobSource.ARBITRAGE, mock_arb_executor)

    print("\n[初始资金]: 每个交易所 S1=$3,500, S2=$1,000")

    # 提交大量任务（超过资金容量）
    print_separator("提交超额任务")

    jobs = [
        HedgeJob(
            symbol="BTC/USDT",
            exchanges={"binance"},
            notional=2000.0,
            vol_score=90.0,
            source=JobSource.HEDGE_VOLUME,
        ),
        HedgeJob(
            symbol="ETH/USDT",
            exchanges={"binance"},
            notional=2000.0,
            vol_score=85.0,
            source=JobSource.HEDGE_VOLUME,
        ),
        HedgeJob(
            symbol="SOL/USDT",
            exchanges={"binance"},
            notional=1500.0,  # 这个应该被拒绝（资金不足）
            vol_score=80.0,
            source=JobSource.HEDGE_VOLUME,
        ),
    ]

    for job in jobs:
        scheduler.submit_job(job)
        print(f"  提交: {job.symbol} ${job.notional:,.2f}")

    # 执行调度
    print_separator("执行调度")

    result = scheduler.tick()
    print(f"\n调度结果:")
    print(f"  成功: {result['scheduled']}")
    print(f"  拒绝: {result['rejected']}")
    if result['rejected_reasons']:
        print(f"  拒绝原因:")
        for reason, count in result['rejected_reasons'].items():
            print(f"    • {reason}: {count} 个任务")

    # 查看资金状态
    print("\n[资金池状态]:")
    snapshot = capital.get_snapshot()
    s1 = snapshot['binance']['pools']['S1_wash']
    print(f"  S1_wash: ${s1['allocated']:,.2f} 占用 / ${s1['available']:,.2f} 可用 / ${s1['pool_size']:,.2f} 总额")


def demo_safe_mode_integration():
    """演示安全模式集成"""
    print_separator("演示 3: 安全模式下的资金限制")

    capital = SimpleCapitalOrchestrator(
        wu_size=10_000.0,
        drawdown_limit_pct=0.05,
    )

    for ex in ["binance"]:
        capital._ensure_exchange(ex)

    config = SchedulerConfig(
        max_global_concurrent_jobs=5,
        risk_mode=RiskMode.BALANCED,
    )
    scheduler = HedgeScheduler(capital_orchestrator=capital, config=config)
    scheduler.register_executor(JobSource.HEDGE_VOLUME, mock_wash_executor)
    scheduler.register_executor(JobSource.ARBITRAGE, mock_arb_executor)

    # 正常模式下提交任务
    print("\n[正常模式] 提交任务:")
    jobs = [
        HedgeJob(symbol="BTC/USDT", exchanges={"binance"}, notional=2000.0, vol_score=90.0, source=JobSource.HEDGE_VOLUME),
        HedgeJob(symbol="ETH/USDT", exchanges={"binance"}, notional=1000.0, expected_edge_bps=20.0, source=JobSource.ARBITRAGE),
    ]

    for job in jobs:
        scheduler.submit_job(job)
        print(f"  • {job.symbol} ({job.source.value}): ${job.notional:,.2f}")

    result1 = scheduler.tick()
    print(f"\n调度结果: 成功 {result1['scheduled']}, 拒绝 {result1['rejected']}")

    # 触发安全模式
    print_separator("触发安全模式（回撤 6%）")
    capital.update_drawdown("binance", 0.06)

    # 完成之前的任务并释放资金
    for job in list(scheduler.state.running_jobs.values()):
        scheduler.on_job_finished(job.job_id, {"success": True, "pnl": 0.0, "volume": 0.0})

    # 安全模式下提交任务
    print("\n[安全模式] 提交任务:")
    jobs2 = [
        HedgeJob(symbol="BTC/USDT", exchanges={"binance"}, notional=2000.0, vol_score=90.0, source=JobSource.HEDGE_VOLUME),
        HedgeJob(symbol="ETH/USDT", exchanges={"binance"}, notional=1000.0, expected_edge_bps=20.0, source=JobSource.ARBITRAGE),
    ]

    for job in jobs2:
        scheduler.submit_job(job)
        print(f"  • {job.symbol} ({job.source.value}): ${job.notional:,.2f}")

    result2 = scheduler.tick()
    print(f"\n调度结果: 成功 {result2['scheduled']}, 拒绝 {result2['rejected']}")
    if result2['rejected_reasons']:
        print(f"拒绝原因:")
        for reason, count in result2['rejected_reasons'].items():
            print(f"  • {reason}: {count} 个")

    print("\n说明: 安全模式下 S2_arb 被禁用，只有刷量任务（S1_wash）能通过")


def demo_scheduler_state():
    """演示调度器状态监控"""
    print_separator("演示 4: 调度器状态监控")

    capital = SimpleCapitalOrchestrator(wu_size=10_000.0)
    for ex in ["binance", "okx", "edgex"]:
        capital._ensure_exchange(ex)

    config = SchedulerConfig(max_global_concurrent_jobs=5, risk_mode=RiskMode.VOLUME_FOCUSED)
    scheduler = HedgeScheduler(capital_orchestrator=capital, config=config)
    scheduler.register_executor(JobSource.HEDGE_VOLUME, mock_wash_executor)
    scheduler.register_executor(JobSource.ARBITRAGE, mock_arb_executor)

    # 提交多个任务
    jobs = create_wash_jobs() + create_arb_jobs()
    for job in jobs:
        scheduler.submit_job(job)

    # 执行调度
    scheduler.tick()

    # 获取调度器状态
    print("\n[调度器状态]:")
    state = scheduler.get_scheduler_state()
    pprint(state)

    # 获取资金快照
    print("\n[资金池快照]:")
    capital_state = capital.get_snapshot()
    for ex in ["binance", "okx"]:
        if ex in capital_state:
            print(f"\n{ex}:")
            for pool_name, pool_data in capital_state[ex]['pools'].items():
                print(f"  {pool_name}: {pool_data['utilization_pct']:.1f}% 占用")


def run_all_demos():
    """运行所有演示"""
    print_separator("调度器与资金系统联动演示")
    print("""
本演示展示 HedgeScheduler 如何与 SimpleCapitalOrchestrator 协同工作：

- 刷量任务 (HEDGE_VOLUME)  → 自动使用 S1_wash 池
- 套利任务 (ARBITRAGE)     → 自动使用 S2_arb 池
- 做市任务 (MARKET_MAKING) → 自动使用 S2_arb 池

所有日志都明确标注使用的资金池（S1/S2/S3），禁止访问 L1-L5！
""")

    demo_basic_integration()
    demo_capital_constraint()
    demo_safe_mode_integration()
    demo_scheduler_state()

    print_separator("所有演示完成")
    print("""
✅ 联动演示总结：

1. 基础集成：调度器根据任务类型自动选择资金池
2. 资金约束：资金不足时自动拒绝任务并记录原因
3. 安全模式：回撤超限时限制资金池访问
4. 状态监控：实时查看调度器和资金池状态

关键日志：
- [调度器] 任务 xxx 使用 S1_wash 池
- [调度器] 任务 xxx 使用 S2_arb 池
- [调度器] 任务 xxx 释放资金

整个流程完全基于三层抽象（S1/S2/S3），不暴露 L 层级概念。
""")


if __name__ == "__main__":
    run_all_demos()
