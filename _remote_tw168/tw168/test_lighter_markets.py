#!/usr/bin/env python3
"""Test Lighter markets API to see supported trading pairs."""

import sys
sys.path.insert(0, "/home/fordxx/perp-tools")

from perpbot.exchanges.lighter import LighterClient

def main():
    print("Connecting to Lighter mainnet...")
    client = LighterClient(use_testnet=False)

    try:
        client.connect()
        print(f"\n✅ Connected! Trading enabled: {client._trading_enabled}")
        print(f"\nSupported markets ({len(client._markets)}):")

        for symbol, market_id in sorted(client._markets.items(), key=lambda x: x[1]):
            print(f"  {symbol:<10} (market_id={market_id})")

        # Test getting price for a common market
        if client._markets:
            test_symbol = list(client._markets.keys())[0]
            print(f"\nTesting price fetch for {test_symbol}...")
            price = client.get_current_price(test_symbol)
            print(f"  Bid: {price.bid}, Ask: {price.ask}")

    finally:
        client.disconnect()

if __name__ == "__main__":
    main()
