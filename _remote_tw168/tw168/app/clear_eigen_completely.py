#!/usr/bin/env python3
"""
Completely clear EIGEN position and orders
"""

import sys
sys.path.insert(0, '/src')

import asyncio
from perpbot.exchanges.lighter import LighterClient


async def clear_eigen():
    """Close all EIGEN positions and cancel all EIGEN orders."""

    # Create client
    print("🔌 Connecting to Lighter...")
    client = LighterClient(use_testnet=False)
    client.connect()

    print("✅ Connected\n")

    # Get EIGEN price
    quote = client.get_current_price("EIGEN/USDT")
    print(f"💰 EIGEN Price: ${quote.mid:.4f}\n")

    # Get positions
    positions = client.get_account_positions()

    # Find and close EIGEN positions
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if not eigen_positions:
        print("✅ No EIGEN positions found")
    else:
        print(f"📊 Found {len(eigen_positions)} EIGEN position(s)\n")

        for i, pos in enumerate(eigen_positions, 1):
            print(f"Position {i}:")
            print(f"  Symbol: {pos.order.symbol}")
            print(f"  Size: {pos.order.size}")
            print(f"  Price: {pos.order.price}")
            print(f"  Side: {pos.order.side}")
            print()

            # Close this position
            print(f"🔴 Closing position {i}...")
            try:
                close_order = client.place_close_order(pos, quote.mid)
                print(f"✅ Close order placed: {close_order.id}")

                # Wait a bit
                await asyncio.sleep(2)

            except Exception as e:
                print(f"❌ Failed to close: {e}")

            print()

    # Verify
    print("\n🔄 Verifying...")
    await asyncio.sleep(3)

    final_positions = client.get_account_positions()
    final_eigen = [p for p in final_positions if 'EIGEN' in p.order.symbol]

    if not final_eigen:
        print("✅ All EIGEN positions cleared!")
    else:
        print(f"⚠️  {len(final_eigen)} EIGEN position(s) still remain:")
        for p in final_eigen:
            print(f"  - {p.order.symbol}: {p.order.size}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(clear_eigen())
