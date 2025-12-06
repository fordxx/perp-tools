"""
资金系统降级演示

展示如何使用简化的三层资金系统（S1/S2/S3）：
- S1 (wash_pool): 刷量对冲主层，70%
- S2 (arb_pool): 套利增强层，20%
- S3 (reserve_pool): 风险备用层，10%

内部映射到传统五层系统（L1-L5）：
- S1 → L1 + L2
- S2 → L3
- S3 → L4 + L5
"""

import logging
from pprint import pprint

from perpbot.capital.simple_capital_orchestrator import (
    CapitalPool,
    SimpleCapitalOrchestrator,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def print_separator(title=""):
    """打印分隔线"""
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def print_snapshot(orchestrator: SimpleCapitalOrchestrator):
    """打印资金快照"""
    snapshot = orchestrator.get_snapshot()

    for exchange, data in snapshot.items():
        print(f"\n[{exchange}]")
        print(f"  权益: ${data['equity']:,.2f}")
        print(f"  回撤: {data['drawdown_pct']*100:.2f}%")
        print(f"  安全模式: {'是' if data['safe_mode'] else '否'}")
        print(f"  累计成交量: ${data['total_volume']:,.2f}")
        print(f"  累计盈亏: ${data['realized_pnl']:,.4f}")

        print(f"\n  资金池状态:")
        for pool_name, pool_data in data['pools'].items():
            print(f"    [{pool_name}]")
            print(f"      总额: ${pool_data['pool_size']:,.2f}")
            print(f"      占用: ${pool_data['allocated']:,.2f}")
            print(f"      可用: ${pool_data['available']:,.2f}")
            print(f"      占用率: {pool_data['utilization_pct']:.1f}%")


def demo_basic_operations():
    """演示基础资金操作"""
    print_separator("演示 1: 基础资金预留与释放")

    # 创建资金调度器
    orchestrator = SimpleCapitalOrchestrator(
        wu_size=10_000.0,
        s1_wash_pct=0.70,   # S1: 70%
        s2_arb_pct=0.20,    # S2: 20%
        s3_reserve_pct=0.10 # S3: 10%
    )

    print("\n[初始化] 初始资金状态:")
    print_snapshot(orchestrator)

    # 场景 1: 刷量任务使用 S1_wash 池
    print_separator("场景 1: 刷量任务预留资金（S1_wash）")

    res1 = orchestrator.reserve_wash("binance", 3000.0)
    print(f"\n预留结果: {'✅ 成功' if res1.approved else '❌ 失败'}")
    if res1.approved:
        print(f"  交易所: {res1.exchange}")
        print(f"  资金池: {res1.pool.value}")
        print(f"  金额: ${res1.amount:,.2f}")

    print("\n资金池状态更新:")
    print_snapshot(orchestrator)

    # 场景 2: 套利任务使用 S2_arb 池
    print_separator("场景 2: 套利任务预留资金（S2_arb）")

    res2 = orchestrator.reserve_arb("okx", 1500.0)
    print(f"\n预留结果: {'✅ 成功' if res2.approved else '❌ 失败'}")
    if res2.approved:
        print(f"  交易所: {res2.exchange}")
        print(f"  资金池: {res2.pool.value}")
        print(f"  金额: ${res2.amount:,.2f}")

    print("\n资金池状态更新:")
    print_snapshot(orchestrator)

    # 场景 3: 尝试超额预留（应该失败）
    print_separator("场景 3: 尝试超额预留（应失败）")

    res3 = orchestrator.reserve_wash("binance", 5000.0)  # S1 只剩 4000
    print(f"\n预留结果: {'✅ 成功' if res3.approved else '❌ 失败'}")
    if not res3.approved:
        print(f"  拒绝原因: {res3.reason}")

    # 场景 4: 释放资金
    print_separator("场景 4: 释放已预留资金")

    print("\n释放刷量任务资金...")
    orchestrator.release(res1)

    print("\n资金池状态更新:")
    print_snapshot(orchestrator)

    # 场景 5: 再次预留（应该成功）
    print_separator("场景 5: 资金释放后重新预留")

    res4 = orchestrator.reserve_wash("binance", 5000.0)
    print(f"\n预留结果: {'✅ 成功' if res4.approved else '❌ 失败'}")

    print("\n资金池状态更新:")
    print_snapshot(orchestrator)

    # 清理
    orchestrator.release(res2)
    orchestrator.release(res4)


def demo_safe_mode():
    """演示安全模式"""
    print_separator("演示 2: 安全模式触发与限制")

    orchestrator = SimpleCapitalOrchestrator(
        wu_size=10_000.0,
        drawdown_limit_pct=0.05,  # 5% 回撤触发安全模式
    )

    print("\n[初始化] 正常模式:")
    print_snapshot(orchestrator)

    # 预留一些资金
    print_separator("预留资金")
    res1 = orchestrator.reserve_wash("binance", 2000.0)
    res2 = orchestrator.reserve_arb("binance", 1000.0)

    print("\n资金池状态:")
    print_snapshot(orchestrator)

    # 触发安全模式
    print_separator("触发安全模式（回撤 6%）")
    orchestrator.update_drawdown("binance", 0.06)

    print("\n资金池状态（安全模式）:")
    print_snapshot(orchestrator)

    # 尝试使用被禁止的池
    print_separator("安全模式下尝试预留资金")

    print("\n1. 尝试使用 S2_arb（应被拒绝）:")
    res3 = orchestrator.reserve_arb("binance", 500.0)
    print(f"   结果: {'✅ 成功' if res3.approved else '❌ 失败'}")
    if not res3.approved:
        print(f"   原因: {res3.reason}")

    print("\n2. 尝试使用 S1_wash（允许）:")
    res4 = orchestrator.reserve_wash("binance", 500.0)
    print(f"   结果: {'✅ 成功' if res4.approved else '❌ 失败'}")

    print("\n3. 尝试使用 S3_reserve（允许）:")
    res5 = orchestrator.reserve_reserve("binance", 500.0)
    print(f"   结果: {'✅ 成功' if res5.approved else '❌ 失败'}")

    # 回撤降低，解除安全模式
    print_separator("回撤降低，解除安全模式（回撤 3%）")
    orchestrator.update_drawdown("binance", 0.03)

    print("\n资金池状态（正常模式）:")
    print_snapshot(orchestrator)

    # 清理
    orchestrator.release(res1)
    orchestrator.release(res2)
    if res4.approved:
        orchestrator.release(res4)
    if res5.approved:
        orchestrator.release(res5)


def demo_multi_exchange():
    """演示多交易所资金管理"""
    print_separator("演示 3: 多交易所独立资金池")

    orchestrator = SimpleCapitalOrchestrator(wu_size=10_000.0)

    # 初始化多个交易所
    exchanges = ["binance", "okx", "edgex", "paradex"]

    print("\n[初始化] 为4个交易所初始化资金池...")
    for ex in exchanges:
        orchestrator._ensure_exchange(ex)

    print_snapshot(orchestrator)

    # 在不同交易所预留资金
    print_separator("在不同交易所预留资金")

    reservations = [
        orchestrator.reserve_wash("binance", 3000.0),
        orchestrator.reserve_arb("okx", 1500.0),
        orchestrator.reserve_wash("edgex", 2000.0),
        orchestrator.reserve_arb("paradex", 800.0),
    ]

    print("\n资金池状态:")
    print_snapshot(orchestrator)

    # 记录成交结果
    print_separator("记录成交结果")

    orchestrator.record_volume_result("binance", 6000.0, 12.0, -2.5)
    orchestrator.record_volume_result("okx", 3000.0, 4.5, 5.2)
    orchestrator.record_volume_result("edgex", 4000.0, 8.0, 1.8)

    print("\n资金池状态（含统计）:")
    print_snapshot(orchestrator)

    # 清理
    for res in reservations:
        if res.approved:
            orchestrator.release(res)


def demo_debug_view():
    """演示调试视图（显示内部 L1-L5 映射）"""
    print_separator("演示 4: 调试视图（显示 L1-L5 映射关系）")

    orchestrator = SimpleCapitalOrchestrator(wu_size=10_000.0)
    orchestrator._ensure_exchange("binance")

    print("\n[对外视图] 只显示 S1/S2/S3:")
    snapshot = orchestrator.get_snapshot()
    pprint(snapshot)

    print("\n[调试视图] 显示内部 L1-L5 映射:")
    debug_snapshot = orchestrator.get_debug_snapshot()
    pprint(debug_snapshot)

    print("\n[映射关系说明]")
    print("  S1_wash    → L1 + L2  (刷量对冲层)")
    print("  S2_arb     → L3       (套利层)")
    print("  S3_reserve → L4 + L5  (底仓 + 安全层)")


def run_all_demos():
    """运行所有演示"""
    print_separator("简化资金系统降级演示")
    print("""
本演示展示三层资金系统（S1/S2/S3）的使用方式：

- S1 (wash_pool):   刷量/对冲成交主层，70%  （内部映射 L1+L2）
- S2 (arb_pool):    微利套利增强层，20%    （内部映射 L3）
- S3 (reserve_pool): 风险备用层，10%       （内部映射 L4+L5）

所有策略模块统一通过以下接口访问资金：
- reserve_wash(exchange, amount)   # 刷量任务使用
- reserve_arb(exchange, amount)    # 套利任务使用
- reserve_reserve(exchange, amount)# 紧急情况使用
- release(reservation)              # 释放资金

禁止直接访问 L1-L5！
""")

    # 运行各个演示
    demo_basic_operations()
    demo_safe_mode()
    demo_multi_exchange()
    demo_debug_view()

    print_separator("所有演示完成")
    print("""
✅ 演示总结：

1. 基础操作：展示了资金预留、释放、超额拒绝等基本流程
2. 安全模式：回撤超限时自动限制资金池访问权限
3. 多交易所：每个交易所独立管理三层资金池
4. 调试视图：可查看内部 L1-L5 映射关系（仅限调试）

所有日志都明确标注使用的是 S1/S2/S3，不再暴露 L 层级概念。
""")


if __name__ == "__main__":
    run_all_demos()
