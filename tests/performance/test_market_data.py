"""
Market Data Processing Performance Tests
测试行情数据处理性能
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from datetime import datetime
from perpbot.events.event_bus import EventBus
from perpbot.events.event_types import MarketDataUpdate

from benchmark_config import get_benchmark, TEST_CONFIG
from benchmark_utils import BenchmarkRunner, PerformanceReporter


def test_market_data_update():
    """测试行情数据更新处理性能"""
    # 初始化
    event_bus = EventBus()
    received_count = 0

    def on_market_data(event: MarketDataUpdate):
        nonlocal received_count
        received_count += 1

    event_bus.subscribe(MarketDataUpdate, on_market_data)

    # 待测试函数
    def publish_market_data():
        event = MarketDataUpdate(
            exchange="okx",
            symbol="BTC-USDT",
            bid=50000.0,
            ask=50001.0,
            bid_size=1.5,
            ask_size=2.0,
            timestamp=datetime.utcnow(),
        )
        event_bus.publish(event)

    # 运行基准测试
    benchmark = get_benchmark("market_data_update")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=TEST_CONFIG["memory_profiling"],
    )

    metrics = runner.run_benchmark(
        name="Market Data Update Processing",
        func=publish_market_data,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 验证
    assert received_count == TEST_CONFIG["test_iterations"], \
        f"Expected {TEST_CONFIG['test_iterations']} events, got {received_count}"

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms, \
        f"Mean latency {metrics.latency_mean:.3f}ms exceeds max {benchmark.max_latency_ms}ms"
    assert metrics.throughput >= benchmark.min_throughput, \
        f"Throughput {metrics.throughput:.2f} ops/s below min {benchmark.min_throughput} ops/s"

    print("✅ Market Data Update test PASSED")

    return metrics


def test_event_dispatch():
    """测试 EventBus 事件分发性能"""
    event_bus = EventBus()
    received = []

    # 注册多个订阅者
    def subscriber1(event: MarketDataUpdate):
        received.append(1)

    def subscriber2(event: MarketDataUpdate):
        received.append(2)

    def subscriber3(event: MarketDataUpdate):
        received.append(3)

    event_bus.subscribe(MarketDataUpdate, subscriber1)
    event_bus.subscribe(MarketDataUpdate, subscriber2)
    event_bus.subscribe(MarketDataUpdate, subscriber3)

    # 待测试函数
    def dispatch_event():
        event = MarketDataUpdate(
            exchange="okx",
            symbol="ETH-USDT",
            bid=3000.0,
            ask=3001.0,
            bid_size=10.0,
            ask_size=12.0,
            timestamp=datetime.utcnow(),
        )
        event_bus.publish(event)
        received.clear()  # 清理，避免内存累积

    # 运行基准测试
    benchmark = get_benchmark("event_dispatch")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=TEST_CONFIG["memory_profiling"],
    )

    metrics = runner.run_benchmark(
        name="EventBus Event Dispatch",
        func=dispatch_event,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms, \
        f"Mean latency {metrics.latency_mean:.3f}ms exceeds max {benchmark.max_latency_ms}ms"
    assert metrics.throughput >= benchmark.min_throughput, \
        f"Throughput {metrics.throughput:.2f} ops/s below min {benchmark.min_throughput} ops/s"

    print("✅ EventBus Dispatch test PASSED")

    return metrics


if __name__ == "__main__":
    print("=" * 80)
    print("Market Data Processing Performance Tests")
    print("=" * 80)
    print()

    all_metrics = []

    # 运行测试
    try:
        print("\n🚀 Test 1: Market Data Update Processing")
        m1 = test_market_data_update()
        all_metrics.append(m1)

        print("\n🚀 Test 2: EventBus Event Dispatch")
        m2 = test_event_dispatch()
        all_metrics.append(m2)

    except AssertionError as e:
        print(f"\n❌ Test FAILED: {e}")
        sys.exit(1)

    # 生成报告
    output_dir = Path(TEST_CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / f"market_data_perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    PerformanceReporter.generate_markdown_report(all_metrics, str(report_file))

    print("\n✅ All tests PASSED!")
    print(f"📊 Report: {report_file}")
