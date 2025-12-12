"""
Performance Testing Utilities
性能测试工具函数
"""
import time
import statistics
import tracemalloc
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class PerformanceMetrics:
    """性能指标"""
    name: str
    iterations: int
    duration_sec: float

    # 延迟统计（毫秒）
    latency_mean: float
    latency_median: float
    latency_min: float
    latency_max: float
    latency_std: float
    latency_percentiles: Dict[int, float] = field(default_factory=dict)

    # 吞吐量
    throughput: float  # ops/sec

    # 内存使用（字节）
    memory_current: Optional[int] = None
    memory_peak: Optional[int] = None

    # 时间戳
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "iterations": self.iterations,
            "duration_sec": self.duration_sec,
            "latency_ms": {
                "mean": self.latency_mean,
                "median": self.latency_median,
                "min": self.latency_min,
                "max": self.latency_max,
                "std": self.latency_std,
                "percentiles": self.latency_percentiles,
            },
            "throughput_ops_per_sec": self.throughput,
            "memory_bytes": {
                "current": self.memory_current,
                "peak": self.memory_peak,
            },
            "timestamp": self.timestamp,
        }

    def to_json(self, indent: int = 2) -> str:
        """转换为 JSON"""
        return json.dumps(self.to_dict(), indent=indent)


class BenchmarkRunner:
    """性能测试运行器"""

    def __init__(
        self,
        warmup_iterations: int = 100,
        test_iterations: int = 1000,
        percentiles: Optional[List[int]] = None,
        enable_memory_profiling: bool = True,
    ):
        self.warmup_iterations = warmup_iterations
        self.test_iterations = test_iterations
        self.percentiles = percentiles or [50, 75, 90, 95, 99, 99.9]
        self.enable_memory_profiling = enable_memory_profiling

    def run_benchmark(
        self,
        name: str,
        func: Callable,
        *args,
        **kwargs,
    ) -> PerformanceMetrics:
        """
        运行性能测试

        Args:
            name: 测试名称
            func: 待测试的函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            性能指标
        """
        # 预热
        print(f"[{name}] Warming up ({self.warmup_iterations} iterations)...")
        for _ in range(self.warmup_iterations):
            func(*args, **kwargs)

        # 启动内存分析
        if self.enable_memory_profiling:
            tracemalloc.start()

        # 正式测试
        print(f"[{name}] Running benchmark ({self.test_iterations} iterations)...")
        latencies = []
        start_time = time.perf_counter()

        for i in range(self.test_iterations):
            iter_start = time.perf_counter()
            func(*args, **kwargs)
            iter_end = time.perf_counter()

            latencies.append((iter_end - iter_start) * 1000)  # 转换为毫秒

        end_time = time.perf_counter()
        duration = end_time - start_time

        # 内存使用
        memory_current = None
        memory_peak = None
        if self.enable_memory_profiling:
            current, peak = tracemalloc.get_traced_memory()
            memory_current = current
            memory_peak = peak
            tracemalloc.stop()

        # 计算统计指标
        metrics = self._calculate_metrics(
            name=name,
            latencies=latencies,
            duration=duration,
            memory_current=memory_current,
            memory_peak=memory_peak,
        )

        return metrics

    def _calculate_metrics(
        self,
        name: str,
        latencies: List[float],
        duration: float,
        memory_current: Optional[int],
        memory_peak: Optional[int],
    ) -> PerformanceMetrics:
        """计算性能指标"""
        n = len(latencies)

        # 延迟统计
        mean = statistics.mean(latencies)
        median = statistics.median(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        std = statistics.stdev(latencies) if n > 1 else 0.0

        # 百分位数
        sorted_latencies = sorted(latencies)
        percentiles = {}
        for p in self.percentiles:
            idx = int((p / 100.0) * n)
            if idx >= n:
                idx = n - 1
            percentiles[p] = sorted_latencies[idx]

        # 吞吐量
        throughput = n / duration

        return PerformanceMetrics(
            name=name,
            iterations=n,
            duration_sec=duration,
            latency_mean=mean,
            latency_median=median,
            latency_min=min_latency,
            latency_max=max_latency,
            latency_std=std,
            latency_percentiles=percentiles,
            throughput=throughput,
            memory_current=memory_current,
            memory_peak=memory_peak,
        )


class PerformanceReporter:
    """性能测试报告生成器"""

    @staticmethod
    def print_metrics(metrics: PerformanceMetrics, benchmark: Optional[Any] = None) -> None:
        """打印性能指标（控制台友好格式）"""
        print(f"\n{'=' * 80}")
        print(f"Performance Test: {metrics.name}")
        print(f"{'=' * 80}")

        print(f"\nTest Configuration:")
        print(f"  Iterations: {metrics.iterations}")
        print(f"  Duration:   {metrics.duration_sec:.2f}s")

        print(f"\nLatency (ms):")
        print(f"  Mean:       {metrics.latency_mean:.3f}")
        print(f"  Median:     {metrics.latency_median:.3f}")
        print(f"  Min:        {metrics.latency_min:.3f}")
        print(f"  Max:        {metrics.latency_max:.3f}")
        print(f"  Std Dev:    {metrics.latency_std:.3f}")

        if metrics.latency_percentiles:
            print(f"\nLatency Percentiles (ms):")
            for p, val in sorted(metrics.latency_percentiles.items()):
                print(f"  P{p:>5}: {val:>10.3f}")

        print(f"\nThroughput:")
        print(f"  {metrics.throughput:.2f} ops/sec")

        if metrics.memory_current is not None:
            print(f"\nMemory Usage:")
            print(f"  Current: {metrics.memory_current / 1024 / 1024:.2f} MB")
            print(f"  Peak:    {metrics.memory_peak / 1024 / 1024:.2f} MB")

        # 与基准对比
        if benchmark:
            print(f"\nBenchmark Comparison:")
            print(f"  Target Latency:  {benchmark.target_latency_ms:.1f}ms")
            print(f"  Max Latency:     {benchmark.max_latency_ms:.1f}ms")
            print(f"  Target Throughput: {benchmark.target_throughput:.1f} ops/sec")
            print(f"  Min Throughput:    {benchmark.min_throughput:.1f} ops/sec")

            # 状态评估
            latency_status = "✅ PASS" if metrics.latency_mean <= benchmark.max_latency_ms else "❌ FAIL"
            throughput_status = "✅ PASS" if metrics.throughput >= benchmark.min_throughput else "❌ FAIL"

            print(f"\n  Latency Check:    {latency_status}")
            print(f"  Throughput Check: {throughput_status}")

            if metrics.latency_mean <= benchmark.target_latency_ms:
                print(f"  🎯 Latency meets target!")
            if metrics.throughput >= benchmark.target_throughput:
                print(f"  🎯 Throughput meets target!")

        print(f"\n{'=' * 80}\n")

    @staticmethod
    def generate_markdown_report(
        metrics_list: List[PerformanceMetrics],
        output_file: str,
    ) -> None:
        """生成 Markdown 格式报告"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Performance Test Report\n\n")
            f.write(f"**Generated**: {datetime.utcnow().isoformat()}\n\n")

            f.write("## Summary\n\n")
            f.write("| Test Name | Iterations | Mean (ms) | P95 (ms) | P99 (ms) | Throughput (ops/s) |\n")
            f.write("|-----------|------------|-----------|----------|----------|--------------------|\n")

            for m in metrics_list:
                p95 = m.latency_percentiles.get(95, 0.0)
                p99 = m.latency_percentiles.get(99, 0.0)
                f.write(
                    f"| {m.name} | {m.iterations} | {m.latency_mean:.3f} | {p95:.3f} | {p99:.3f} | {m.throughput:.2f} |\n"
                )

            f.write("\n## Detailed Results\n\n")

            for m in metrics_list:
                f.write(f"### {m.name}\n\n")
                f.write(f"- **Iterations**: {m.iterations}\n")
                f.write(f"- **Duration**: {m.duration_sec:.2f}s\n")
                f.write(f"- **Mean Latency**: {m.latency_mean:.3f}ms\n")
                f.write(f"- **Median Latency**: {m.latency_median:.3f}ms\n")
                f.write(f"- **Throughput**: {m.throughput:.2f} ops/sec\n")

                if m.memory_peak:
                    f.write(f"- **Peak Memory**: {m.memory_peak / 1024 / 1024:.2f} MB\n")

                f.write("\n**Latency Percentiles**:\n\n")
                f.write("| Percentile | Latency (ms) |\n")
                f.write("|------------|-------------|\n")
                for p, val in sorted(m.latency_percentiles.items()):
                    f.write(f"| P{p} | {val:.3f} |\n")

                f.write("\n")

        print(f"✅ Markdown report saved to: {output_file}")


def format_memory_size(size_bytes: int) -> str:
    """格式化内存大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"
