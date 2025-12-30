#!/usr/bin/env python3
"""Compare prices between OKX and Lighter for configured trading pairs."""

import sys
import os
sys.path.insert(0, "/home/fordxx/perp-tools")

from dotenv import load_dotenv
from perpbot.exchanges.lighter import LighterClient

# Also need OKX client
sys.path.insert(0, "/home/fordxx/perp-tools/_remote_tw168/tw168")
from app.okx import OKXClient, OKXCredentials
from app.config import SETTINGS

def main():
    load_dotenv()

    # Get symbol list from env
    symbols_str = os.getenv("CANDLE_WS_SYMBOL_TFS", "")
    if not symbols_str:
        print("❌ No CANDLE_WS_SYMBOL_TFS configured")
        return

    # Parse symbols (format: "ETH-USDT-SWAP:1h,BTC-USDT-SWAP:4h,...")
    symbol_pairs = []
    for pair in symbols_str.split(","):
        if ":" in pair:
            symbol = pair.split(":")[0].strip()
            if symbol:
                symbol_pairs.append(symbol)

    if not symbol_pairs:
        print("❌ No symbols found in CANDLE_WS_SYMBOL_TFS")
        return

    print(f"🔍 Comparing prices for {len(symbol_pairs)} trading pairs...\n")

    # Initialize OKX client
    print("📊 Connecting to OKX...")
    okx = OKXClient(
        SETTINGS.okx_base_url,
        OKXCredentials(
            api_key=SETTINGS.okx_api_key,
            api_secret=SETTINGS.okx_api_secret,
            passphrase=SETTINGS.okx_api_passphrase,
        ),
    )

    # Initialize Lighter client
    print("⚡ Connecting to Lighter...")
    lighter = LighterClient(use_testnet=False)
    try:
        lighter.connect()
        print(f"✅ Lighter connected (trading_enabled={lighter._trading_enabled})\n")
    except Exception as e:
        print(f"❌ Lighter connection failed: {e}")
        return

    # Compare prices
    print(f"{'Symbol':<20} {'OKX Bid':<12} {'OKX Ask':<12} {'Lighter Bid':<12} {'Lighter Ask':<12} {'Spread %':<10}")
    print("=" * 90)

    total_symbols = 0
    lighter_available = 0
    price_differences = []

    for okx_symbol in symbol_pairs:
        try:
            # Get OKX price
            okx_price = okx.get_current_price(okx_symbol)

            # Convert to Lighter symbol (e.g., ETH-USDT-SWAP -> ETH)
            lighter_symbol = okx_symbol.split("-")[0] if "-" in okx_symbol else okx_symbol

            # Get Lighter price
            lighter_price = lighter.get_current_price(lighter_symbol)

            total_symbols += 1

            # Check if symbol exists on Lighter
            if lighter_price.bid > 0 and lighter_price.ask > 0:
                lighter_available += 1

                # Calculate mid prices
                okx_mid = (okx_price.bid + okx_price.ask) / 2 if okx_price.bid > 0 and okx_price.ask > 0 else 0
                lighter_mid = (lighter_price.bid + lighter_price.ask) / 2

                # Calculate spread percentage
                if okx_mid > 0:
                    spread_pct = ((lighter_mid - okx_mid) / okx_mid) * 100
                    price_differences.append((okx_symbol, spread_pct))

                    print(f"{okx_symbol:<20} ${okx_price.bid:<11.2f} ${okx_price.ask:<11.2f} "
                          f"${lighter_price.bid:<11.2f} ${lighter_price.ask:<11.2f} {spread_pct:>+9.2f}%")
                else:
                    print(f"{okx_symbol:<20} ${okx_price.bid:<11.2f} ${okx_price.ask:<11.2f} "
                          f"${lighter_price.bid:<11.2f} ${lighter_price.ask:<11.2f} {'N/A':>10}")
            else:
                print(f"{okx_symbol:<20} ${okx_price.bid:<11.2f} ${okx_price.ask:<11.2f} "
                      f"{'N/A':<12} {'N/A':<12} {'N/A':>10}")

        except Exception as e:
            print(f"{okx_symbol:<20} Error: {str(e)[:60]}")

    # Summary
    print("\n" + "=" * 90)
    print(f"\n📈 Summary:")
    print(f"   Total symbols checked: {total_symbols}")
    print(f"   Available on Lighter: {lighter_available}")
    print(f"   Not on Lighter: {total_symbols - lighter_available}")

    if price_differences:
        avg_spread = sum(abs(s) for _, s in price_differences) / len(price_differences)
        max_spread = max(price_differences, key=lambda x: abs(x[1]))
        min_spread = min(price_differences, key=lambda x: abs(x[1]))

        print(f"\n💰 Price Analysis:")
        print(f"   Average spread: {avg_spread:.2f}%")
        print(f"   Largest spread: {max_spread[0]} ({max_spread[1]:+.2f}%)")
        print(f"   Smallest spread: {min_spread[0]} ({min_spread[1]:+.2f}%)")

    lighter.disconnect()

if __name__ == "__main__":
    main()
