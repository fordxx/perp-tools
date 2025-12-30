#!/usr/bin/env python3
"""Test OKX trading flow: ladder orders → SL/TP → close position (simplified version)."""

import sys
import time
import asyncio
import os
from decimal import Decimal

# Add app to path
sys.path.insert(0, '/app')

from app.okx import OKXClient, OKXCredentials

# Test parameters
TEST_SYMBOL = "ONDO-USDT-SWAP"
TEST_SIDE = "buy"  # buy (long) or sell (short)
TEST_POS_SIDE = "long"  # long or short
TEST_RISK_USDT = 5.0  # Very small risk for testing: $5
STOP_LOSS_BPS = 50  # 0.5% stop loss

# Ladder order settings (hardcoded, no dependency on SETTINGS)
LADDER_LEVEL1_BPS = 5      # 0.05%
LADDER_LEVEL1_PCT = 0.50   # 50%
LADDER_LEVEL2_BPS = 15     # 0.15%
LADDER_LEVEL2_PCT = 0.30   # 30%
LADDER_LEVEL3_BPS = 30     # 0.30%
LADDER_LEVEL3_PCT = 0.20   # 20%

# TP settings
TP1_R = 1.5
TP1_PCT = 0.70
TP2_R = 2.0
TP2_PCT = 0.15
TP3_R = 2.5
TP3_PCT = 0.10
TP4_R = 3.5
TP4_PCT = 0.05


def main():
    print("=" * 80)
    print("OKX Trading Flow Test - Ladder Orders + SL/TP + Close")
    print("=" * 80)

    # Get OKX credentials from environment
    OKX_API_KEY = os.getenv("OKX_API_KEY")
    OKX_API_SECRET = os.getenv("OKX_API_SECRET")
    OKX_API_PASSPHRASE = os.getenv("OKX_API_PASSPHRASE")
    OKX_BASE_URL = os.getenv("OKX_BASE_URL", "https://www.okx.com")
    OKX_TD_MODE = os.getenv("OKX_TD_MODE", "cross")

    if not all([OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE]):
        print("❌ Missing OKX credentials in environment")
        return

    # Initialize OKX client
    creds = OKXCredentials(
        api_key=OKX_API_KEY,
        api_secret=OKX_API_SECRET,
        passphrase=OKX_API_PASSPHRASE,
    )
    okx = OKXClient(base_url=OKX_BASE_URL, creds=creds)

    # Step 1: Get current market price
    print("\n📊 Step 1: Get Market Price")
    print("-" * 80)

    last_price = okx.get_last_price(inst_id=TEST_SYMBOL)
    if not last_price:
        print("❌ Failed to get market price")
        return

    print(f"Current price: {last_price:.4f}")

    # Step 2: Calculate position size based on risk
    print("\n📐 Step 2: Calculate Position Size")
    print("-" * 80)

    # Calculate stop loss price (0.5% away)
    if TEST_SIDE == "buy":
        sl_price = last_price * (1 - STOP_LOSS_BPS / 10000)
    else:
        sl_price = last_price * (1 + STOP_LOSS_BPS / 10000)

    r_value = abs(last_price - sl_price)
    total_contracts = int(TEST_RISK_USDT / r_value)

    print(f"Entry price: {last_price:.4f}")
    print(f"Stop loss: {sl_price:.4f}")
    print(f"R-value: {r_value:.4f}")
    print(f"Total contracts: {total_contracts}")
    print(f"Max risk: ${total_contracts * r_value:.2f}")

    if total_contracts < 1:
        print("❌ Position too small for testing")
        return

    # Step 3: Calculate ladder order levels
    print("\n📋 Step 3: Calculate Ladder Orders")
    print("-" * 80)

    # Calculate prices
    if TEST_SIDE == "buy":
        level1_px = last_price * (1 - LADDER_LEVEL1_BPS / 10000)
        level2_px = last_price * (1 - LADDER_LEVEL2_BPS / 10000)
        level3_px = last_price * (1 - LADDER_LEVEL3_BPS / 10000)
    else:
        level1_px = last_price * (1 + LADDER_LEVEL1_BPS / 10000)
        level2_px = last_price * (1 + LADDER_LEVEL2_BPS / 10000)
        level3_px = last_price * (1 + LADDER_LEVEL3_BPS / 10000)

    # Calculate sizes
    level1_sz = int(total_contracts * LADDER_LEVEL1_PCT)
    level2_sz = int(total_contracts * LADDER_LEVEL2_PCT)
    level3_sz = total_contracts - level1_sz - level2_sz

    print(f"Level 1: {level1_sz} contracts @ {level1_px:.4f} ({LADDER_LEVEL1_PCT:.0%})")
    print(f"Level 2: {level2_sz} contracts @ {level2_px:.4f} ({LADDER_LEVEL2_PCT:.0%})")
    print(f"Level 3: {level3_sz} contracts @ {level3_px:.4f} ({LADDER_LEVEL3_PCT:.0%})")

    # Step 4: Place ladder orders
    print("\n📝 Step 4: Place Ladder Orders")
    print("-" * 80)

    input("Press Enter to place ladder orders (or Ctrl+C to cancel)...")

    orders = []
    ts = int(time.time())

    for i, (sz, px, label) in enumerate([
        (level1_sz, level1_px, "L1"),
        (level2_sz, level2_px, "L2"),
        (level3_sz, level3_px, "L3"),
    ], 1):
        if sz <= 0:
            continue

        cl_ord_id = f"test{ts}{label}"[:32]

        print(f"\nPlacing {label}: {sz} @ {px:.4f}")

        resp = okx.place_order(
            inst_id=TEST_SYMBOL,
            td_mode=OKX_TD_MODE,
            side=TEST_SIDE,
            pos_side=TEST_POS_SIDE,
            ord_type="limit",
            sz=str(sz),
            px=f"{px:.4f}",
            cl_ord_id=cl_ord_id,
            reduce_only=False,
        )

        if str(resp.get("code", "")) not in {"0", "success"}:
            print(f"❌ Failed: {resp}")
        else:
            print(f"✅ Success: {cl_ord_id}")
            orders.append({
                "cl_ord_id": cl_ord_id,
                "size": sz,
                "price": px,
                "level": label,
            })

    if not orders:
        print("❌ No orders placed")
        return

    # Step 5: Wait for fills
    print("\n⏳ Step 5: Wait for Fills (checking every 2s for 20s)")
    print("-" * 80)

    filled_orders = []
    total_filled_sz = 0
    total_filled_value = 0.0

    for retry in range(10):  # 10 retries = 20 seconds
        time.sleep(2)

        for order in orders:
            if order["cl_ord_id"] in [o["cl_ord_id"] for o in filled_orders]:
                continue  # Already filled

            ord_info = okx.get_order(inst_id=TEST_SYMBOL, cl_ord_id=order["cl_ord_id"])
            if ord_info:
                state = ord_info.get("state", "").lower()
                avg_px = ord_info.get("avgPx")
                acc_fill_sz = int(float(ord_info.get("accFillSz", "0") or "0"))

                if avg_px and acc_fill_sz > 0:
                    px = float(avg_px)
                    total_filled_value += px * acc_fill_sz
                    total_filled_sz += acc_fill_sz
                    filled_orders.append(order)
                    print(f"✅ {order['level']} filled: {acc_fill_sz} @ {px:.4f}")

        if total_filled_sz > 0:
            avg_fill_px = total_filled_value / total_filled_sz
            print(f"\n📊 Current: {total_filled_sz}/{total_contracts} filled, avg: {avg_fill_px:.4f}")

    if total_filled_sz == 0:
        print("\n⚠️ No fills after 20s. Canceling orders...")
        for order in orders:
            try:
                okx.cancel_order(inst_id=TEST_SYMBOL, cl_ord_id=order["cl_ord_id"])
                print(f"Canceled: {order['cl_ord_id']}")
            except Exception as e:
                print(f"Cancel failed: {e}")
        return

    avg_fill_px = total_filled_value / total_filled_sz
    print(f"\n✅ Total filled: {total_filled_sz} contracts @ avg {avg_fill_px:.4f}")

    # Step 6: Place stop-loss order
    print("\n🛡️ Step 6: Place Stop-Loss Order")
    print("-" * 80)

    sl_side = "sell" if TEST_SIDE == "buy" else "buy"

    print(f"SL: {total_filled_sz} contracts @ trigger {sl_price:.4f}")

    input("Press Enter to place stop-loss (or Ctrl+C to cancel)...")

    sl_resp = okx.place_algo_order(
        inst_id=TEST_SYMBOL,
        td_mode=OKX_TD_MODE,
        side=sl_side,
        pos_side=TEST_POS_SIDE,
        ord_type="conditional",
        sz=str(total_filled_sz),
        sl_trigger_px=f"{sl_price:.4f}",
        sl_ord_px="-1",
    )

    if str(sl_resp.get("code", "")) not in {"0", "success"}:
        print(f"❌ SL failed: {sl_resp}")
    else:
        print(f"✅ SL placed: {sl_resp}")

    # Step 7: Check position
    print("\n📊 Step 7: Check Position")
    print("-" * 80)

    pos = okx.get_position(inst_id=TEST_SYMBOL, pos_side=TEST_POS_SIDE)
    if pos:
        print(f"Position: {pos.get('pos')} contracts")
        print(f"Avg price: {pos.get('avgPx')}")
        print(f"Unrealized PnL: ${pos.get('upl')}")
    else:
        print("No position found")

    # Step 8: Manual close
    print("\n🔴 Step 8: Close Position (Manual)")
    print("-" * 80)
    print("Options:")
    print("1. Wait for stop-loss to trigger")
    print("2. Manually close position now")
    print("3. Leave position open")

    choice = input("Enter choice (1/2/3): ").strip()

    if choice == "2":
        print(f"\nClosing {total_filled_sz} contracts...")

        close_resp = okx.place_order(
            inst_id=TEST_SYMBOL,
            td_mode=OKX_TD_MODE,
            side=sl_side,
            pos_side=TEST_POS_SIDE,
            ord_type="market",
            sz=str(total_filled_sz),
            px=None,
            cl_ord_id=f"test{ts}close"[:32],
            reduce_only=True,
        )

        if str(close_resp.get("code", "")) not in {"0", "success"}:
            print(f"❌ Close failed: {close_resp}")
        else:
            print(f"✅ Position closed: {close_resp}")

            # Cancel SL order
            try:
                algo_orders = okx.get_algo_orders(inst_id=TEST_SYMBOL)
                for algo in algo_orders:
                    if algo.get("state") == "live":
                        okx.cancel_algo_order(inst_id=TEST_SYMBOL, algo_id=algo.get("algoId"))
                        print(f"✅ Canceled SL order: {algo.get('algoId')}")
            except Exception as e:
                print(f"Cancel SL failed: {e}")

    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Test canceled by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
