#!/usr/bin/env python3
"""
Run All Performance Benchmarks
运行所有性能测试
"""
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import argparse


# 测试文件列表
TEST_FILES = [
    "test_market_data.py",
    "test_arbitrage_scanner.py",
    "test_risk_manager.py",
]


def run_test(test_file: Path, verbose: bool = False) -> bool:
    """
    运行单个测试文件

    Args:
        test_file: 测试文件路径
        verbose: 是否显示详细输出

    Returns:
        测试是否通过
    """
    print(f"\n{'=' * 80}")
    print(f"Running: {test_file.name}")
    print(f"{'=' * 80}\n")

    try:
        result = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=test_file.parent,
            capture_output=not verbose,
            text=True,
            timeout=600,  # 10分钟超时
        )

        if result.returncode == 0:
            print(f"✅ {test_file.name} PASSED")
            if not verbose and result.stdout:
                # 只显示关键信息
                lines = result.stdout.split("\n")
                for line in lines:
                    if "PASS" in line or "FAIL" in line or "Report:" in line:
                        print(f"   {line}")
            return True
        else:
            print(f"❌ {test_file.name} FAILED")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
            return False

    except subprocess.TimeoutExpired:
        print(f"⏱️  {test_file.name} TIMEOUT (>10 minutes)")
        return False
    except Exception as e:
        print(f"💥 {test_file.name} ERROR: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run all performance benchmarks")
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed test output"
    )
    parser.add_argument(
        "--filter",
        type=str,
        help="Only run tests matching this pattern"
    )
    args = parser.parse_args()

    print("=" * 80)
    print("PerpBot V2 Performance Benchmark Suite")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 确定测试目录
    test_dir = Path(__file__).parent

    # 过滤测试文件
    test_files = TEST_FILES
    if args.filter:
        test_files = [f for f in test_files if args.filter in f]
        print(f"Filtered tests: {test_files}")
        print()

    # 运行测试
    results = {}
    for test_file_name in test_files:
        test_file = test_dir / test_file_name
        if not test_file.exists():
            print(f"⚠️  Test file not found: {test_file}")
            results[test_file_name] = False
            continue

        passed = run_test(test_file, verbose=args.verbose)
        results[test_file_name] = passed

    # 汇总结果
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)

    passed_count = sum(1 for p in results.values() if p)
    failed_count = len(results) - passed_count

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:10} | {test_name}")

    print()
    print(f"Total:  {len(results)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")

    if failed_count == 0:
        print("\n🎉 All performance tests PASSED!")
        return 0
    else:
        print(f"\n💔 {failed_count} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
