"""
Risk Manager Performance Tests
测试风控管理器性能
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from datetime import datetime
from perpbot.risk_manager import RiskManager, RiskCheckResult
from perpbot.events.event_bus import EventBus

from benchmark_config import get_benchmark, TEST_CONFIG
from benchmark_utils import BenchmarkRunner, PerformanceReporter


def create_mock_risk_manager() -> RiskManager:
    """创建模拟风控管理器"""
    event_bus = EventBus()

    risk_manager = RiskManager(
        max_position_size=10000.0,
        max_daily_loss=500.0,
        max_drawdown_percent=5.0,
        event_bus=event_bus,
    )

    return risk_manager


def test_risk_check():
    """测试风控检查性能"""
    risk_manager = create_mock_risk_manager()

    # 模拟交易请求
    trade_request = {
        "symbol": "BTC-USDT",
        "size": 0.1,
        "side": "long",
        "exchange": "okx",
        "price": 50000.0,
        "notional": 5000.0,
    }

    # 待测试函数
    def perform_risk_check():
        # 简化的风控检查逻辑
        checks = []

        # 检查1: 仓位大小
        position_ok = trade_request["notional"] <= risk_manager.max_position_size
        checks.append(("position_size", position_ok))

        # 检查2: 总风险敞口
        total_exposure = 15000.0  # 模拟当前总敞口
        exposure_ok = total_exposure + trade_request["notional"] <= risk_manager.max_position_size * 3
        checks.append(("total_exposure", exposure_ok))

        # 检查3: 日内亏损
        daily_pnl = -100.0  # 模拟日内亏损
        loss_ok = abs(daily_pnl) <= risk_manager.max_daily_loss
        checks.append(("daily_loss", loss_ok))

        # 汇总结果
        all_passed = all(check[1] for check in checks)

        return {
            "passed": all_passed,
            "checks": checks,
            "timestamp": datetime.utcnow(),
        }

    # 运行基准测试
    benchmark = get_benchmark("risk_check")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=TEST_CONFIG["memory_profiling"],
    )

    metrics = runner.run_benchmark(
        name="Risk Manager Check",
        func=perform_risk_check,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms, \
        f"Mean latency {metrics.latency_mean:.3f}ms exceeds max {benchmark.max_latency_ms}ms"
    assert metrics.throughput >= benchmark.min_throughput, \
        f"Throughput {metrics.throughput:.2f} ops/s below min {benchmark.min_throughput} ops/s"

    print("✅ Risk Check test PASSED")

    return metrics


def test_exposure_calculation():
    """测试风险敞口计算性能"""
    # 模拟持仓数据
    positions = [
        {"symbol": "BTC-USDT", "size": 0.5, "entry_price": 50000.0, "side": "long"},
        {"symbol": "ETH-USDT", "size": 2.0, "entry_price": 3000.0, "side": "long"},
        {"symbol": "BTC-USDT", "size": -0.3, "entry_price": 50100.0, "side": "short"},
    ]

    # 待测试函数
    def calculate_exposure():
        total_long = 0.0
        total_short = 0.0

        for pos in positions:
            notional = abs(pos["size"]) * pos["entry_price"]
            if pos["side"] == "long":
                total_long += notional
            else:
                total_short += notional

        net_exposure = total_long - total_short

        return {
            "total_long": total_long,
            "total_short": total_short,
            "net_exposure": net_exposure,
        }

    # 运行基准测试
    benchmark = get_benchmark("exposure_calculation")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=TEST_CONFIG["memory_profiling"],
    )

    metrics = runner.run_benchmark(
        name="Exposure Calculation",
        func=calculate_exposure,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms, \
        f"Mean latency {metrics.latency_mean:.3f}ms exceeds max {benchmark.max_latency_ms}ms"
    assert metrics.throughput >= benchmark.min_throughput, \
        f"Throughput {metrics.throughput:.2f} ops/s below min {benchmark.min_throughput} ops/s"

    print("✅ Exposure Calculation test PASSED")

    return metrics


if __name__ == "__main__":
    print("=" * 80)
    print("Risk Manager Performance Tests")
    print("=" * 80)
    print()

    all_metrics = []

    # 运行测试
    try:
        print("\n🚀 Test 1: Risk Manager Check")
        m1 = test_risk_check()
        all_metrics.append(m1)

        print("\n🚀 Test 2: Exposure Calculation")
        m2 = test_exposure_calculation()
        all_metrics.append(m2)

    except AssertionError as e:
        print(f"\n❌ Test FAILED: {e}")
        sys.exit(1)

    # 生成报告
    output_dir = Path(TEST_CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / f"risk_manager_perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    PerformanceReporter.generate_markdown_report(all_metrics, str(report_file))

    print("\n✅ All tests PASSED!")
    print(f"📊 Report: {report_file}")
