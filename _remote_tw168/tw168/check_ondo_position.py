#!/usr/bin/env python3
"""Check ONDO position and TP/SL calculation details."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config import SETTINGS
from app.okx import OKXClient, OKXCredentials

def main():
    print("=" * 80)
    print("ONDO Position Analysis")
    print("=" * 80)

    # Initialize OKX client
    creds = OKXCredentials(
        api_key=SETTINGS.okx_api_key,
        api_secret=SETTINGS.okx_api_secret,
        passphrase=SETTINGS.okx_api_passphrase,
    )
    okx = OKXClient(
        base_url=SETTINGS.okx_base_url,
        creds=creds,
    )

    inst_id = "ONDO-USDT-SWAP"

    # 1. Get current position
    print("\n📊 Current Position:")
    print("-" * 80)
    pos_long = okx.get_position(inst_id=inst_id, pos_side="long")
    if pos_long and float(pos_long.get("pos", "0")) != 0:
        print(f"Position Side: long")
        print(f"Size: {pos_long.get('pos')}")
        print(f"Entry Price (avgPx): {pos_long.get('avgPx')}")
        print(f"Mark Price: {pos_long.get('markPx')}")
        print(f"Liquidation Price: {pos_long.get('liqPx')}")
        print(f"Unrealized PnL: {pos_long.get('upl')}")
        print(f"Unrealized PnL Ratio: {pos_long.get('uplRatio')}")
        print(f"Leverage: {pos_long.get('lever')}")

        entry_px = float(pos_long.get('avgPx', '0'))
        mark_px = float(pos_long.get('markPx', '0'))

    else:
        print("No long position found")
        pos_long = None
        entry_px = 0
        mark_px = 0

    # 2. Get current market price
    print("\n📈 Current Market:")
    print("-" * 80)
    last_price = okx.get_last_price(inst_id=inst_id)
    if last_price:
        print(f"Last Price: {last_price:.4f}")
    else:
        print("Could not fetch last price")
        last_price = 0

    # 3. Get open orders (including stop-loss and take-profit)
    print("\n📝 Open Orders:")
    print("-" * 80)
    orders = okx.get_open_orders(inst_id=inst_id)
    if orders:
        for i, order in enumerate(orders, 1):
            ord_type = order.get("ordType", "")
            side = order.get("side", "")
            sz = order.get("sz", "")
            px = order.get("px", "")
            state = order.get("state", "")
            print(f"\nOrder #{i}:")
            print(f"  Type: {ord_type}")
            print(f"  Side: {side}")
            print(f"  Size: {sz}")
            print(f"  Price: {px}")
            print(f"  State: {state}")
            print(f"  Full: {order}")
    else:
        print("No open orders")

    # 4. Get algo orders (stop-loss, take-profit triggers)
    print("\n🤖 Algo Orders (SL/TP):")
    print("-" * 80)
    algo_orders = okx.get_algo_orders(inst_id=inst_id)
    if algo_orders:
        for i, order in enumerate(algo_orders, 1):
            ord_type = order.get("ordType", "")
            side = order.get("side", "")
            sz = order.get("sz", "")
            sl_trigger_px = order.get("slTriggerPx", "")
            tp_trigger_px = order.get("tpTriggerPx", "")
            state = order.get("state", "")
            print(f"\nAlgo Order #{i}:")
            print(f"  Type: {ord_type}")
            print(f"  Side: {side}")
            print(f"  Size: {sz}")
            print(f"  SL Trigger: {sl_trigger_px}")
            print(f"  TP Trigger: {tp_trigger_px}")
            print(f"  State: {state}")
    else:
        print("No algo orders")

    # 5. Calculate expected TP/SL based on current config
    if pos_long and entry_px > 0:
        print("\n🎯 TP/SL Calculation (Based on Current Config):")
        print("-" * 80)
        print(f"Entry Price: {entry_px:.4f}")

        # Try to find the stop-loss from algo orders
        sl_price = None
        for order in (algo_orders or []):
            sl_trigger = order.get("slTriggerPx", "")
            if sl_trigger and sl_trigger != "":
                sl_price = float(sl_trigger)
                break

        if sl_price:
            print(f"Stop-Loss (from orders): {sl_price:.4f}")
            r_value = abs(entry_px - sl_price)
            print(f"R-Value (risk per trade): {r_value:.4f}")

            # Calculate TP levels based on R-multiples
            print(f"\nExpected TP Levels (R-multiples):")
            tp1_r = SETTINGS.tp1_r
            tp2_r = SETTINGS.tp2_r
            tp3_r = SETTINGS.tp3_r
            tp4_r = SETTINGS.tp4_r

            tp1_price = entry_px + (r_value * tp1_r)
            tp2_price = entry_px + (r_value * tp2_r)
            tp3_price = entry_px + (r_value * tp3_r)
            tp4_price = entry_px + (r_value * tp4_r)

            print(f"  TP1 ({SETTINGS.tp1_pct:.0%} @ {tp1_r}R): {tp1_price:.4f}")
            print(f"  TP2 ({SETTINGS.tp2_pct:.0%} @ {tp2_r}R): {tp2_price:.4f}")
            print(f"  TP3 ({SETTINGS.tp3_pct:.0%} @ {tp3_r}R): {tp3_price:.4f}")
            print(f"  TP4 ({SETTINGS.tp4_pct:.0%} @ {tp4_r}R): {tp4_price:.4f}")

            # Calculate current profit_r
            if last_price > 0:
                profit_r = (last_price - entry_px) / r_value
                print(f"\nCurrent Position:")
                print(f"  Last Price: {last_price:.4f}")
                print(f"  Profit/Loss: ${(last_price - entry_px) * float(pos_long.get('pos', '0')):.2f}")
                print(f"  Profit R-multiple: {profit_r:.2f}R")

                if profit_r >= tp1_r:
                    print(f"  ✅ TP1 REACHED ({tp1_r}R)")
                if profit_r >= tp2_r:
                    print(f"  ✅ TP2 REACHED ({tp2_r}R)")
                if profit_r >= tp3_r:
                    print(f"  ✅ TP3 REACHED ({tp3_r}R)")
                if profit_r >= tp4_r:
                    print(f"  ✅ TP4 REACHED ({tp4_r}R)")

                if profit_r < 0:
                    print(f"  ⚠️ Position is at a LOSS ({profit_r:.2f}R)")
        else:
            print("Could not find stop-loss order to calculate R-value")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
