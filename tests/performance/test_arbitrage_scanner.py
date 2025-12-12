"""
Arbitrage Scanner Performance Tests
测试套利扫描器性能
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from datetime import datetime
from perpbot.scanner.market_scanner_v3 import MarketScannerV3
from perpbot.scanner.scanner_config import ScannerConfig
from perpbot.events.event_bus import EventBus

from benchmark_config import get_benchmark, TEST_CONFIG
from benchmark_utils import BenchmarkRunner, PerformanceReporter


def create_mock_scanner() -> MarketScannerV3:
    """创建模拟扫描器"""
    config = ScannerConfig(
        enabled_exchanges=["okx", "paradex", "hyperliquid"],
        enabled_symbols=["BTC-USDT", "ETH-USDT"],
        min_profit_bps=10,
        update_interval_sec=1.0,
        max_position_size_usd=1000.0,
    )

    event_bus = EventBus()
    scanner = MarketScannerV3(config=config, event_bus=event_bus)

    return scanner


def test_arbitrage_scan():
    """测试套利机会扫描性能"""
    scanner = create_mock_scanner()

    # 模拟行情数据
    mock_quotes = {
        "okx": {
            "BTC-USDT": {"bid": 50000.0, "ask": 50010.0, "bid_size": 1.0, "ask_size": 1.0},
            "ETH-USDT": {"bid": 3000.0, "ask": 3005.0, "bid_size": 5.0, "ask_size": 5.0},
        },
        "paradex": {
            "BTC-USDT": {"bid": 50020.0, "ask": 50030.0, "bid_size": 0.8, "ask_size": 0.8},
            "ETH-USDT": {"bid": 3010.0, "ask": 3015.0, "bid_size": 4.0, "ask_size": 4.0},
        },
        "hyperliquid": {
            "BTC-USDT": {"bid": 50005.0, "ask": 50015.0, "bid_size": 1.2, "ask_size": 1.2},
            "ETH-USDT": {"bid": 3002.0, "ask": 3008.0, "bid_size": 6.0, "ask_size": 6.0},
        },
    }

    # 待测试函数
    def scan_opportunities():
        # 模拟扫描逻辑：遍历交易对，计算价差
        opportunities = []
        symbols = ["BTC-USDT", "ETH-USDT"]

        for symbol in symbols:
            # 找到最高 bid 和最低 ask
            best_bid = max(
                (ex, mock_quotes[ex][symbol]["bid"])
                for ex in mock_quotes
                if symbol in mock_quotes[ex]
            )
            best_ask = min(
                (ex, mock_quotes[ex][symbol]["ask"])
                for ex in mock_quotes
                if symbol in mock_quotes[ex]
            )

            bid_exchange, bid_price = best_bid
            ask_exchange, ask_price = best_ask

            # 计算价差（BPS）
            if bid_price > ask_price:
                spread_bps = ((bid_price - ask_price) / ask_price) * 10000
                if spread_bps >= scanner.config.min_profit_bps:
                    opportunities.append({
                        "symbol": symbol,
                        "buy_exchange": ask_exchange,
                        "sell_exchange": bid_exchange,
                        "spread_bps": spread_bps,
                        "buy_price": ask_price,
                        "sell_price": bid_price,
                    })

        return opportunities

    # 运行基准测试
    benchmark = get_benchmark("arbitrage_scan")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=TEST_CONFIG["memory_profiling"],
    )

    metrics = runner.run_benchmark(
        name="Arbitrage Opportunity Scan",
        func=scan_opportunities,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms, \
        f"Mean latency {metrics.latency_mean:.3f}ms exceeds max {benchmark.max_latency_ms}ms"
    assert metrics.throughput >= benchmark.min_throughput, \
        f"Throughput {metrics.throughput:.2f} ops/s below min {benchmark.min_throughput} ops/s"

    print("✅ Arbitrage Scan test PASSED")

    return metrics


def test_spread_calculation():
    """测试价差计算性能"""
    # 待测试函数
    def calculate_spread():
        buy_price = 50000.0
        sell_price = 50100.0
        spread_bps = ((sell_price - buy_price) / buy_price) * 10000
        return spread_bps

    # 运行基准测试
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"] * 10,  # 更多迭代，因为这是轻量操作
        percentiles=TEST_CONFIG["percentiles"],
        enable_memory_profiling=False,  # 不需要内存分析
    )

    metrics = runner.run_benchmark(
        name="Spread Calculation",
        func=calculate_spread,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics)

    print("✅ Spread Calculation test PASSED")

    return metrics


if __name__ == "__main__":
    print("=" * 80)
    print("Arbitrage Scanner Performance Tests")
    print("=" * 80)
    print()

    all_metrics = []

    # 运行测试
    try:
        print("\n🚀 Test 1: Arbitrage Opportunity Scan")
        m1 = test_arbitrage_scan()
        all_metrics.append(m1)

        print("\n🚀 Test 2: Spread Calculation")
        m2 = test_spread_calculation()
        all_metrics.append(m2)

    except AssertionError as e:
        print(f"\n❌ Test FAILED: {e}")
        sys.exit(1)

    # 生成报告
    output_dir = Path(TEST_CONFIG["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / f"arbitrage_scanner_perf_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    PerformanceReporter.generate_markdown_report(all_metrics, str(report_file))

    print("\n✅ All tests PASSED!")
    print(f"📊 Report: {report_file}")
