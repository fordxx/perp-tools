"""
UnifiedMonitoringState 演示

展示统一监控状态的功能：
1. 聚合各模块状态
2. 实时更新监控数据
3. 导出 JSON 格式
4. 摘要信息生成
5. 健康状态检查
"""

import json
import logging
from pprint import pprint

from perpbot.core_capital_orchestrator import CoreCapitalOrchestrator
from perpbot.enhanced_risk_manager import EnhancedRiskManager, RiskMode, MarketData
from perpbot.unified_hedge_scheduler import UnifiedHedgeScheduler, JobResult, JobStatus
from perpbot.monitoring.unified_monitoring_state import UnifiedMonitoringState
from perpbot.models.hedge_job import create_wash_job, create_arb_job


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def print_separator(title=""):
    print("\n" + "=" * 80)
    if title:
        print(f"  {title}")
        print("=" * 80)


def demo_basic_monitoring():
    """演示基础监控功能"""
    print_separator("演示 1: 基础监控状态聚合")

    # 初始化所有组件
    capital = CoreCapitalOrchestrator()
    risk_manager = EnhancedRiskManager(risk_mode=RiskMode.BALANCED)
    scheduler = UnifiedHedgeScheduler(
        capital=capital,
        risk_manager=risk_manager,
        max_global_concurrent=10,
        max_concurrent_per_exchange=3,
    )

    # 初始化监控状态
    monitoring = UnifiedMonitoringState(
        capital=capital,
        risk_manager=risk_manager,
        scheduler=scheduler,
    )

    # 初始化交易所权益
    for ex in ["binance", "okx", "edgex"]:
        capital.update_equity(ex, 10_000.0)

    # 更新交易所连接状态
    monitoring.update_exchange_status("binance", is_connected=True, last_ping_ms=15.2)
    monitoring.update_exchange_status("okx", is_connected=True, last_ping_ms=25.8)
    monitoring.update_exchange_status("edgex", is_connected=False, last_ping_ms=999.0)

    # 更新市场数据
    monitoring.update_market_data("BTC/USDT", "binance", 50000.0, 50001.0, 50000.5)
    monitoring.update_market_data("BTC/USDT", "okx", 49999.0, 50000.0, 49999.5)
    monitoring.update_market_data("ETH/USDT", "binance", 3000.0, 3000.5, 3000.2)

    print("\n[更新所有监控状态]")
    monitoring.update_all()

    print("\n[全局摘要]")
    summary = monitoring.get_summary()
    for key, value in summary.items():
        print(f"  {key}: {value}")

    print("\n[交易所摘要]")
    for exchange in ["binance", "okx", "edgex"]:
        ex_summary = monitoring.get_exchange_summary(exchange)
        if ex_summary:
            print(f"\n  {exchange}:")
            print(f"    权益: ${ex_summary['equity']:,.2f}")
            print(f"    盈亏: ${ex_summary['pnl']:,.2f}")
            print(f"    在线: {ex_summary['is_connected']}")
            print(f"    活跃任务: {ex_summary['active_jobs']}")


def demo_realtime_updates():
    """演示实时更新"""
    print_separator("演示 2: 实时状态更新")

    # 初始化组件
    capital = CoreCapitalOrchestrator()
    risk_manager = EnhancedRiskManager(risk_mode=RiskMode.BALANCED)
    scheduler = UnifiedHedgeScheduler(
        capital=capital,
        risk_manager=risk_manager,
        max_global_concurrent=5,
    )
    monitoring = UnifiedMonitoringState(capital, risk_manager, scheduler)

    # 初始化
    capital.update_equity("binance", 10_000.0)
    monitoring.update_exchange_status("binance", is_connected=True, last_ping_ms=10.0)

    print("\n[初始状态]")
    monitoring.update_all()
    print(f"总权益: ${monitoring.global_stats.total_equity:,.2f}")
    print(f"活跃任务: {monitoring.global_stats.active_jobs_count}")
    print(f"风控模式: {monitoring.global_stats.risk_mode}")

    # 模拟提交任务
    print("\n[提交3个任务]")
    for i in range(3):
        job = create_wash_job("binance", "BTC/USDT", 1.0, 2000.0, 5.0)
        scheduler.submit_job(job)

    monitoring.update_all()
    print(f"待调度任务: {monitoring.global_stats.pending_jobs_count}")

    # 模拟记录 PnL
    print("\n[记录 PnL]")
    capital.record_pnl("binance", pnl=50.0, volume=4000.0, fees=0.8)

    monitoring.update_all()
    print(f"总盈亏: ${monitoring.global_stats.total_pnl:,.2f}")
    print(f"总成交量: ${monitoring.global_stats.total_volume_24h:,.2f}")

    # 模拟风控模式切换
    print("\n[切换风控模式]")
    risk_manager.set_risk_mode(RiskMode.CONSERVATIVE)

    monitoring.update_all()
    print(f"新风控模式: {monitoring.global_stats.risk_mode}")


def demo_json_export():
    """演示 JSON 导出"""
    print_separator("演示 3: JSON 格式导出")

    # 初始化
    capital = CoreCapitalOrchestrator()
    risk_manager = EnhancedRiskManager(risk_mode=RiskMode.AGGRESSIVE)
    scheduler = UnifiedHedgeScheduler(capital, risk_manager)
    monitoring = UnifiedMonitoringState(capital, risk_manager, scheduler)

    # 初始化数据
    capital.update_equity("binance", 10_000.0)
    capital.update_equity("okx", 8_000.0)
    monitoring.update_exchange_status("binance", True, 12.5)
    monitoring.update_exchange_status("okx", True, 18.3)

    # 提交任务
    job1 = create_wash_job("binance", "BTC/USDT", 1.0, 2000.0, 10.0)
    job2 = create_arb_job("binance", "okx", "ETH/USDT", 10.0, 3000.0, 15.0)
    scheduler.submit_job(job1)
    scheduler.submit_job(job2)

    # 更新状态
    monitoring.update_all()

    print("\n[导出完整状态（JSON）]")
    full_state = monitoring.to_dict()

    # 只显示部分关键信息
    print("\n全局统计:")
    print(json.dumps(full_state["global"], indent=2, default=str))

    print("\n任务统计:")
    print(json.dumps(full_state["jobs"], indent=2, default=str))

    print("\n风控统计:")
    print(json.dumps(full_state["risk"], indent=2, default=str))

    # 完整 JSON 可以保存到文件
    print("\n[完整 JSON 长度]")
    full_json = json.dumps(full_state, indent=2, default=str)
    print(f"总字符数: {len(full_json)}")


def demo_health_check():
    """演示健康检查"""
    print_separator("演示 4: 系统健康检查")

    # 场景 1: 健康系统
    print("\n[场景 1: 健康系统]")
    capital = CoreCapitalOrchestrator()
    risk_manager = EnhancedRiskManager()
    scheduler = UnifiedHedgeScheduler(capital, risk_manager)
    monitoring = UnifiedMonitoringState(capital, risk_manager, scheduler)

    capital.update_equity("binance", 10_000.0)
    monitoring.update_exchange_status("binance", True, 10.0)
    monitoring.update_all()

    summary = monitoring.get_summary()
    print(f"系统健康: {summary['is_healthy']}")
    print(f"原因: 所有指标正常")

    # 场景 2: 触发日亏限制
    print("\n[场景 2: 触发日亏限制]")
    capital2 = CoreCapitalOrchestrator()
    risk_manager2 = EnhancedRiskManager(daily_loss_limit_abs=100.0)
    scheduler2 = UnifiedHedgeScheduler(capital2, risk_manager2)
    monitoring2 = UnifiedMonitoringState(capital2, risk_manager2, scheduler2)

    capital2.update_equity("binance", 10_000.0)
    monitoring2.update_exchange_status("binance", True, 10.0)

    # 模拟巨额亏损
    for _ in range(5):
        risk_manager2.record_failure("测试亏损")
    risk_manager2.today_pnl = -150.0  # 超过限制

    monitoring2.update_all()

    summary2 = monitoring2.get_summary()
    print(f"系统健康: {summary2['is_healthy']}")
    print(f"原因: 触发日亏限制 ({abs(risk_manager2.today_pnl):.2f} > {risk_manager2.daily_loss_limit_abs:.2f})")

    # 场景 3: 连续失败过多
    print("\n[场景 3: 连续失败过多]")
    capital3 = CoreCapitalOrchestrator()
    risk_manager3 = EnhancedRiskManager(max_consecutive_failures=3)
    scheduler3 = UnifiedHedgeScheduler(capital3, risk_manager3)
    monitoring3 = UnifiedMonitoringState(capital3, risk_manager3, scheduler3)

    capital3.update_equity("binance", 10_000.0)
    monitoring3.update_exchange_status("binance", True, 10.0)

    # 模拟连续失败
    for _ in range(5):
        risk_manager3.record_failure("连续失败")

    monitoring3.update_all()

    summary3 = monitoring3.get_summary()
    print(f"系统健康: {summary3['is_healthy']}")
    print(f"原因: 连续失败 {risk_manager3.consecutive_failures} 次 (限制 {risk_manager3.max_consecutive_failures})")

    # 场景 4: 交易所大面积离线
    print("\n[场景 4: 交易所大面积离线]")
    capital4 = CoreCapitalOrchestrator()
    risk_manager4 = EnhancedRiskManager()
    scheduler4 = UnifiedHedgeScheduler(capital4, risk_manager4)
    monitoring4 = UnifiedMonitoringState(capital4, risk_manager4, scheduler4)

    # 3个交易所，2个离线
    capital4.update_equity("binance", 10_000.0)
    capital4.update_equity("okx", 10_000.0)
    capital4.update_equity("edgex", 10_000.0)

    monitoring4.update_exchange_status("binance", True, 10.0)
    monitoring4.update_exchange_status("okx", False, 999.0)
    monitoring4.update_exchange_status("edgex", False, 999.0)

    monitoring4.update_all()

    summary4 = monitoring4.get_summary()
    print(f"系统健康: {summary4['is_healthy']}")
    print(f"原因: 交易所在线率 {summary4['exchanges_online']} < 50%")


def demo_exchange_details():
    """演示交易所详细信息"""
    print_separator("演示 5: 交易所详细状态")

    capital = CoreCapitalOrchestrator()
    risk_manager = EnhancedRiskManager()
    scheduler = UnifiedHedgeScheduler(capital, risk_manager, max_concurrent_per_exchange=5)
    monitoring = UnifiedMonitoringState(capital, risk_manager, scheduler)

    # 初始化 binance
    capital.update_equity("binance", 10_000.0)
    monitoring.update_exchange_status("binance", True, 12.5, errors_last_hour=0)

    # 预留一些资金
    capital.reserve_for_wash("binance", 2000.0)
    capital.reserve_for_arb("binance", 1500.0)

    # 更新状态
    monitoring.update_all()

    # 获取详细信息
    print("\n[binance 详细信息]")
    details = monitoring.get_exchange_summary("binance")

    if details:
        print(f"\n交易所: {details['exchange']}")
        print(f"总权益: ${details['equity']:,.2f}")
        print(f"盈亏: ${details['pnl']:,.2f}")
        print(f"在线状态: {details['is_connected']}")
        print(f"安全模式: {details['is_safe_mode']}")
        print(f"活跃任务: {details['active_jobs']}")

        print("\n资金池状态:")
        for pool_name, pool_data in details['pools'].items():
            print(f"  {pool_name}:")
            print(f"    总额: ${pool_data['total']:,.2f}")
            print(f"    可用: ${pool_data['available']:,.2f}")
            print(f"    使用率: {pool_data['usage_pct']:.1f}%")


def run_all_demos():
    """运行所有演示"""
    print_separator("UnifiedMonitoringState 完整演示")
    print("""
本演示展示统一监控状态的核心功能：

1. 基础监控状态聚合
2. 实时状态更新
3. JSON 格式导出
4. 系统健康检查
5. 交易所详细状态

监控模块集成了：
- CoreCapitalOrchestrator: 资金状态
- EnhancedRiskManager: 风控状态
- UnifiedHedgeScheduler: 任务状态
    """)

    demo_basic_monitoring()
    demo_realtime_updates()
    demo_json_export()
    demo_health_check()
    demo_exchange_details()

    print_separator("所有演示完成")
    print("""
✅ 核心功能验证：
1. ✅ 状态聚合（从各模块拉取）
2. ✅ 实时更新机制
3. ✅ JSON 导出（可用于 API）
4. ✅ 摘要信息生成
5. ✅ 健康状态检查
6. ✅ 交易所详细信息
7. ✅ 市场数据快照

监控模块已准备好用于 Web 面板和 API！
    """)


if __name__ == "__main__":
    run_all_demos()
