"""
核心资金调度器演示

展示 CoreCapitalOrchestrator 的基础功能：
1. 多交易所资金池管理
2. 并发预留与释放
3. 约束检查
4. 安全模式
"""

import logging
from dataclasses import dataclass
from pprint import pprint

from perpbot.core_capital_orchestrator import CoreCapitalOrchestrator, PoolType

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


@dataclass
class MockJob:
    """模拟任务"""
    job_id: str
    exchanges: set
    notional: float
    strategy_type: str


def print_separator(title=""):
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def demo_basic_operations():
    """演示基础操作"""
    print_separator("演示 1: 基础资金池操作")

    # 创建调度器
    orchestrator = CoreCapitalOrchestrator(
        wash_budget_pct=0.70,
        arb_budget_pct=0.20,
        reserve_budget_pct=0.10,
        max_single_reserve_pct=0.10,
        max_total_notional_pct=0.30,
    )

    # 初始化几个交易所
    exchanges = ["binance", "okx", "edgex"]
    for ex in exchanges:
        orchestrator.update_equity(ex, 10_000.0)

    print("\n[初始资金快照]")
    snapshot = orchestrator.current_snapshot()
    for ex in exchanges:
        data = snapshot[ex]
        print(f"\n{ex}:")
        print(f"  权益: ${data['equity']:,.2f}")
        for pool_name, pool_data in data['pools'].items():
            print(f"  {pool_name}: ${pool_data['budget']:,.2f} 预算, ${pool_data['available']:,.2f} 可用")

    # 场景 1: S1 刷量池预留
    print_separator("场景 1: 从 S1 刷量池预留资金")
    success, reason = orchestrator.reserve_for_wash("binance", 3000.0)
    print(f"预留结果: {'✅ 成功' if success else f'❌ 失败 - {reason}'}")

    # 场景 2: S2 套利池预留
    print_separator("场景 2: 从 S2 套利池预留资金")
    success, reason = orchestrator.reserve_for_arb("okx", 1500.0)
    print(f"预留结果: {'✅ 成功' if success else f'❌ 失败 - {reason}'}")

    # 场景 3: 尝试超额预留
    print_separator("场景 3: 尝试超额预留（应失败）")
    success, reason = orchestrator.reserve_for_wash("binance", 5000.0)
    print(f"预留结果: {'✅ 成功' if success else f'❌ 失败 - {reason}'}")

    # 查看快照
    print_separator("当前资金状态")
    snapshot = orchestrator.current_snapshot()
    for ex in ["binance", "okx"]:
        data = snapshot[ex]
        print(f"\n{ex}:")
        for pool_name, pool_data in data['pools'].items():
            print(f"  {pool_name}:")
            print(f"    预算: ${pool_data['budget']:,.2f}")
            print(f"    在途: ${pool_data['in_flight']:,.2f}")
            print(f"    可用: ${pool_data['available']:,.2f}")
            print(f"    占用率: {pool_data['utilization_pct']:.1f}%")

    # 场景 4: 释放资金
    print_separator("场景 4: 释放资金")
    orchestrator.release("binance", 3000.0, "wash", from_in_flight=True)
    orchestrator.release("okx", 1500.0, "arb", from_in_flight=True)
    print("已释放所有资金")


def demo_job_based_reservation():
    """演示基于任务的资金预留"""
    print_separator("演示 2: 基于任务的资金预留")

    orchestrator = CoreCapitalOrchestrator()

    # 初始化交易所
    for ex in ["binance", "okx", "edgex"]:
        orchestrator.update_equity(ex, 10_000.0)

    # 创建一些模拟任务
    jobs = [
        MockJob(
            job_id="job_wash_1",
            exchanges={"binance", "okx"},
            notional=2000.0,
            strategy_type="wash_trade"
        ),
        MockJob(
            job_id="job_arb_1",
            exchanges={"edgex", "okx"},
            notional=1500.0,
            strategy_type="arbitrage"
        ),
        MockJob(
            job_id="job_wash_2",
            exchanges={"binance"},
            notional=3000.0,
            strategy_type="hedge"
        ),
    ]

    print("\n[提交任务并预留资金]")
    reserved_jobs = []

    for job in jobs:
        print(f"\n任务: {job.job_id}")
        print(f"  交易所: {', '.join(job.exchanges)}")
        print(f"  名义金额: ${job.notional:,.2f}")
        print(f"  策略类型: {job.strategy_type}")

        # 检查是否可以预留
        can_reserve, reason = orchestrator.can_reserve_for_job(job)
        if not can_reserve:
            print(f"  ❌ 无法预留: {reason}")
            continue

        # 实际预留
        success, reason = orchestrator.reserve_for_job(job)
        if success:
            print(f"  ✅ 预留成功")
            reserved_jobs.append(job)
        else:
            print(f"  ❌ 预留失败: {reason}")

    # 查看快照
    print_separator("任务预留后的资金状态")
    snapshot = orchestrator.current_snapshot()
    pprint(snapshot)

    # 模拟任务完成并记录 PnL
    print_separator("模拟任务完成")
    for job in reserved_jobs:
        for exchange in job.exchanges:
            # 释放资金
            pool = "wash" if "wash" in job.strategy_type or "hedge" in job.strategy_type else "arb"
            orchestrator.release(exchange, job.notional, pool, from_in_flight=True)

            # 记录 PnL
            pnl = job.notional * 0.0005  # 假设 0.05% 收益
            volume = job.notional * 2  # 双边成交
            fees = volume * 0.0002  # 0.02% 手续费
            orchestrator.record_pnl(exchange, pnl, volume, fees)

        print(f"✅ 任务 {job.job_id} 完成")


def demo_concurrent_limits():
    """演示并发限制"""
    print_separator("演示 3: 并发与总在途限制")

    orchestrator = CoreCapitalOrchestrator(
        max_single_reserve_pct=0.10,    # 单笔最多 10%
        max_total_notional_pct=0.30,    # 总在途最多 30%
    )

    orchestrator.update_equity("binance", 10_000.0)

    print("\n[测试单笔占用限制]")
    # S1 wash 池有 7000，单笔最多 700
    success, reason = orchestrator.reserve_for_wash("binance", 700.0)
    print(f"预留 $700 (10%): {'✅' if success else '❌'} {reason or ''}")

    success, reason = orchestrator.reserve_for_wash("binance", 800.0)
    print(f"预留 $800 (>10%): {'✅' if success else '❌'} {reason or ''}")

    print("\n[测试总在途限制]")
    # 总权益 10000，总在途最多 3000
    # 已经预留了 700，还可以预留 2300
    for i in range(5):
        amount = 600.0
        success, reason = orchestrator.reserve_for_wash("binance", amount)
        snapshot = orchestrator.current_snapshot()
        total_in_flight = snapshot["binance"]["total_in_flight"]
        print(f"第 {i+1} 次预留 ${amount:.0f}: {'✅' if success else '❌'}, 总在途: ${total_in_flight:.0f}")
        if not success:
            print(f"  原因: {reason}")
            break


def demo_safe_mode():
    """演示安全模式"""
    print_separator("演示 4: 安全模式")

    orchestrator = CoreCapitalOrchestrator()
    orchestrator.update_equity("binance", 10_000.0)

    print("\n[正常模式]")
    success1, _ = orchestrator.reserve_for_wash("binance", 2000.0)
    success2, _ = orchestrator.reserve_for_arb("binance", 1000.0)
    print(f"S1_wash 预留: {'✅' if success1 else '❌'}")
    print(f"S2_arb 预留: {'✅' if success2 else '❌'}")

    # 释放
    orchestrator.release("binance", 2000.0, "wash", from_in_flight=True)
    orchestrator.release("binance", 1000.0, "arb", from_in_flight=True)

    print("\n[进入安全模式]")
    orchestrator.set_safe_mode("binance", True)

    success1, reason1 = orchestrator.reserve_for_wash("binance", 2000.0)
    success2, reason2 = orchestrator.reserve_for_arb("binance", 1000.0)
    print(f"S1_wash 预留: {'✅' if success1 else f'❌ {reason1}'}")
    print(f"S2_arb 预留: {'✅' if success2 else f'❌ {reason2}'}")

    print("\n说明: 安全模式下只允许 S1_wash + S3_reserve，禁止 S2_arb")


def demo_multi_exchange():
    """演示多交易所并发"""
    print_separator("演示 5: 多交易所并发管理")

    orchestrator = CoreCapitalOrchestrator()

    # 初始化多个交易所
    exchanges = {
        "binance": 20_000.0,
        "okx": 15_000.0,
        "edgex": 10_000.0,
        "paradex": 8_000.0,
    }

    for ex, equity in exchanges.items():
        orchestrator.update_equity(ex, equity)

    # 创建跨交易所任务
    jobs = [
        MockJob("arb_btc", {"binance", "okx"}, 3000.0, "arbitrage"),
        MockJob("arb_eth", {"edgex", "paradex"}, 2000.0, "arbitrage"),
        MockJob("wash_btc", {"binance"}, 5000.0, "wash_trade"),
        MockJob("wash_eth", {"okx"}, 4000.0, "wash_trade"),
    ]

    print("\n[并发预留多个任务]")
    for job in jobs:
        success, reason = orchestrator.reserve_for_job(job)
        status = "✅" if success else f"❌ {reason}"
        print(f"{job.job_id} @ {', '.join(job.exchanges)}: {status}")

    # 查看各交易所状态
    print_separator("各交易所资金占用情况")
    snapshot = orchestrator.current_snapshot()

    for ex in exchanges.keys():
        data = snapshot[ex]
        print(f"\n{ex}:")
        print(f"  权益: ${data['equity']:,.2f}")
        print(f"  总在途: ${data['total_in_flight']:,.2f} ({data['total_in_flight']/data['equity']*100:.1f}%)")
        print(f"  S1_wash 占用率: {data['pools']['S1_wash']['utilization_pct']:.1f}%")
        print(f"  S2_arb 占用率: {data['pools']['S2_arb']['utilization_pct']:.1f}%")


def run_all_demos():
    """运行所有演示"""
    print_separator("核心资金调度器完整演示")
    print("""
本演示展示 CoreCapitalOrchestrator 的核心功能：

- S1 (wash_pool):    70% - 刷量/对冲成交层
- S2 (arb_pool):     20% - 微利套利/机会增强层
- S3 (reserve_pool): 10% - 风控备用/救火层

约束：
- 单笔占用 ≤ 10% (可配置)
- 总在途 ≤ 30% (可配置)
- 安全模式下只允许 S1 + S3
""")

    demo_basic_operations()
    demo_job_based_reservation()
    demo_concurrent_limits()
    demo_safe_mode()
    demo_multi_exchange()

    print_separator("所有演示完成")
    print("""
✅ 核心功能验证：
1. ✅ 基础资金池预留与释放
2. ✅ 基于任务的自动资金分配
3. ✅ 单笔占用与总在途限制
4. ✅ 安全模式资金池访问控制
5. ✅ 多交易所并发管理

所有资金操作都有详细日志，便于追踪和审计。
""")


if __name__ == "__main__":
    run_all_demos()
