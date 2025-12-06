"""
对冲任务调度器演示脚本

展示如何使用 HedgeScheduler 进行多任务调度：
1. 创建调度器实例
2. 提交不同类型的对冲任务
3. 运行多轮调度 tick
4. 查看调度结果和状态
"""

import time
from datetime import datetime
from pprint import pprint

from perpbot.hedge_scheduler import (
    HedgeJob,
    HedgeScheduler,
    JobSource,
    JobStatus,
    RiskMode,
    SchedulerConfig,
)


def mock_hedge_executor(job: HedgeJob):
    """模拟对冲刷量执行器"""
    print(f"  [Executor] Executing HEDGE_VOLUME job {job.job_id[:8]} - {job.symbol}")
    time.sleep(0.1)  # 模拟执行时间
    # 实际场景应该是异步执行，完成后调用 scheduler.on_job_finished


def mock_arbitrage_executor(job: HedgeJob):
    """模拟套利执行器"""
    print(f"  [Executor] Executing ARBITRAGE job {job.job_id[:8]} - {job.symbol}")
    time.sleep(0.1)
    # 实际场景应该是异步执行


def mock_market_making_executor(job: HedgeJob):
    """模拟做市执行器"""
    print(f"  [Executor] Executing MARKET_MAKING job {job.job_id[:8]} - {job.symbol}")
    time.sleep(0.1)


def create_sample_jobs():
    """创建一批示例任务"""
    jobs = []

    # 1. 高收益套利任务 - 应该被优先选择
    jobs.append(HedgeJob(
        symbol="BTC/USDT",
        exchanges={"binance", "okx"},
        notional=5000.0,
        expected_edge_bps=25.0,  # 25 bps = 0.25% 收益
        expected_pnl=12.5,
        risk_score=30.0,  # 低风险
        latency_score=85.0,
        vol_score=60.0,
        funding_score=70.0,
        liquidity_score=90.0,
        source=JobSource.ARBITRAGE,
        metadata={"strategy": "cross_exchange_arb", "confidence": 0.95}
    ))

    # 2. 刷量对冲任务 - 成交量贡献高
    jobs.append(HedgeJob(
        symbol="ETH/USDT",
        exchanges={"edgex", "paradex"},
        notional=8000.0,
        expected_edge_bps=5.0,  # 较低收益
        expected_pnl=4.0,
        risk_score=25.0,
        latency_score=90.0,
        vol_score=95.0,  # 高成交量贡献
        funding_score=80.0,
        liquidity_score=85.0,
        source=JobSource.HEDGE_VOLUME,
        metadata={"target_volume": 100000}
    ))

    # 3. 中等收益套利
    jobs.append(HedgeJob(
        symbol="BTC/USDT",
        exchanges={"backpack", "aster"},
        notional=3000.0,
        expected_edge_bps=15.0,
        expected_pnl=4.5,
        risk_score=40.0,
        latency_score=70.0,
        vol_score=50.0,
        funding_score=60.0,
        liquidity_score=75.0,
        source=JobSource.ARBITRAGE,
    ))

    # 4. 做市任务
    jobs.append(HedgeJob(
        symbol="ETH/USDT",
        exchanges={"grvt"},
        notional=2000.0,
        expected_edge_bps=10.0,
        expected_pnl=2.0,
        risk_score=50.0,
        latency_score=95.0,
        vol_score=70.0,
        funding_score=50.0,
        liquidity_score=80.0,
        source=JobSource.MARKET_MAKING,
    ))

    # 5. 高风险高收益任务
    jobs.append(HedgeJob(
        symbol="SOL/USDT",
        exchanges={"extended", "paradex"},
        notional=10000.0,
        expected_edge_bps=50.0,  # 极高收益
        expected_pnl=50.0,
        risk_score=80.0,  # 高风险
        latency_score=60.0,
        vol_score=40.0,
        funding_score=30.0,
        liquidity_score=50.0,
        source=JobSource.ARBITRAGE,
        metadata={"warning": "volatile_market"}
    ))

    # 6. 低评分任务 - 应该被过滤
    jobs.append(HedgeJob(
        symbol="DOGE/USDT",
        exchanges={"binance"},
        notional=500.0,
        expected_edge_bps=2.0,  # 低收益
        expected_pnl=0.1,
        risk_score=60.0,
        latency_score=40.0,
        vol_score=20.0,
        funding_score=40.0,
        liquidity_score=30.0,
        source=JobSource.MANUAL,
    ))

    # 7. 多个交易所的大额套利
    jobs.append(HedgeJob(
        symbol="BTC/USDT",
        exchanges={"binance", "okx", "edgex"},
        notional=15000.0,
        expected_edge_bps=20.0,
        expected_pnl=30.0,
        risk_score=35.0,
        latency_score=75.0,
        vol_score=85.0,
        funding_score=75.0,
        liquidity_score=95.0,
        source=JobSource.ARBITRAGE,
    ))

    return jobs


def print_separator(title=""):
    """打印分隔线"""
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def run_demo():
    """运行演示"""
    print_separator("对冲任务调度器演示")

    # 1. 创建调度器配置
    config = SchedulerConfig(
        max_global_concurrent_jobs=4,
        max_concurrent_per_exchange=2,
        max_notional_per_exchange=30000.0,
        risk_mode=RiskMode.BALANCED,
        min_score_threshold=30.0,
        enable_greedy_selection=True,
    )

    print("\n[配置] 调度器配置:")
    print(f"  - 风险模式: {config.risk_mode.value}")
    print(f"  - 全局最大并发: {config.max_global_concurrent_jobs}")
    print(f"  - 单交易所最大并发: {config.max_concurrent_per_exchange}")
    print(f"  - 单交易所最大名义金额: ${config.max_notional_per_exchange:,.0f}")
    print(f"  - 最低评分门槛: {config.min_score_threshold}")

    # 2. 创建调度器实例（不连接真实 CapitalOrchestrator）
    scheduler = HedgeScheduler(
        capital_orchestrator=None,  # 演示中不使用真实资金调度器
        config=config
    )

    # 3. 注册执行器
    scheduler.register_executor(JobSource.HEDGE_VOLUME, mock_hedge_executor)
    scheduler.register_executor(JobSource.ARBITRAGE, mock_arbitrage_executor)
    scheduler.register_executor(JobSource.MARKET_MAKING, mock_market_making_executor)

    print("\n[执行器] 已注册 3 个执行器:")
    print("  - HEDGE_VOLUME")
    print("  - ARBITRAGE")
    print("  - MARKET_MAKING")

    # 4. 创建并提交示例任务
    print_separator("提交任务")
    jobs = create_sample_jobs()

    print(f"\n[提交] 提交 {len(jobs)} 个任务到调度器:\n")
    for i, job in enumerate(jobs, 1):
        job_id = scheduler.submit_job(job)
        score = job.calculate_final_score(config.risk_mode)
        print(f"  {i}. [{job.source.value:15s}] {job.symbol:10s} | "
              f"Exchanges: {', '.join(sorted(job.exchanges)):30s} | "
              f"Notional: ${job.notional:7,.0f} | "
              f"Edge: {job.expected_edge_bps:5.1f}bps | "
              f"Score: {score:5.1f}")

    # 5. 第一轮调度
    print_separator("第 1 轮调度 (Tick)")
    print(f"\n[调度前状态]")
    state = scheduler.get_scheduler_state()
    print(f"  - 待调度: {state['pending_count']}")
    print(f"  - 运行中: {state['running_count']}")

    print("\n[执行调度]")
    result = scheduler.tick()
    print(f"  - 本轮调度成功: {result['scheduled']}")
    print(f"  - 本轮拒绝: {result['rejected']}")
    if result['rejected_reasons']:
        print(f"  - 拒绝原因: {result['rejected_reasons']}")

    print(f"\n[调度后状态]")
    state = scheduler.get_scheduler_state()
    print(f"  - 待调度: {state['pending_count']}")
    print(f"  - 运行中: {state['running_count']}")

    # 显示运行中的任务
    if state['running_jobs']:
        print(f"\n  运行中的任务:")
        for job in state['running_jobs']:
            print(f"    • {job['job_id']} | {job['symbol']} | "
                  f"Exchanges: {', '.join(job['exchanges'])} | "
                  f"${job['notional']:,.0f}")

    # 6. 模拟完成一些任务
    print_separator("模拟任务完成")
    completed_jobs = list(scheduler.state.running_jobs.values())[:2]
    for job in completed_jobs:
        print(f"\n[完成] 任务 {job.job_id[:8]} 执行成功")
        scheduler.on_job_finished(job.job_id, {
            "success": True,
            "pnl": job.expected_pnl * 0.9,  # 实际收益略低于预期
            "volume": job.notional * 2,
        })

    # 7. 第二轮调度
    print_separator("第 2 轮调度 (Tick)")
    print("\n[执行调度]")
    result = scheduler.tick()
    print(f"  - 本轮调度成功: {result['scheduled']}")
    print(f"  - 本轮拒绝: {result['rejected']}")
    if result['rejected_reasons']:
        print(f"  - 拒绝原因: {result['rejected_reasons']}")

    # 8. 显示最终状态
    print_separator("最终调度器状态")
    state = scheduler.get_scheduler_state()

    print(f"\n[统计数据]")
    print(f"  - 总提交: {state['total_submitted']}")
    print(f"  - 待调度: {state['pending_count']}")
    print(f"  - 运行中: {state['running_count']}")
    print(f"  - 已完成: {state['completed_count']}")
    print(f"  - 失败: {state['failed_count']}")
    print(f"  - 总收益: ${state['total_pnl']:,.2f}")
    print(f"  - 总成交量: ${state['total_volume']:,.2f}")

    print(f"\n[交易所状态]")
    for exchange, count in state['exchange_running'].items():
        notional = state['exchange_notional'].get(exchange, 0)
        print(f"  - {exchange:12s}: {count} 个任务运行中, 名义金额 ${notional:,.0f}")

    # 9. 展示待调度任务的评分排名
    if state['top_pending_jobs']:
        print(f"\n[Top 5 待调度任务（按评分排序）]")
        for i, job in enumerate(state['top_pending_jobs'], 1):
            print(f"  {i}. Score: {job['score']:5.1f} | "
                  f"{job['symbol']:10s} | "
                  f"Edge: {job['expected_edge_bps']:5.1f}bps | "
                  f"${job['notional']:7,.0f} | "
                  f"[{job['source']}]")

    # 10. 测试不同风险模式
    print_separator("测试不同风险模式下的评分")

    test_job = HedgeJob(
        symbol="BTC/USDT",
        exchanges={"binance", "okx"},
        notional=5000.0,
        expected_edge_bps=20.0,
        expected_pnl=10.0,
        risk_score=40.0,
        latency_score=80.0,
        vol_score=70.0,
        funding_score=60.0,
        liquidity_score=85.0,
        source=JobSource.ARBITRAGE,
    )

    print(f"\n[测试任务] {test_job.symbol} - Edge: {test_job.expected_edge_bps}bps, "
          f"Risk: {test_job.risk_score}, Volume: {test_job.vol_score}")
    print(f"\n不同风险模式下的评分:")

    for mode in RiskMode:
        score = test_job.calculate_final_score(risk_mode=mode)
        print(f"  - {mode.value:15s}: {score:6.2f}")

    print_separator("演示结束")
    print("\n完整的调度器状态字典:\n")
    pprint(state)


if __name__ == "__main__":
    run_demo()
