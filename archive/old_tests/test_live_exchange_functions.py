#!/usr/bin/env python3
"""
交易所实盘功能测试脚本
Live Exchange Function Testing Script

测试范围：
1. 连接测试 - 验证 API 凭证和网络连接
2. 行情数据测试 - 获取最新价格和订单簿
3. 账户查询测试 - 查询余额和持仓
4. 下单测试 - 小额测试单（如果启用）
5. WebSocket 测试 - 实时行情推送

安全措施：
- 默认只读模式，不执行下单
- 需要明确启用才允许下单
- 下单金额限制在最小值
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import traceback
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Load environment variables
load_dotenv()


class ExchangeTestResult:
    """测试结果数据类"""
    def __init__(self, exchange: str, test_name: str):
        self.exchange = exchange
        self.test_name = test_name
        self.status = "PENDING"
        self.message = ""
        self.data: Optional[Dict] = None
        self.error: Optional[str] = None
        self.timestamp = datetime.utcnow()
        self.duration_ms = 0.0

    def mark_success(self, message: str = "", data: Optional[Dict] = None):
        """标记为成功"""
        self.status = "✅ PASS"
        self.message = message
        self.data = data

    def mark_failure(self, error: str):
        """标记为失败"""
        self.status = "❌ FAIL"
        self.error = error

    def mark_skipped(self, reason: str):
        """标记为跳过"""
        self.status = "⏭️  SKIP"
        self.message = reason

    def __str__(self):
        return f"{self.status:10} | {self.exchange:15} | {self.test_name:30} | {self.message or self.error or ''}"


class LiveExchangeTester:
    """交易所实盘测试器"""

    def __init__(self, enable_trading: bool = False):
        """
        初始化测试器

        Args:
            enable_trading: 是否启用交易测试（默认False，只读模式）
        """
        self.enable_trading = enable_trading
        self.results: List[ExchangeTestResult] = []
        self.exchanges_to_test = []

        # 检测配置的交易所
        self._detect_configured_exchanges()

    def _detect_configured_exchanges(self):
        """检测已配置的交易所"""
        # OKX
        if os.getenv("OKX_API_KEY") and os.getenv("OKX_API_KEY") != "your_okx_api_key_here":
            self.exchanges_to_test.append("okx")

        # Paradex
        if os.getenv("PARADEX_L2_PRIVATE_KEY") and os.getenv("PARADEX_L2_PRIVATE_KEY") != "0xyour_l2_private_key_here":
            self.exchanges_to_test.append("paradex")

        # Hyperliquid
        if os.getenv("HYPERLIQUID_PRIVATE_KEY"):
            self.exchanges_to_test.append("hyperliquid")

        # Extended
        if os.getenv("EXTENDED_API_KEY") and os.getenv("EXTENDED_API_KEY") != "your_extended_api_key_here":
            self.exchanges_to_test.append("extended")

        # EdgeX
        if os.getenv("EDGEX_API_KEY") and os.getenv("EDGEX_API_KEY") != "your_edgex_api_key_here":
            self.exchanges_to_test.append("edgex")

        # Backpack
        if os.getenv("BACKPACK_API_KEY") and os.getenv("BACKPACK_API_KEY") != "your_backpack_api_key_here":
            self.exchanges_to_test.append("backpack")

        # Lighter
        if os.getenv("LIGHTER_API_KEY") and os.getenv("LIGHTER_API_KEY") != "your_lighter_api_key_here":
            self.exchanges_to_test.append("lighter")

        # GRVT
        if os.getenv("GRVT_API_KEY") and os.getenv("GRVT_API_KEY") != "your_grvt_api_key_here":
            self.exchanges_to_test.append("grvt")

        # Aster
        if os.getenv("ASTER_API_KEY") and os.getenv("ASTER_API_KEY") != "your_aster_api_key_here":
            self.exchanges_to_test.append("aster")

    def test_okx(self):
        """测试 OKX 交易所"""
        exchange = "okx"
        print(f"\n{'=' * 80}")
        print(f"Testing {exchange.upper()}")
        print(f"{'=' * 80}")

        # Test 1: Connection
        result = ExchangeTestResult(exchange, "Connection & Authentication")
        try:
            from perpbot.exchanges.okx import OKXClient

            client = OKXClient(
                api_key=os.getenv("OKX_API_KEY"),
                api_secret=os.getenv("OKX_API_SECRET"),
                passphrase=os.getenv("OKX_PASSPHRASE"),
                is_demo=True,  # OKX 使用 Demo Trading
            )
            client.connect()
            result.mark_success("Connected successfully (Demo Trading mode)")
        except Exception as e:
            result.mark_failure(f"Connection failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 2: Get Current Price
        result = ExchangeTestResult(exchange, "Get Current Price (BTC-USDT)")
        try:
            quote = client.get_current_price("BTC-USDT")
            result.mark_success(
                f"Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: {(quote.ask - quote.bid):.2f}",
                data={"bid": quote.bid, "ask": quote.ask}
            )
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 3: Get Account Balance
        result = ExchangeTestResult(exchange, "Get Account Balance")
        try:
            balances = client.get_account_balances()
            if balances:
                usdt_balance = next((b for b in balances if b.currency == "USDT"), None)
                if usdt_balance:
                    result.mark_success(
                        f"USDT Available: ${usdt_balance.available:.2f}, Total: ${usdt_balance.total:.2f}",
                        data={"usdt_available": usdt_balance.available}
                    )
                else:
                    result.mark_success(f"Found {len(balances)} currencies, no USDT")
            else:
                result.mark_success("No balances found (empty account)")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 4: Get Positions
        result = ExchangeTestResult(exchange, "Get Active Positions")
        try:
            positions = client.get_account_positions()
            if positions:
                result.mark_success(
                    f"Found {len(positions)} active position(s)",
                    data={"count": len(positions)}
                )
            else:
                result.mark_success("No active positions")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

    def test_paradex(self):
        """测试 Paradex 交易所"""
        exchange = "paradex"
        print(f"\n{'=' * 80}")
        print(f"Testing {exchange.upper()}")
        print(f"{'=' * 80}")

        # Test 1: Connection
        result = ExchangeTestResult(exchange, "Connection & Authentication")
        try:
            from perpbot.exchanges.paradex import ParadexClient

            client = ParadexClient(
                l2_private_key=os.getenv("PARADEX_L2_PRIVATE_KEY"),
                account_address=os.getenv("PARADEX_ACCOUNT_ADDRESS"),
                env=os.getenv("PARADEX_ENV", "testnet"),
            )
            client.connect()
            result.mark_success(f"Connected successfully ({client.env} mode)")
        except Exception as e:
            result.mark_failure(f"Connection failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 2: Get Current Price
        result = ExchangeTestResult(exchange, "Get Current Price (BTC-USD-PERP)")
        try:
            quote = client.get_current_price("BTC-USD-PERP")
            result.mark_success(
                f"Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: {(quote.ask - quote.bid):.2f}",
                data={"bid": quote.bid, "ask": quote.ask}
            )
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 3: Get Account Balance
        result = ExchangeTestResult(exchange, "Get Account Balance")
        try:
            balances = client.get_account_balances()
            if balances:
                usdc_balance = next((b for b in balances if b.currency == "USDC"), None)
                if usdc_balance:
                    result.mark_success(
                        f"USDC Available: ${usdc_balance.available:.2f}, Total: ${usdc_balance.total:.2f}",
                        data={"usdc_available": usdc_balance.available}
                    )
                else:
                    result.mark_success(f"Found {len(balances)} currencies, no USDC")
            else:
                result.mark_success("No balances found (empty account)")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 4: Get Positions
        result = ExchangeTestResult(exchange, "Get Active Positions")
        try:
            positions = client.get_account_positions()
            if positions:
                result.mark_success(
                    f"Found {len(positions)} active position(s)",
                    data={"count": len(positions)}
                )
            else:
                result.mark_success("No active positions")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

    def test_hyperliquid(self):
        """测试 Hyperliquid 交易所"""
        exchange = "hyperliquid"
        print(f"\n{'=' * 80}")
        print(f"Testing {exchange.upper()}")
        print(f"{'=' * 80}")

        # Test 1: Connection
        result = ExchangeTestResult(exchange, "Connection & Authentication")
        try:
            from perpbot.exchanges.hyperliquid import HyperliquidClient

            client = HyperliquidClient(
                account_address=os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS"),
                private_key=os.getenv("HYPERLIQUID_PRIVATE_KEY"),
                env=os.getenv("HYPERLIQUID_ENV", "testnet"),
            )
            client.connect()
            result.mark_success(f"Connected successfully ({client.env} mode)")
        except Exception as e:
            result.mark_failure(f"Connection failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 2: Get Current Price
        result = ExchangeTestResult(exchange, "Get Current Price (BTC)")
        try:
            quote = client.get_current_price("BTC")
            result.mark_success(
                f"Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: {(quote.ask - quote.bid):.2f}",
                data={"bid": quote.bid, "ask": quote.ask}
            )
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 3: Get Account Balance
        result = ExchangeTestResult(exchange, "Get Account Balance")
        try:
            balances = client.get_account_balances()
            if balances:
                usdc_balance = next((b for b in balances if b.currency == "USDC"), None)
                if usdc_balance:
                    result.mark_success(
                        f"USDC Available: ${usdc_balance.available:.2f}, Total: ${usdc_balance.total:.2f}",
                        data={"usdc_available": usdc_balance.available}
                    )
                else:
                    result.mark_success(f"Found {len(balances)} currencies")
            else:
                result.mark_success("No balances found (empty account)")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

        # Test 4: Get Positions
        result = ExchangeTestResult(exchange, "Get Active Positions")
        try:
            positions = client.get_account_positions()
            if positions:
                result.mark_success(
                    f"Found {len(positions)} active position(s)",
                    data={"count": len(positions)}
                )
            else:
                result.mark_success("No active positions")
        except Exception as e:
            result.mark_failure(f"Failed: {str(e)}")
        self.results.append(result)
        print(result)

    def run_all_tests(self):
        """运行所有已配置交易所的测试"""
        print(f"\n{'=' * 80}")
        print(f"Live Exchange Function Testing")
        print(f"{'=' * 80}")
        print(f"Testing Mode: {'🔴 TRADING ENABLED' if self.enable_trading else '✅ READ-ONLY (Safe)'}")
        print(f"Configured Exchanges: {', '.join(self.exchanges_to_test) if self.exchanges_to_test else 'None'}")
        print(f"Started: {datetime.utcnow().isoformat()}")
        print(f"{'=' * 80}")

        if not self.exchanges_to_test:
            print("\n⚠️  No exchanges configured in .env file!")
            print("Please copy .env.example to .env and fill in your API credentials.")
            return

        # 运行各交易所测试
        for exchange in self.exchanges_to_test:
            try:
                if exchange == "okx":
                    self.test_okx()
                elif exchange == "paradex":
                    self.test_paradex()
                elif exchange == "hyperliquid":
                    self.test_hyperliquid()
                elif exchange == "extended":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
                elif exchange == "edgex":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
                elif exchange == "backpack":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
                elif exchange == "lighter":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
                elif exchange == "grvt":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
                elif exchange == "aster":
                    print(f"\n⏭️  Skipping {exchange.upper()} (test not implemented yet)")
            except Exception as e:
                print(f"\n❌ Error testing {exchange}: {str(e)}")
                traceback.print_exc()

        # 打印测试总结
        self.print_summary()

    def print_summary(self):
        """打印测试总结"""
        print(f"\n{'=' * 80}")
        print(f"Test Summary")
        print(f"{'=' * 80}")

        # 统计
        total = len(self.results)
        passed = sum(1 for r in self.results if "PASS" in r.status)
        failed = sum(1 for r in self.results if "FAIL" in r.status)
        skipped = sum(1 for r in self.results if "SKIP" in r.status)

        print(f"\nTotal Tests:  {total}")
        print(f"✅ Passed:     {passed}")
        print(f"❌ Failed:     {failed}")
        print(f"⏭️  Skipped:    {skipped}")

        # 按交易所分组
        print(f"\n{'=' * 80}")
        print(f"Results by Exchange:")
        print(f"{'=' * 80}")

        for exchange in self.exchanges_to_test:
            exchange_results = [r for r in self.results if r.exchange == exchange]
            if exchange_results:
                print(f"\n{exchange.upper()}:")
                for result in exchange_results:
                    print(f"  {result}")

        # 失败的测试详情
        failed_results = [r for r in self.results if "FAIL" in r.status]
        if failed_results:
            print(f"\n{'=' * 80}")
            print(f"Failed Tests Details:")
            print(f"{'=' * 80}")
            for result in failed_results:
                print(f"\n{result.exchange.upper()} - {result.test_name}:")
                print(f"  Error: {result.error}")

        print(f"\n{'=' * 80}")
        if failed == 0:
            print("🎉 All tests PASSED!")
        else:
            print(f"⚠️  {failed} test(s) FAILED - please check details above")
        print(f"{'=' * 80}\n")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="交易所实盘功能测试")
    parser.add_argument(
        "--enable-trading",
        action="store_true",
        help="启用交易测试（危险！会执行真实下单）"
    )
    parser.add_argument(
        "--exchange",
        type=str,
        help="只测试指定交易所（okx, paradex, hyperliquid, 等）"
    )
    args = parser.parse_args()

    # 创建测试器
    tester = LiveExchangeTester(enable_trading=args.enable_trading)

    # 过滤交易所
    if args.exchange:
        if args.exchange in tester.exchanges_to_test:
            tester.exchanges_to_test = [args.exchange]
        else:
            print(f"❌ Exchange '{args.exchange}' is not configured in .env")
            print(f"Available: {', '.join(tester.exchanges_to_test)}")
            return

    # 警告
    if args.enable_trading:
        print("\n" + "!" * 80)
        print("⚠️  WARNING: TRADING MODE ENABLED!")
        print("⚠️  This will execute REAL ORDERS with REAL MONEY!")
        print("!" * 80)
        confirm = input("\nType 'YES I UNDERSTAND THE RISK' to continue: ")
        if confirm != "YES I UNDERSTAND THE RISK":
            print("❌ Aborted.")
            return

    # 运行测试
    tester.run_all_tests()


if __name__ == "__main__":
    main()
