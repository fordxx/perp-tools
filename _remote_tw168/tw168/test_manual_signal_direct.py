#!/usr/bin/env python3
"""
Direct code test for manual signal functionality
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

async def test_manual_signal_direct():
    """Test the manual signal functionality directly without HTTP"""

    # Import the necessary modules
    try:
        from app.main import ManualSignalRequest, _process_payload
        from app.config import SETTINGS
        print("✅ Successfully imported app modules")
    except Exception as e:
        print(f"❌ Failed to import app modules: {e}")
        return False

    # Check admin key
    admin_key = os.getenv("TV_WEBHOOK_SECRET", "CHANGE_ME")
    if admin_key == "CHANGE_ME":
        print("❌ TV_WEBHOOK_SECRET not set properly")
        return False

    print(f"🔑 Admin key loaded: {admin_key[:10]}...")
    print(f"📊 Current SETTINGS.paper_trade_tfs: {SETTINGS.paper_trade_tfs}")
    print(f"📊 Current SETTINGS.trading_enabled: {SETTINGS.trading_enabled}")
    print(f"📊 Current SETTINGS.rsi_filter_enabled: {SETTINGS.rsi_filter_enabled}")

    # Create test request - use paper trade timeframe to avoid RSI filtering
    test_request = ManualSignalRequest(
        instId="ETH-USDT-SWAP",
        tf="1m",  # Use 1m which should be in paper_trade_tfs
        side="long",
        type="DIV",
        admin_key=admin_key
    )

    print("📦 Test request created:")
    print(f"  - instId: {test_request.instId}")
    print(f"  - tf: {test_request.tf}")
    print(f"  - side: {test_request.side}")
    print(f"  - type: {test_request.type}")

    # Construct TvPayload from ManualSignalRequest (like the endpoint does)
    from datetime import datetime
    from app.main import TvPayload

    payload = TvPayload(
        secret=SETTINGS.tv_webhook_secret,
        type=test_request.type,
        instId=test_request.instId,
        tf=test_request.tf,
        side=test_request.side,
        t=datetime.utcnow().isoformat() + "Z",
        close=None,  # 让系统自动获取最新价格
        zone=None
    )

    print("🔄 Constructed TvPayload for processing...")

    # Test payload processing
    try:
        print("🔄 Processing payload...")
        result = await _process_payload(payload, allow_no_zone=True)

        print("📊 Processing result:")
        print(f"  - ok: {result.get('ok')}")
        print(f"  - skipped: {result.get('skipped', 'N/A')}")
        print(f"  - error: {result.get('error', 'N/A')}")

        if result.get("ok"):
            print("✅ Signal processed successfully")
            if result.get("skipped"):
                print(f"⚠️  Signal was skipped: {result.get('skipped')}")
            return True
        else:
            print(f"❌ Signal processing failed: {result.get('error', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"❌ Payload processing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("🧪 Testing manual signal functionality directly...")
    success = await test_manual_signal_direct()
    print(f"{'✅' if success else '❌'} Test {'PASSED' if success else 'FAILED'}")
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)