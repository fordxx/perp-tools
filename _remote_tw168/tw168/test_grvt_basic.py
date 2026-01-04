#!/usr/bin/env python3
"""Test script for GRVT exchange client."""

import asyncio
import os
import sys
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.grvt import GrvtClient, GrvtCredentials


async def test_grvt_client():
    """Test basic GRVT client functionality."""
    print("Testing GRVT client...")

    # Get credentials from environment
    api_key = os.getenv("GRVT_API_KEY", "")
    private_key = os.getenv("GRVT_PRIVATE_KEY", "")
    trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID", "")
    base_url = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

    if not all([api_key, private_key, trading_account_id]):
        print("❌ Missing GRVT credentials. Please set:")
        print("  GRVT_API_KEY")
        print("  GRVT_PRIVATE_KEY")
        print("  GRVT_TRADING_ACCOUNT_ID")
        return

    creds = GrvtCredentials(
        api_key=api_key,
        private_key=private_key,
        trading_account_id=trading_account_id,
    )

    client = GrvtClient(base_url, creds)

    try:
        # Test connection
        print("🔗 Connecting to GRVT...")
        await client.connect()
        print("✅ Connected successfully")

        # Test getting instrument info
        print("📊 Testing instrument info...")
        inst_id = "BTC-USDT-SWAP"
        info = await client.get_instrument_info(inst_id=inst_id)
        if info:
            print(f"✅ Instrument info for {inst_id}: {info}")
        else:
            print(f"❌ Failed to get instrument info for {inst_id}")

        # Test getting last price
        print("💰 Testing last price...")
        price = await client.get_last_price(inst_id=inst_id)
        if price:
            print(f"✅ Last price for {inst_id}: {price}")
        else:
            print(f"❌ Failed to get last price for {inst_id}")

        # Test getting positions (should be empty for new account)
        print("📈 Testing positions...")
        pos = await client.get_position(inst_id=inst_id, pos_side="long")
        if pos is None:
            print("✅ No position found (expected for new account)")
        else:
            print(f"📊 Position found: {pos}")

        # Test getting open orders (should be empty)
        print("📋 Testing open orders...")
        orders = await client.get_open_orders(inst_id=inst_id)
        print(f"✅ Open orders count: {len(orders)}")

        print("🎉 All basic tests passed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test_grvt_client())