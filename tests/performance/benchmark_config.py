"""
Performance Testing Configuration
配置性能测试的参数和基准值
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class PerformanceBenchmark:
    """性能基准定义"""
    name: str
    target_latency_ms: float  # 目标延迟（毫秒）
    max_latency_ms: float  # 最大可接受延迟（毫秒）
    target_throughput: float  # 目标吞吐量（ops/sec）
    min_throughput: float  # 最低可接受吞吐量（ops/sec）


# ===========================================
# 性能基准定义
# ===========================================

BENCHMARKS: Dict[str, PerformanceBenchmark] = {
    # 行情数据处理
    "market_data_update": PerformanceBenchmark(
        name="Market Data Update Processing",
        target_latency_ms=1.0,
        max_latency_ms=5.0,
        target_throughput=1000.0,
        min_throughput=500.0,
    ),

    # WebSocket 消息处理
    "websocket_message": PerformanceBenchmark(
        name="WebSocket Message Processing",
        target_latency_ms=2.0,
        max_latency_ms=10.0,
        target_throughput=500.0,
        min_throughput=200.0,
    ),

    # 套利机会扫描
    "arbitrage_scan": PerformanceBenchmark(
        name="Arbitrage Opportunity Scan",
        target_latency_ms=50.0,
        max_latency_ms=100.0,
        target_throughput=20.0,
        min_throughput=10.0,
    ),

    # 风控检查
    "risk_check": PerformanceBenchmark(
        name="Risk Manager Check",
        target_latency_ms=5.0,
        max_latency_ms=20.0,
        target_throughput=200.0,
        min_throughput=100.0,
    ),

    # 订单执行决策
    "execution_decision": PerformanceBenchmark(
        name="Execution Decision Making",
        target_latency_ms=10.0,
        max_latency_ms=50.0,
        target_throughput=100.0,
        min_throughput=50.0,
    ),

    # 持仓聚合计算
    "position_aggregation": PerformanceBenchmark(
        name="Position Aggregation",
        target_latency_ms=20.0,
        max_latency_ms=100.0,
        target_throughput=50.0,
        min_throughput=20.0,
    ),

    # 风险敞口计算
    "exposure_calculation": PerformanceBenchmark(
        name="Exposure Calculation",
        target_latency_ms=30.0,
        max_latency_ms=150.0,
        target_throughput=30.0,
        min_throughput=10.0,
    ),

    # 资金快照生成
    "capital_snapshot": PerformanceBenchmark(
        name="Capital Snapshot Generation",
        target_latency_ms=100.0,
        max_latency_ms=500.0,
        target_throughput=10.0,
        min_throughput=5.0,
    ),

    # EventBus 事件分发
    "event_dispatch": PerformanceBenchmark(
        name="EventBus Dispatch",
        target_latency_ms=1.0,
        max_latency_ms=5.0,
        target_throughput=1000.0,
        min_throughput=500.0,
    ),

    # 完整交易流程（端到端）
    "end_to_end_trade": PerformanceBenchmark(
        name="End-to-End Trade Flow",
        target_latency_ms=200.0,
        max_latency_ms=1000.0,
        target_throughput=5.0,
        min_throughput=2.0,
    ),
}


# ===========================================
# 测试配置
# ===========================================

TEST_CONFIG = {
    # 测试运行配置
    "warmup_iterations": 100,  # 预热迭代次数
    "test_iterations": 1000,  # 正式测试迭代次数
    "concurrent_tasks": 10,  # 并发任务数（用于并发测试）

    # 数据生成配置
    "num_exchanges": 9,  # 模拟交易所数量
    "num_symbols": 10,  # 模拟交易对数量
    "market_data_rate": 100,  # 行情数据生成速率（/秒）

    # 报告配置
    "percentiles": [50, 75, 90, 95, 99, 99.9],  # 延迟百分位数
    "report_format": "markdown",  # 报告格式: markdown, json, html
    "output_dir": "tests/performance/reports",  # 报告输出目录

    # 内存分析配置
    "memory_profiling": True,  # 是否启用内存分析
    "memory_sample_rate": 100,  # 内存采样间隔（迭代次数）

    # 告警阈值
    "alert_on_regression": True,  # 性能退化时告警
    "regression_threshold": 0.2,  # 性能退化阈值（20%）
}


# ===========================================
# 测试场景定义
# ===========================================

TEST_SCENARIOS = {
    "smoke": {
        "description": "快速冒烟测试（5分钟）",
        "warmup_iterations": 10,
        "test_iterations": 100,
        "enabled_tests": [
            "market_data_update",
            "arbitrage_scan",
            "risk_check",
        ],
    },

    "standard": {
        "description": "标准性能测试（30分钟）",
        "warmup_iterations": 100,
        "test_iterations": 1000,
        "enabled_tests": list(BENCHMARKS.keys()),
    },

    "stress": {
        "description": "压力测试（2小时）",
        "warmup_iterations": 1000,
        "test_iterations": 10000,
        "concurrent_tasks": 50,
        "enabled_tests": list(BENCHMARKS.keys()),
    },

    "endurance": {
        "description": "耐久测试（24小时）",
        "warmup_iterations": 1000,
        "test_iterations": 100000,
        "enabled_tests": [
            "market_data_update",
            "arbitrage_scan",
            "end_to_end_trade",
        ],
    },
}


def get_benchmark(name: str) -> PerformanceBenchmark:
    """获取性能基准"""
    if name not in BENCHMARKS:
        raise ValueError(f"Unknown benchmark: {name}")
    return BENCHMARKS[name]


def get_scenario_config(scenario: str) -> Dict[str, Any]:
    """获取测试场景配置"""
    if scenario not in TEST_SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}. Available: {list(TEST_SCENARIOS.keys())}")
    return TEST_SCENARIOS[scenario]
