#!/usr/bin/env python3
"""
Run All Unit Tests
运行所有单元测试
"""
import sys
import unittest
from pathlib import Path


def discover_and_run_tests():
    """发现并运行所有单元测试"""
    # 测试目录
    test_dir = Path(__file__).parent

    # 使用 unittest 的测试发现功能
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir=str(test_dir),
        pattern="test_*.py",
        top_level_dir=str(test_dir.parent.parent)
    )

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 返回退出码
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(discover_and_run_tests())
