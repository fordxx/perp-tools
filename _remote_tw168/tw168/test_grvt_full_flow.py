#!/usr/bin/env python3
"""
Complete GRVT trading flow test script.

This script demonstrates the full GRVT trading workflow including:
- Connection and authentication
- Market data retrieval
- Order placement (market/limit)
- Position management
- Stop-loss and take-profit orders
- Order cancellation

Before running, set your GRVT credentials in environment variables:
export GRVT_API_KEY="your_api_key"
export GRVT_PRIVATE_KEY="your_private_key"
export GRVT_TRADING_ACCOUNT_ID="your_trading_account_id"
export GRVT_BASE_URL="https://api.grvt.io"  # or testnet URL
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent / "app"))

from app.grvt import GrvtClient, GrvtCredentials


async def test_grvt_full_flow():
    """Test the complete GRVT trading flow."""
    print("🚀 Testing complete GRVT trading flow...")

    # Get credentials from environment
    api_key = os.getenv("GRVT_API_KEY", "")
    private_key = os.getenv("GRVT_PRIVATE_KEY", "")
    trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID", "")
    base_url = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

    if not all([api_key, private_key, trading_account_id]):
        print("❌ Missing GRVT credentials. Please set environment variables:")
        print("  export GRVT_API_KEY='your_api_key'")
        print("  export GRVT_PRIVATE_KEY='your_private_key'")
        print("  export GRVT_TRADING_ACCOUNT_ID='your_trading_account_id'")
        print("  export GRVT_BASE_URL='https://api.grvt.io'")
        print("\n📖 Get your credentials from: https://app.grvt.io/")
        return

    creds = GrvtCredentials(
        api_key=api_key,
        private_key=private_key,
        trading_account_id=trading_account_id,
    )

    client = GrvtClient(base_url, creds)

    try:
        # 1. Test connection
        print("🔗 Step 1: Connecting to GRVT...")
        await client.connect()
        print("✅ Connected successfully")

        # 2. Test market data
        print("📊 Step 2: Testing market data...")
        inst_id = "BTC-USDT-SWAP"
        price = await client.get_last_price(inst_id=inst_id)
        if price:
            print(f"✅ Last price for {inst_id}: ${price:.2f}")
        else:
            print(f"❌ Failed to get last price for {inst_id}")
            return

        # 3. Test instrument info
        print("ℹ️  Step 3: Testing instrument info...")
        info = await client.get_instrument_info(inst_id=inst_id)
        if info:
            print(f"✅ Instrument info: {info}")
        else:
            print(f"❌ Failed to get instrument info for {inst_id}")

        # 4. Test positions (should be empty)
        print("📈 Step 4: Testing positions...")
        pos = await client.get_position(inst_id=inst_id, pos_side="long")
        if pos is None:
            print("✅ No position found (expected)")
        else:
            print(f"📊 Existing position: {pos}")

        # 5. Test open orders (should be empty)
        print("📋 Step 5: Testing open orders...")
        orders = await client.get_open_orders(inst_id=inst_id)
        print(f"✅ Open orders count: {len(orders)}")

        print("🎉 All basic tests passed!")
        print("\n📝 To test full trading flow:")
        print("1. Ensure you have sufficient balance in your GRVT account")
        print("2. Uncomment the trading test sections below")
        print("3. Run the script again")

        # Uncomment below for actual trading tests (USE WITH CAUTION!)
        """
        # 6. Test market order placement (SMALL TEST ORDER)
        print("⚠️  Step 6: Testing market order (SMALL TEST - 0.001 BTC)...")
        test_sz = "0.001"  # Very small test order

        order_resp = await client.place_order(
            inst_id=inst_id,
            td_mode="cross",
            side="buy",
            pos_side="long",
            ord_type="market",
            sz=test_sz,
            px=None,
            cl_ord_id="test_market_buy",
            sl_trigger_px=None,
            tp_trigger_px=None,
            reduce_only=False,
        )

        if "code" in order_resp and str(order_resp["code"]) == "0":
            print(f"✅ Market order placed: {order_resp}")
            order_id = order_resp.get("data", [{}])[0].get("ordId")

            # Wait a moment for order to fill
            await asyncio.sleep(2)

            # Check position
            pos = await client.get_position(inst_id=inst_id, pos_side="long")
            if pos and float(pos.get("pos", "0")) > 0:
                print(f"✅ Position opened: {pos}")

                # 7. Test stop-loss order
                print("🛡️  Step 7: Testing stop-loss order...")
                sl_price = price * 0.98  # 2% stop loss

                sl_resp = await client.place_algo_order(
                    inst_id=inst_id,
                    td_mode="cross",
                    side="sell",
                    pos_side="long",
                    ord_type="conditional",
                    sz=str(pos["pos"]),
                    sl_trigger_px=str(sl_price),
                    sl_ord_px="-1",  # Market order
                )

                if "code" in sl_resp and str(sl_resp["code"]) == "0":
                    print(f"✅ Stop-loss order placed at ${sl_price:.2f}")
                else:
                    print(f"❌ Stop-loss order failed: {sl_resp}")

                # 8. Test take-profit order
                print("💰 Step 8: Testing take-profit order...")
                tp_price = price * 1.02  # 2% take profit

                tp_resp = await client.place_algo_order(
                    inst_id=inst_id,
                    td_mode="cross",
                    side="sell",
                    pos_side="long",
                    ord_type="conditional",
                    sz=str(pos["pos"]),
                    tp_trigger_px=str(tp_price),
                    tp_ord_px="-1",  # Market order
                )

                if "code" in tp_resp and str(tp_resp["code"]) == "0":
                    print(f"✅ Take-profit order placed at ${tp_price:.2f}")
                else:
                    print(f"❌ Take-profit order failed: {tp_resp}")

                # 9. Close position (cleanup)
                print("🔄 Step 9: Closing test position...")
                close_resp = await client.place_order(
                    inst_id=inst_id,
                    td_mode="cross",
                    side="sell",
                    pos_side="long",
                    ord_type="market",
                    sz=str(pos["pos"]),
                    px=None,
                    cl_ord_id="test_close",
                    sl_trigger_px=None,
                    tp_trigger_px=None,
                    reduce_only=True,
                )

                if "code" in close_resp and str(close_resp["code"]) == "0":
                    print("✅ Position closed successfully")
                else:
                    print(f"❌ Position close failed: {close_resp}")

            else:
                print("❌ Position not found after order placement")

        else:
            print(f"❌ Market order failed: {order_resp}")
        """

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test_grvt_full_flow())