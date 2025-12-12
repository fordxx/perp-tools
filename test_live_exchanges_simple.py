#!/usr/bin/env python3
"""
交易所实盘功能测试脚本 (简化版)
不依赖 dotenv，直接从环境变量读取
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import traceback

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


class ExchangeTester:
    """交易所测试器"""

    def __init__(self):
        self.results = []
        self.exchanges_configured = []
        self._detect_exchanges()

    def _detect_exchanges(self):
        """检测已配置的交易所"""
        # 检查 OKX
        if os.getenv("OKX_API_KEY"):
            self.exchanges_configured.append("OKX")

        # 检查 Paradex
        if os.getenv("PARADEX_L2_PRIVATE_KEY"):
            self.exchanges_configured.append("Paradex")

        # 检查 Hyperliquid
        if os.getenv("HYPERLIQUID_PRIVATE_KEY"):
            self.exchanges_configured.append("Hyperliquid")

    def test_okx(self):
        """测试 OKX"""
        print(f"\n{'=' * 80}")
        print(f"Testing OKX")
        print(f"{'=' * 80}")

        try:
            from perpbot.exchanges.okx import OKXClient

            # Test 1: Connection
            print("Test 1: Connection...")
            client = OKXClient(
                api_key=os.getenv("OKX_API_KEY"),
                api_secret=os.getenv("OKX_API_SECRET"),
                passphrase=os.getenv("OKX_PASSPHRASE"),
                is_demo=True,
            )
            client.connect()
            print("✅ PASS - Connected successfully (Demo Trading mode)")

            # Test 2: Get Price
            print("\nTest 2: Get Current Price (BTC-USDT)...")
            quote = client.get_current_price("BTC-USDT")
            print(f"✅ PASS - Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: ${(quote.ask - quote.bid):.2f}")

            # Test 3: Get Balance
            print("\nTest 3: Get Account Balance...")
            balances = client.get_account_balances()
            if balances:
                usdt = next((b for b in balances if b.currency == "USDT"), None)
                if usdt:
                    print(f"✅ PASS - USDT Available: ${usdt.available:.2f}, Total: ${usdt.total:.2f}")
                else:
                    print(f"✅ PASS - Found {len(balances)} currencies")
            else:
                print("✅ PASS - No balances (empty account)")

            # Test 4: Get Positions
            print("\nTest 4: Get Active Positions...")
            positions = client.get_account_positions()
            if positions:
                print(f"✅ PASS - Found {len(positions)} active position(s)")
                for pos in positions[:3]:  # Show first 3
                    print(f"  - {pos.symbol}: {pos.side} {pos.size} @ ${pos.entry_price:.2f}")
            else:
                print("✅ PASS - No active positions")

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            traceback.print_exc()

    def test_paradex(self):
        """测试 Paradex"""
        print(f"\n{'=' * 80}")
        print(f"Testing Paradex")
        print(f"{'=' * 80}")

        try:
            from perpbot.exchanges.paradex import ParadexClient

            # Test 1: Connection
            print("Test 1: Connection...")
            client = ParadexClient(
                l2_private_key=os.getenv("PARADEX_L2_PRIVATE_KEY"),
                account_address=os.getenv("PARADEX_ACCOUNT_ADDRESS"),
                env=os.getenv("PARADEX_ENV", "testnet"),
            )
            client.connect()
            print(f"✅ PASS - Connected successfully ({client.env} mode)")

            # Test 2: Get Price
            print("\nTest 2: Get Current Price (BTC-USD-PERP)...")
            quote = client.get_current_price("BTC-USD-PERP")
            print(f"✅ PASS - Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: ${(quote.ask - quote.bid):.2f}")

            # Test 3: Get Balance
            print("\nTest 3: Get Account Balance...")
            balances = client.get_account_balances()
            if balances:
                usdc = next((b for b in balances if b.currency == "USDC"), None)
                if usdc:
                    print(f"✅ PASS - USDC Available: ${usdc.available:.2f}, Total: ${usdc.total:.2f}")
                else:
                    print(f"✅ PASS - Found {len(balances)} currencies")
            else:
                print("✅ PASS - No balances (empty account)")

            # Test 4: Get Positions
            print("\nTest 4: Get Active Positions...")
            positions = client.get_account_positions()
            if positions:
                print(f"✅ PASS - Found {len(positions)} active position(s)")
                for pos in positions[:3]:
                    print(f"  - {pos.symbol}: {pos.side} {pos.size} @ ${pos.entry_price:.2f}")
            else:
                print("✅ PASS - No active positions")

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            traceback.print_exc()

    def test_hyperliquid(self):
        """测试 Hyperliquid"""
        print(f"\n{'=' * 80}")
        print(f"Testing Hyperliquid")
        print(f"{'=' * 80}")

        try:
            from perpbot.exchanges.hyperliquid import HyperliquidClient

            # Test 1: Connection
            print("Test 1: Connection...")
            client = HyperliquidClient(
                account_address=os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS"),
                private_key=os.getenv("HYPERLIQUID_PRIVATE_KEY"),
                env=os.getenv("HYPERLIQUID_ENV", "testnet"),
            )
            client.connect()
            print(f"✅ PASS - Connected successfully ({client.env} mode)")

            # Test 2: Get Price
            print("\nTest 2: Get Current Price (BTC)...")
            quote = client.get_current_price("BTC")
            print(f"✅ PASS - Bid: ${quote.bid:.2f}, Ask: ${quote.ask:.2f}, Spread: ${(quote.ask - quote.bid):.2f}")

            # Test 3: Get Balance
            print("\nTest 3: Get Account Balance...")
            balances = client.get_account_balances()
            if balances:
                usdc = next((b for b in balances if b.currency == "USDC"), None)
                if usdc:
                    print(f"✅ PASS - USDC Available: ${usdc.available:.2f}, Total: ${usdc.total:.2f}")
                else:
                    print(f"✅ PASS - Found {len(balances)} currencies")
            else:
                print("✅ PASS - No balances (empty account)")

            # Test 4: Get Positions
            print("\nTest 4: Get Active Positions...")
            positions = client.get_account_positions()
            if positions:
                print(f"✅ PASS - Found {len(positions)} active position(s)")
                for pos in positions[:3]:
                    print(f"  - {pos.symbol}: {pos.side} {pos.size} @ ${pos.entry_price:.2f}")
            else:
                print("✅ PASS - No active positions")

        except Exception as e:
            print(f"❌ FAIL - Error: {str(e)}")
            traceback.print_exc()

    def run_all_tests(self):
        """运行所有测试"""
        print(f"\n{'=' * 80}")
        print(f"Live Exchange Function Testing (Simple Mode)")
        print(f"{'=' * 80}")
        print(f"Mode: ✅ READ-ONLY (Safe - No Trading)")
        print(f"Configured Exchanges: {', '.join(self.exchanges_configured) if self.exchanges_configured else 'None'}")
        print(f"Started: {datetime.utcnow().isoformat()}")
        print(f"{'=' * 80}")

        if not self.exchanges_configured:
            print("\n❌ No exchanges configured!")
            print("Please set environment variables for at least one exchange.")
            print("\nExample for OKX:")
            print("  export OKX_API_KEY=your_key")
            print("  export OKX_API_SECRET=your_secret")
            print("  export OKX_PASSPHRASE=your_passphrase")
            return

        # 运行测试
        if "OKX" in self.exchanges_configured:
            self.test_okx()

        if "Paradex" in self.exchanges_configured:
            self.test_paradex()

        if "Hyperliquid" in self.exchanges_configured:
            self.test_hyperliquid()

        print(f"\n{'=' * 80}")
        print(f"Testing Complete")
        print(f"{'=' * 80}\n")


def main():
    tester = ExchangeTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
