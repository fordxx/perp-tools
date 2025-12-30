#!/usr/bin/env python3
"""
Cancel all EIGEN orders on Lighter exchange
Simple script that uses SignerClient.cancel_all_orders()
"""

import asyncio
import os
import sys


async def cancel_all_eigen_orders():
    """Cancel all orders for EIGEN market."""
    from lighter.signer_client import SignerClient

    # Load .env file
    env_file = "/home/ubuntu/tw168/.env"
    config = {}

    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key] = value

    api_private_key = config.get('LIGHTER_API_KEY_PRIVATE_KEY', '')
    account_index = int(config.get('LIGHTER_ACCOUNT_INDEX', '1'))
    api_key_index = int(config.get('LIGHTER_API_KEY_INDEX', '2'))

    if not api_private_key:
        print("❌ LIGHTER_API_KEY_PRIVATE_KEY not found in .env")
        return False

    print("=" * 70)
    print("Cancel All EIGEN Orders")
    print("=" * 70)
    print(f"\nAccount Index: {account_index}")
    print(f"API Key Index: {api_key_index}")
    print(f"Market: EIGEN (ID: 49)")
    print()

    try:
        # Create SignerClient
        print("📋 Connecting to Lighter...")
        client = SignerClient(
            url="https://mainnet.zklighter.elliot.ai",
            account_index=account_index,
            api_private_keys={api_key_index: api_private_key}
        )

        # Check client
        err = client.check_client()
        if err:
            print(f"❌ Client check failed: {err}")
            return False

        print("✅ Connected successfully\n")

        # Cancel all orders for EIGEN market (ID: 49)
        print("🗑️  Cancelling all EIGEN orders...")

        cancel_result, tx_hash, error = await client.cancel_all_orders(
            market_index=49
        )

        if error:
            print(f"❌ Cancel failed: {error}")
            return False

        print(f"✅ Cancel request submitted!")
        print(f"   TxHash: {tx_hash}")
        print()

        # Wait for confirmation
        print("⏳ Waiting 3 seconds for confirmation...")
        await asyncio.sleep(3)

        print("\n" + "=" * 70)
        print("✅ All EIGEN orders should be cancelled!")
        print("=" * 70)
        print()
        print("Verify on Lighter platform: https://mainnet.zklighter.elliot.ai/")
        print("Or check with: docker compose exec tv-okx python3 /app/check_eigen_position.py")
        print()

        return True

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(cancel_all_eigen_orders())
    sys.exit(0 if success else 1)
