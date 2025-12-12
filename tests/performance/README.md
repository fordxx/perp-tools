# PerpBot V2 Performance Testing

完整的性能测试基础设施，用于验证系统的延迟、吞吐量和资源使用。

---

## 📁 目录结构

```
tests/performance/
├── README.md                      # 本文档
├── __init__.py
├── benchmark_config.py            # 性能基准配置
├── benchmark_utils.py             # 性能测试工具函数
├── test_market_data.py            # 行情数据处理性能测试
├── test_arbitrage_scanner.py      # 套利扫描器性能测试
├── test_risk_manager.py           # 风控管理器性能测试
├── run_all_benchmarks.py          # 运行所有测试的脚本
└── reports/                       # 测试报告输出目录
    └── (generated reports)
```

---

## 🎯 性能基准

### 核心组件基准

| Component | Target Latency | Max Latency | Target Throughput | Min Throughput |
|-----------|----------------|-------------|-------------------|----------------|
| Market Data Update | 1ms | 5ms | 1000 ops/s | 500 ops/s |
| WebSocket Message | 2ms | 10ms | 500 ops/s | 200 ops/s |
| Arbitrage Scan | 50ms | 100ms | 20 ops/s | 10 ops/s |
| Risk Check | 5ms | 20ms | 200 ops/s | 100 ops/s |
| Execution Decision | 10ms | 50ms | 100 ops/s | 50 ops/s |
| Position Aggregation | 20ms | 100ms | 50 ops/s | 20 ops/s |
| Exposure Calculation | 30ms | 150ms | 30 ops/s | 10 ops/s |
| Capital Snapshot | 100ms | 500ms | 10 ops/s | 5 ops/s |
| EventBus Dispatch | 1ms | 5ms | 1000 ops/s | 500 ops/s |
| End-to-End Trade | 200ms | 1000ms | 5 ops/s | 2 ops/s |

---

## 🚀 快速开始

### 1. 运行所有测试

```bash
# 进入测试目录
cd tests/performance

# 运行所有基准测试
python run_all_benchmarks.py

# 显示详细输出
python run_all_benchmarks.py -v

# 只运行匹配的测试
python run_all_benchmarks.py --filter market_data
```

### 2. 运行单个测试

```bash
# 行情数据处理性能测试
python test_market_data.py

# 套利扫描器性能测试
python test_arbitrage_scanner.py

# 风控管理器性能测试
python test_risk_manager.py
```

### 3. 查看报告

测试完成后，Markdown 报告会自动生成到 `reports/` 目录：

```bash
# 查看最新报告
ls -lt reports/
cat reports/market_data_perf_*.md
```

---

## 📊 测试场景

### Smoke Test (快速冒烟测试)
- **时长**: ~5分钟
- **迭代**: 100次
- **用途**: 快速验证系统基本性能
- **测试**: 行情更新、套利扫描、风控检查

```python
from benchmark_config import get_scenario_config

config = get_scenario_config("smoke")
```

### Standard Test (标准性能测试)
- **时长**: ~30分钟
- **迭代**: 1000次
- **用途**: 完整的性能基准测试
- **测试**: 所有核心组件

```python
config = get_scenario_config("standard")
```

### Stress Test (压力测试)
- **时长**: ~2小时
- **迭代**: 10000次
- **并发**: 50个任务
- **用途**: 验证系统在高负载下的稳定性
- **测试**: 所有核心组件

```python
config = get_scenario_config("stress")
```

### Endurance Test (耐久测试)
- **时长**: ~24小时
- **迭代**: 100000次
- **用途**: 验证系统长时间运行的稳定性
- **测试**: 行情更新、套利扫描、端到端交易

```python
config = get_scenario_config("endurance")
```

---

## 🔧 自定义测试

### 修改测试参数

编辑 `benchmark_config.py`：

```python
TEST_CONFIG = {
    "warmup_iterations": 100,     # 预热迭代次数
    "test_iterations": 1000,      # 测试迭代次数
    "concurrent_tasks": 10,       # 并发任务数
    "percentiles": [50, 75, 90, 95, 99, 99.9],  # 延迟百分位数
}
```

### 添加新的性能基准

在 `benchmark_config.py` 中添加：

```python
BENCHMARKS["my_component"] = PerformanceBenchmark(
    name="My Component",
    target_latency_ms=10.0,
    max_latency_ms=50.0,
    target_throughput=100.0,
    min_throughput=50.0,
)
```

### 编写新的测试

```python
from benchmark_config import get_benchmark, TEST_CONFIG
from benchmark_utils import BenchmarkRunner, PerformanceReporter

def test_my_component():
    # 待测试函数
    def my_function():
        # Your code here
        pass

    # 运行基准测试
    benchmark = get_benchmark("my_component")
    runner = BenchmarkRunner(
        warmup_iterations=TEST_CONFIG["warmup_iterations"],
        test_iterations=TEST_CONFIG["test_iterations"],
    )

    metrics = runner.run_benchmark(
        name="My Component",
        func=my_function,
    )

    # 打印结果
    PerformanceReporter.print_metrics(metrics, benchmark)

    # 断言性能要求
    assert metrics.latency_mean <= benchmark.max_latency_ms
    assert metrics.throughput >= benchmark.min_throughput

    return metrics
```

---

## 📈 性能指标说明

### 延迟指标

- **Mean (平均延迟)**: 所有迭代的平均处理时间
- **Median (中位数延迟)**: P50，50%的请求低于此延迟
- **Min/Max**: 最小/最大延迟
- **Std Dev (标准差)**: 延迟的波动程度
- **P95/P99**: 95%/99%的请求低于此延迟

### 吞吐量指标

- **Throughput (ops/sec)**: 每秒处理的操作数

### 内存指标

- **Current Memory**: 测试结束时的内存使用
- **Peak Memory**: 测试期间的峰值内存使用

---

## 🎯 性能目标

### 低延迟组件 (<10ms)
- 行情数据更新处理
- EventBus 事件分发
- WebSocket 消息处理

### 中延迟组件 (10-100ms)
- 套利机会扫描
- 风控检查
- 执行决策
- 持仓聚合

### 高延迟组件 (100-500ms)
- 风险敞口计算
- 资金快照生成

### 端到端流程 (<1s)
- 完整交易流程（发现机会 → 风控检查 → 执行下单）

---

## 🐛 故障排查

### 测试失败

1. **延迟超标**:
   - 检查是否有其他进程占用 CPU
   - 尝试增加预热迭代次数
   - 检查是否启用了调试模式

2. **吞吐量不足**:
   - 检查系统负载
   - 检查内存是否充足
   - 优化代码逻辑

3. **内存泄漏**:
   - 启用内存分析: `memory_profiling=True`
   - 使用 `tracemalloc` 定位泄漏点
   - 检查是否有未释放的资源

### 环境问题

```bash
# 确保依赖已安装
pip install -r requirements.txt

# 检查 Python 版本（需要 3.10+）
python --version

# 清理临时文件
rm -rf tests/performance/reports/*.md
```

---

## 📚 最佳实践

### 1. 测试前准备

- 关闭不必要的后台进程
- 确保系统资源充足
- 使用稳定的网络环境

### 2. 测试运行

- 先运行 smoke test 快速验证
- 定期运行 standard test 建立基线
- 发布前运行 stress test
- 定期运行 endurance test 验证稳定性

### 3. 结果分析

- 关注 P95/P99 延迟，而非平均延迟
- 监控内存使用趋势
- 对比历史基线，识别性能退化
- 记录测试环境信息

### 4. 持续改进

- 定期更新性能基准
- 优化高延迟组件
- 添加新组件的性能测试
- 集成到 CI/CD 流水线

---

## 🔗 相关文档

- [DEVELOPMENT_ROADMAP.md](../../DEVELOPMENT_ROADMAP.md) - 项目开发路线图
- [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) - 部署指南
- [RUNBOOK.md](../../docs/RUNBOOK.md) - 运维手册

---

## 📝 输出示例

### 控制台输出

```
================================================================================
Performance Test: Market Data Update Processing
================================================================================

Test Configuration:
  Iterations: 1000
  Duration:   1.23s

Latency (ms):
  Mean:       1.230
  Median:     1.150
  Min:        0.890
  Max:        3.450
  Std Dev:    0.320

Latency Percentiles (ms):
  P50:         1.150
  P75:         1.380
  P90:         1.670
  P95:         1.920
  P99:         2.340
  P99.9:       3.120

Throughput:
  812.35 ops/sec

Memory Usage:
  Current: 15.23 MB
  Peak:    18.67 MB

Benchmark Comparison:
  Target Latency:  1.0ms
  Max Latency:     5.0ms
  Target Throughput: 1000.0 ops/sec
  Min Throughput:    500.0 ops/sec

  Latency Check:    ✅ PASS
  Throughput Check: ✅ PASS

================================================================================

✅ Market Data Update test PASSED
```

### Markdown 报告

生成的报告包含：
- 测试摘要表格
- 详细的性能指标
- 延迟百分位数表格
- 内存使用统计

---

**维护者**: Claude Sonnet 4.5
**创建时间**: 2025-12-12
**版本**: 1.0.0
