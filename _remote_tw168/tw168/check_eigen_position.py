#!/usr/bin/env python3
"""Check EIGEN position on Lighter DEX"""
import asyncio
import sys
from app.lighter_adapter import create_lighter_adapter

async def main():
    symbol = "EIGEN-USDT-SWAP"
    
    print("=" * 80)
    print(f"Checking {symbol} on Lighter DEX")
    print("=" * 80)
    
    client = create_lighter_adapter(use_testnet=False)
    await client.connect()
    
    # Check long position
    print("\n📊 Long Position:")
    print("-" * 80)
    pos = await client.get_position(inst_id=symbol, pos_side="long")
    
    if pos:
        size = pos.get('pos', 0)
        entry = pos.get('avgPx', 0)
        value = float(size) * float(entry)
        print(f"✅ Size: {size} contracts")
        print(f"   Entry: ${entry}")
        print(f"   Market value: ${value:.2f}")
    else:
        print("❌ No long position")
    
    # Check short position
    print("\n📊 Short Position:")
    print("-" * 80)
    pos = await client.get_position(inst_id=symbol, pos_side="short")
    
    if pos:
        size = pos.get('pos', 0)
        entry = pos.get('avgPx', 0)
        value = float(size) * float(entry)
        print(f"✅ Size: {size} contracts")
        print(f"   Entry: ${entry}")
        print(f"   Market value: ${value:.2f}")
    else:
        print("❌ No short position")
    
    # Get current price
    print("\n📈 Current Market:")
    print("-" * 80)
    price = await client.get_last_price(inst_id=symbol)
    print(f"Last Price: ${price}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
