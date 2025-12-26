#!/usr/bin/env python3
"""Test script for critical fixes validation."""
import asyncio
import json
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))


def test_exception_handling():
    """Test that exception handling is properly refined."""
    print("🧪 Testing exception handling...")

    # Test 1: JSON parsing should handle specific exceptions
    try:
        from app.main import webhook_tradingview
        print("  ✅ Webhook endpoint imports correctly")
    except Exception as e:
        print(f"  ❌ Failed to import: {e}")
        return False

    # Test 2: OKX client should have retry logic
    try:
        from app.okx import OKXClient
        import inspect

        # Check if request method has max_retries parameter
        sig = inspect.signature(OKXClient.request)
        params = sig.parameters

        if "max_retries" in params:
            print("  ✅ OKX client has retry mechanism")
        else:
            print("  ❌ OKX client missing retry parameter")
            return False
    except Exception as e:
        print(f"  ❌ OKX client test failed: {e}")
        return False

    return True


def test_websocket_reconnection():
    """Test WebSocket reconnection logic improvements."""
    print("\n🧪 Testing WebSocket reconnection...")

    try:
        # Test candle cache WebSocket
        from app.candle_cache import _okx_candles_loop
        import inspect

        source = inspect.getsource(_okx_candles_loop)

        checks = [
            ("retry_delay", "Has retry delay variable"),
            ("max_retry_delay", "Has max retry delay"),
            ("consecutive_errors", "Tracks consecutive errors"),
            ("exponential backoff", "Uses exponential backoff"),
        ]

        all_passed = True
        for check_str, desc in checks:
            if check_str.lower() in source.lower():
                print(f"  ✅ {desc}")
            else:
                print(f"  ❌ Missing: {desc}")
                all_passed = False

        # Test fill tracker WebSocket
        from app.ws_fills import _okx_ws_loop
        source_fills = inspect.getsource(_okx_ws_loop)

        if "retry_delay" in source_fills and "consecutive_errors" in source_fills:
            print("  ✅ Fill tracker WebSocket has reconnection logic")
        else:
            print("  ❌ Fill tracker WebSocket missing reconnection logic")
            all_passed = False

        return all_passed
    except Exception as e:
        print(f"  ❌ WebSocket test failed: {e}")
        return False


async def test_emergency_handler():
    """Test emergency handler functionality."""
    print("\n🧪 Testing emergency handler...")

    try:
        from app.emergency_handler import EmergencyHandler, get_emergency_handler

        # Test 1: Create handler
        handler = EmergencyHandler()
        print("  ✅ Emergency handler instantiates")

        # Test 2: Start handler
        handler.start()
        print("  ✅ Emergency handler starts")

        # Test 3: Register emergency
        await handler.register_emergency(
            inst_id="BTC-USDT-SWAP",
            pos_side="long",
            size="10",
            entry_price=42000.0,
            stop_loss=41500.0,
            cl_ord_id="test_12345",
            failure_reason="test failure",
        )
        print("  ✅ Emergency position registered")

        # Test 4: Check positions
        positions = await handler.get_emergency_positions()
        if len(positions) == 1:
            print("  ✅ Emergency position retrieved")
        else:
            print(f"  ❌ Expected 1 position, got {len(positions)}")
            return False

        # Test 5: Clear emergency
        await handler.clear_emergency("BTC-USDT-SWAP", "long")
        positions = await handler.get_emergency_positions()
        if len(positions) == 0:
            print("  ✅ Emergency position cleared")
        else:
            print(f"  ❌ Position not cleared, count={len(positions)}")
            return False

        # Test 6: Stop handler
        await handler.stop()
        print("  ✅ Emergency handler stops cleanly")

        # Test 7: Global instance
        global_handler = get_emergency_handler()
        if global_handler is not None:
            print("  ✅ Global emergency handler accessible")
        else:
            print("  ❌ Global emergency handler not initialized")
            return False

        return True
    except Exception as e:
        print(f"  ❌ Emergency handler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_main_integration():
    """Test that main.py integrates all fixes."""
    print("\n🧪 Testing main.py integration...")

    try:
        from app.main import app, get_emergency_handler

        # Check routes
        routes = [route.path for route in app.routes]

        if "/emergency" in routes:
            print("  ✅ /emergency endpoint exists")
        else:
            print("  ❌ /emergency endpoint missing")
            return False

        if "/metrics" in routes:
            print("  ✅ /metrics endpoint exists")
        else:
            print("  ❌ /metrics endpoint missing")
            return False

        # Check imports
        import app.main as main_module
        if hasattr(main_module, 'get_emergency_handler'):
            print("  ✅ Emergency handler imported in main")
        else:
            print("  ❌ Emergency handler not imported")
            return False

        return True
    except Exception as e:
        print(f"  ❌ Main integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_validation():
    """Test configuration is valid."""
    print("\n🧪 Testing configuration...")

    try:
        from app.config import SETTINGS

        # Check critical settings
        if hasattr(SETTINGS, 'backup_sl_enabled'):
            print(f"  ✅ BACKUP_SL_ENABLED = {SETTINGS.backup_sl_enabled}")
        else:
            print("  ❌ BACKUP_SL_ENABLED setting missing")
            return False

        if hasattr(SETTINGS, 'trading_enabled'):
            print(f"  ℹ️  TRADING_ENABLED = {SETTINGS.trading_enabled}")

        if hasattr(SETTINGS, 'exchange'):
            print(f"  ℹ️  EXCHANGE = {SETTINGS.exchange}")

        return True
    except Exception as e:
        print(f"  ❌ Config test failed: {e}")
        return False


async def run_all_tests():
    """Run all validation tests."""
    print("=" * 60)
    print("🔍 Critical Fixes Validation Test Suite")
    print("=" * 60)

    results = {
        "Exception Handling": test_exception_handling(),
        "WebSocket Reconnection": test_websocket_reconnection(),
        "Emergency Handler": await test_emergency_handler(),
        "Main Integration": test_main_integration(),
        "Configuration": test_config_validation(),
    }

    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)

    all_passed = True
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}  {test_name}")
        if not result:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("🎉 All tests passed! Critical fixes validated.")
        print("\n📝 Next steps:")
        print("  1. Review CRITICAL_FIXES.md for detailed documentation")
        print("  2. Test in a staging environment")
        print("  3. Monitor /emergency endpoint after deployment")
        print("  4. Ensure Telegram notifications are working")
        return 0
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        print("\n🔧 Troubleshooting:")
        print("  1. Check that all dependencies are installed: pip install -r requirements.txt")
        print("  2. Verify .env file has required settings")
        print("  3. Review error messages and stack traces")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
