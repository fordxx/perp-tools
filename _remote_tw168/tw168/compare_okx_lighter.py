#!/usr/bin/env python3
"""Compare OKX vs Lighter prices using REST APIs only."""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Get symbols from CANDLE_WS_SYMBOL_TFS
symbols_str = os.getenv("CANDLE_WS_SYMBOL_TFS", "")
if not symbols_str:
    print("❌ No CANDLE_WS_SYMBOL_TFS configured")
    exit(1)

# Parse symbols
okx_symbols = []
for pair in symbols_str.split(","):
    if ":" in pair:
        symbol = pair.split(":")[0].strip()
        if symbol:
            okx_symbols.append(symbol)

print(f"🔍 Comparing OKX vs Lighter prices for {len(okx_symbols)} trading pairs...\n")

# First, get Lighter market list
print("📊 Fetching Lighter markets...")
try:
    lighter_resp = requests.get("https://mainnet.zklighter.elliot.ai/order-books", timeout=10)
    lighter_data = lighter_resp.json()
    lighter_markets = {}

    if "order_books" in lighter_data:
        for market in lighter_data["order_books"]:
            symbol = market.get("symbol", "")
            market_id = market.get("market_id")
            if symbol and market_id is not None:
                lighter_markets[symbol.upper()] = market_id
        print(f"✅ Found {len(lighter_markets)} Lighter markets: {', '.join(sorted(lighter_markets.keys()))}\n")
    else:
        print("❌ Failed to fetch Lighter markets\n")
        lighter_markets = {}
except Exception as e:
    print(f"❌ Error fetching Lighter markets: {e}\n")
    lighter_markets = {}

# Compare prices
print(f"{'Symbol':<20} {'OKX Mid':<12} {'Lighter Mid':<12} {'Spread %':<10} {'Status':<15}")
print("=" * 80)

available_on_lighter = 0
price_differences = []

for okx_symbol in okx_symbols:
    try:
        # Get OKX price
        url = f"https://www.okx.com/api/v5/market/ticker?instId={okx_symbol}"
        response = requests.get(url, timeout=10)
        okx_data = response.json()

        if okx_data.get("code") != "0" or not okx_data.get("data"):
            print(f"{okx_symbol:<20} Error fetching OKX price")
            continue

        ticker = okx_data["data"][0]
        okx_bid = float(ticker.get("bidPx", 0))
        okx_ask = float(ticker.get("askPx", 0))
        okx_mid = (okx_bid + okx_ask) / 2 if okx_bid > 0 and okx_ask > 0 else 0

        if okx_mid == 0:
            print(f"{okx_symbol:<20} Invalid OKX price")
            continue

        # Convert to Lighter symbol (e.g., ETH-USDT-SWAP -> ETH)
        lighter_symbol = okx_symbol.split("-")[0].upper()

        # Check if available on Lighter
        if lighter_symbol not in lighter_markets:
            print(f"{okx_symbol:<20} ${okx_mid:<11.2f} {'N/A':<12} {'N/A':<10} Not on Lighter")
            continue

        # Get Lighter price from orderbook
        market_id = lighter_markets[lighter_symbol]
        lighter_url = f"https://mainnet.zklighter.elliot.ai/order-book-orders?market_id={market_id}&limit=1"
        lighter_resp = requests.get(lighter_url, timeout=10)
        lighter_ob = lighter_resp.json()

        bids = lighter_ob.get("bids", [])
        asks = lighter_ob.get("asks", [])

        if not bids or not asks:
            print(f"{okx_symbol:<20} ${okx_mid:<11.2f} {'No liquidity':<12} {'N/A':<10} No orderbook")
            continue

        lighter_bid = float(bids[0].get("price", 0))
        lighter_ask = float(asks[0].get("price", 0))
        lighter_mid = (lighter_bid + lighter_ask) / 2

        if lighter_mid == 0:
            print(f"{okx_symbol:<20} ${okx_mid:<11.2f} {'Invalid':<12} {'N/A':<10} Bad price")
            continue

        # Calculate spread
        spread_pct = ((lighter_mid - okx_mid) / okx_mid) * 100
        price_differences.append((okx_symbol, spread_pct))
        available_on_lighter += 1

        status = "✅ Available" if abs(spread_pct) < 1.0 else "⚠️  Large spread"
        print(f"{okx_symbol:<20} ${okx_mid:<11.2f} ${lighter_mid:<11.2f} {spread_pct:>+9.2f}% {status}")

    except Exception as e:
        print(f"{okx_symbol:<20} Error: {str(e)[:40]}")

# Summary
print("\n" + "=" * 80)
print(f"\n📈 Summary:")
print(f"   Total symbols checked: {len(okx_symbols)}")
print(f"   Available on Lighter: {available_on_lighter}")
print(f"   Not on Lighter: {len(okx_symbols) - available_on_lighter}")

if price_differences:
    avg_spread = sum(abs(s) for _, s in price_differences) / len(price_differences)
    max_spread = max(price_differences, key=lambda x: abs(x[1]))
    min_spread = min(price_differences, key=lambda x: abs(x[1]))

    print(f"\n💰 Price Analysis:")
    print(f"   Average spread: {avg_spread:.2f}%")
    print(f"   Largest spread: {max_spread[0]} ({max_spread[1]:+.2f}%)")
    print(f"   Smallest spread: {min_spread[0]} ({min_spread[1]:+.2f}%)")
