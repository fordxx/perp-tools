#!/usr/bin/env python3
"""通用交易所测试框架

用于快速测试所有已配置交易所的基本功能。
无需真实交易，只测试连接和查询功能。

使用方法:
    python test_all_exchanges.py              # 测试所有交易所
    python test_all_exchanges.py paradex      # 只测试 Paradex
    python test_all_exchanges.py --trading    # 包含交易测试（谨慎！）
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果"""
    exchange: str
    test_name: str
    passed: bool
    duration_ms: float
    error: Optional[str] = None
    details: Optional[str] = None


class ExchangeTester:
    """通用交易所测试器"""

    # 支持的交易所及其环境变量
    EXCHANGES = {
        "paradex": {
            "required_env": ["PARADEX_L2_PRIVATE_KEY", "PARADEX_ACCOUNT_ADDRESS"],
            "class": "ParadexClient",
            "module": "perpbot.exchanges.paradex",
        },
        "extended": {
            "required_env": ["EXTENDED_API_KEY"],
            "class": "ExtendedClient",
            "module": "perpbot.exchanges.extended",
        },
        "lighter": {
            "required_env": ["LIGHTER_API_KEY"],
            "class": "LighterClient",
            "module": "perpbot.exchanges.lighter",
        },
        "edgex": {
            "required_env": ["EDGEX_API_KEY"],
            "class": "EdgeXClient",
            "module": "perpbot.exchanges.edgex",
        },
        "backpack": {
            "required_env": ["BACKPACK_API_KEY", "BACKPACK_API_SECRET"],
            "class": "BackpackClient",
            "module": "perpbot.exchanges.backpack",
        },
        "grvt": {
            "required_env": ["GRVT_API_KEY"],
            "class": "GRVTClient",
            "module": "perpbot.exchanges.grvt",
        },
        "aster": {
            "required_env": ["ASTER_API_KEY"],
            "class": "AsterClient",
            "module": "perpbot.exchanges.aster",
        },
        "okx": {
            "required_env": ["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"],
            "class": "OKXClient",
            "module": "perpbot.exchanges.okx",
        },
    }

    DEFAULT_SYMBOL = "ETH/USDT"

    def __init__(self, include_trading: bool = False):
        self.include_trading = include_trading
        self.results: List[TestResult] = []
        load_dotenv()

    def _time_it(self, func):
        """计时装饰器"""
        import time

        start = time.perf_counter()
        try:
            result = func()
            duration = (time.perf_counter() - start) * 1000
            return result, duration, None
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return None, duration, str(e)

    def _check_env(self, exchange: str) -> tuple[bool, List[str]]:
        """检查环境变量"""
        config = self.EXCHANGES.get(exchange, {})
        required = config.get("required_env", [])
        missing = [k for k in required if not os.getenv(k)]
        return len(missing) == 0, missing

    def _load_client(self, exchange: str):
        """动态加载交易所客户端"""
        config = self.EXCHANGES.get(exchange, {})
        module_name = config.get("module")
        class_name = config.get("class")

        if not module_name or not class_name:
            raise ValueError(f"Unknown exchange: {exchange}")

        import importlib

        module = importlib.import_module(module_name)
        client_class = getattr(module, class_name)
        return client_class()

    def test_connection(self, exchange: str) -> TestResult:
        """测试连接"""
        def _test():
            client = self._load_client(exchange)
            client.connect()
            return "Connected"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name="连接",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def test_price(self, exchange: str, symbol: str = None) -> TestResult:
        """测试价格查询"""
        symbol = symbol or self.DEFAULT_SYMBOL

        def _test():
            client = self._load_client(exchange)
            client.connect()
            quote = client.get_current_price(symbol)
            return f"Bid: {quote.bid:.2f}, Ask: {quote.ask:.2f}"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name=f"价格 ({symbol})",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def test_orderbook(self, exchange: str, symbol: str = None) -> TestResult:
        """测试订单簿"""
        symbol = symbol or self.DEFAULT_SYMBOL

        def _test():
            client = self._load_client(exchange)
            client.connect()
            book = client.get_orderbook(symbol, depth=5)
            return f"Bids: {len(book.bids)}, Asks: {len(book.asks)}"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name=f"订单簿 ({symbol})",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def test_balance(self, exchange: str) -> TestResult:
        """测试余额查询"""
        def _test():
            client = self._load_client(exchange)
            client.connect()
            balances = client.get_account_balances()
            if balances:
                return ", ".join([f"{b.asset}: {b.free:.4f}" for b in balances[:3]])
            return "No balances"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name="余额",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def test_positions(self, exchange: str) -> TestResult:
        """测试持仓查询"""
        def _test():
            client = self._load_client(exchange)
            client.connect()
            positions = client.get_account_positions()
            if positions:
                return f"{len(positions)} positions"
            return "No positions"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name="持仓",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def test_orders(self, exchange: str) -> TestResult:
        """测试订单查询"""
        def _test():
            client = self._load_client(exchange)
            client.connect()
            orders = client.get_active_orders()
            return f"{len(orders)} active orders"

        result, duration, error = self._time_it(_test)
        return TestResult(
            exchange=exchange,
            test_name="活跃订单",
            passed=error is None,
            duration_ms=duration,
            error=error,
            details=result,
        )

    def run_exchange_tests(self, exchange: str, symbol: str = None) -> List[TestResult]:
        """运行单个交易所的所有测试"""
        results = []

        # 检查环境变量
        has_env, missing = self._check_env(exchange)
        if not has_env:
            results.append(TestResult(
                exchange=exchange,
                test_name="环境检查",
                passed=False,
                duration_ms=0,
                error=f"Missing: {', '.join(missing)}",
            ))
            return results

        results.append(TestResult(
            exchange=exchange,
            test_name="环境检查",
            passed=True,
            duration_ms=0,
            details="All env vars present",
        ))

        # 基础测试
        results.append(self.test_connection(exchange))
        results.append(self.test_price(exchange, symbol))
        results.append(self.test_orderbook(exchange, symbol))
        results.append(self.test_balance(exchange))
        results.append(self.test_positions(exchange))
        results.append(self.test_orders(exchange))

        return results

    def run_all_tests(self, exchanges: List[str] = None, symbol: str = None) -> Dict[str, List[TestResult]]:
        """运行所有交易所测试"""
        exchanges = exchanges or list(self.EXCHANGES.keys())
        all_results = {}

        for exchange in exchanges:
            if exchange not in self.EXCHANGES:
                logger.warning(f"Unknown exchange: {exchange}")
                continue

            logger.info(f"\n{'=' * 50}")
            logger.info(f"Testing {exchange.upper()}")
            logger.info("=" * 50)

            results = self.run_exchange_tests(exchange, symbol)
            all_results[exchange] = results

            # 打印结果
            for r in results:
                status = "✅" if r.passed else "❌"
                detail = r.details or r.error or ""
                logger.info(f"  {status} {r.test_name}: {detail} ({r.duration_ms:.0f}ms)")

        return all_results

    def print_summary(self, all_results: Dict[str, List[TestResult]]):
        """打印测试汇总"""
        print("\n" + "=" * 60)
        print("📊 测试汇总")
        print("=" * 60)

        total_passed = 0
        total_failed = 0

        for exchange, results in all_results.items():
            passed = sum(1 for r in results if r.passed)
            failed = sum(1 for r in results if not r.passed)
            total_passed += passed
            total_failed += failed

            status = "✅" if failed == 0 else "⚠️" if passed > 0 else "❌"
            print(f"{status} {exchange:12} | {passed} passed, {failed} failed")

        print("-" * 60)
        print(f"总计: {total_passed} passed, {total_failed} failed")

        if total_failed == 0:
            print("\n🎉 所有测试通过！")
        else:
            print(f"\n⚠️ {total_failed} 个测试失败，请检查配置。")


def main():
    parser = argparse.ArgumentParser(description="通用交易所测试框架")
    parser.add_argument(
        "exchanges",
        nargs="*",
        help="要测试的交易所 (默认: 全部)",
    )
    parser.add_argument(
        "--symbol",
        default="ETH/USDT",
        help="测试交易对 (默认: ETH/USDT)",
    )
    parser.add_argument(
        "--trading",
        action="store_true",
        help="包含交易测试 (谨慎使用!)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有支持的交易所",
    )

    args = parser.parse_args()

    if args.list:
        print("支持的交易所:")
        for name, config in ExchangeTester.EXCHANGES.items():
            env_vars = ", ".join(config["required_env"])
            print(f"  - {name:12} | 需要: {env_vars}")
        return

    tester = ExchangeTester(include_trading=args.trading)
    results = tester.run_all_tests(args.exchanges or None, args.symbol)
    tester.print_summary(results)


if __name__ == "__main__":
    main()
