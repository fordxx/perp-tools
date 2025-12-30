#!/usr/bin/env python3
"""Quick price comparison without needing full client initialization."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Get symbols from CANDLE_WS_SYMBOL_TFS
symbols_str = os.getenv("CANDLE_WS_SYMBOL_TFS", "")
if not symbols_str:
    print("❌ No CANDLE_WS_SYMBOL_TFS configured")
    exit(1)

# Parse symbols (format: "ETH-USDT-SWAP:1h,BTC-USDT-SWAP:4h,...")
okx_symbols = []
for pair in symbols_str.split(","):
    if ":" in pair:
        symbol = pair.split(":")[0].strip()
        if symbol:
            okx_symbols.append(symbol)

print(f"🔍 Checking prices for {len(okx_symbols)} trading pairs on OKX...\n")
print(f"{'Symbol':<20} {'OKX Bid':<12} {'OKX Ask':<12} {'Mid Price':<12} {'Spread':<10}")
print("=" * 80)

# Get OKX prices
for symbol in okx_symbols:
    try:
        # OKX REST API for ticker
        url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("code") == "0" and data.get("data"):
            ticker = data["data"][0]
            bid = float(ticker.get("bidPx", 0))
            ask = float(ticker.get("askPx", 0))
            mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
            spread_bps = ((ask - bid) / mid * 10000) if mid > 0 else 0

            print(f"{symbol:<20} ${bid:<11.2f} ${ask:<11.2f} ${mid:<11.2f} {spread_bps:>9.1f}bp")
        else:
            print(f"{symbol:<20} Error: {data.get('msg', 'Unknown error')}")

    except Exception as e:
        print(f"{symbol:<20} Error: {str(e)[:50]}")

print("\n" + "=" * 80)
print("\n💡 Note: Lighter DEX integration requires lighter-sdk package.")
print("   To compare with Lighter prices, need to add 'lighter-sdk' to requirements.txt and rebuild.")
