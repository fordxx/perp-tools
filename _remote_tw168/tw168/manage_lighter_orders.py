#!/usr/bin/env python3
"""
Lighter Order Management Script

Query and cancel hanging orders on Lighter exchange using SignerClient.
Run this on the host system (not in container) to avoid DNS issues.
"""

import asyncio
import os
import sys


async def get_active_orders_and_cancel(api_private_key: str, account_index: int, api_key_index: int, market_id: int):
    """Query active orders and cancel them using SignerClient."""
    from lighter.signer_client import SignerClient

    print(f"\n📋 Connecting to Lighter...")

    try:
        # Create SignerClient
        client = SignerClient(
            url="https://mainnet.zklighter.elliot.ai",
            account_index=account_index,
            api_private_keys={api_key_index: api_private_key}
        )

        # Check client first
        err = client.check_client()
        if err:
            print(f"❌ Client check failed: {err}")
            return False

        print(f"✅ SignerClient connected successfully\n")

        # Get account info to check for open orders
        print(f"📊 Fetching account info for account {account_index}...")

        account_data, err = await client.get_account(account_index=account_index)

        if err:
            print(f"❌ Failed to get account info: {err}")
            return False

        if not account_data:
            print("❌ No account data returned")
            return False

        print(f"✅ Account data retrieved\n")

        # Check positions for EIGEN market
        if hasattr(account_data, 'positions') and account_data.positions:
            for pos in account_data.positions:
                if pos.market_index == market_id:
                    ooc = getattr(pos, 'open_order_count', 0)
                    print(f"🔍 EIGEN Market (ID: {market_id}):")
                    print(f"   Open Order Count: {ooc}")
                    print(f"   Position Size: {getattr(pos, 'position', 0)}")
                    print()

                    if ooc == 0:
                        print("✅ No open orders found!")
                        return True

        # Try to get order history to find open orders
        print(f"📋 Fetching active orders...")

        # Note: SignerClient may not have direct get_active_orders method
        # We'll use cancel_all_orders which is more direct
        print(f"\n⚠️  Attempting to cancel all open orders for market {market_id}...")

        response = input(f"Cancel all orders? (yes/no): ")
        if response.lower() != 'yes':
            print("❌ Cancelled by user")
            return False

        # Cancel all orders for this market
        cancel_result, tx_hash, error = await client.cancel_all_orders(
            market_index=market_id
        )

        if error:
            print(f"❌ Cancel failed: {error}")
            return False

        print(f"✅ Cancel request submitted!")
        print(f"   TxHash: {tx_hash}")
        print()

        # Wait a bit for the transaction to process
        print("⏳ Waiting 5 seconds for transaction confirmation...")
        await asyncio.sleep(5)

        # Verify by checking account again
        print("\n🔄 Verifying...")
        account_data_after, err = await client.get_account(account_index=account_index)

        if not err and account_data_after and hasattr(account_data_after, 'positions'):
            for pos in account_data_after.positions:
                if pos.market_index == market_id:
                    ooc_after = getattr(pos, 'open_order_count', 0)
                    print(f"✅ After cancellation:")
                    print(f"   Open Order Count: {ooc_after}")

                    if ooc_after == 0:
                        print("\n🎉 All orders cancelled successfully!")
                        return True
                    else:
                        print(f"\n⚠️  {ooc_after} order(s) still remain")
                        return False

        return True

    except Exception as e:
        print(f"❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main function."""
    print("=" * 70)
    print("Lighter Order Management Tool")
    print("=" * 70)

    # Get credentials from environment or .env file
    env_file = "/home/ubuntu/tw168/.env"

    # Load .env file
    config = {}
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key] = value

    # Get configuration
    api_private_key = config.get('LIGHTER_API_KEY_PRIVATE_KEY', '')
    account_index = int(config.get('LIGHTER_ACCOUNT_INDEX', '1'))
    api_key_index = int(config.get('LIGHTER_API_KEY_INDEX', '2'))

    if not api_private_key:
        print("❌ LIGHTER_API_KEY_PRIVATE_KEY not found in .env")
        sys.exit(1)

    print(f"\n📍 Configuration:")
    print(f"   Account Index: {account_index}")
    print(f"   API Key Index: {api_key_index}")

    # EIGEN market ID
    EIGEN_MARKET_ID = 49

    # Execute cancellation
    success = await get_active_orders_and_cancel(
        api_private_key,
        account_index,
        api_key_index,
        EIGEN_MARKET_ID
    )

    # Summary
    print("\n" + "=" * 70)
    if success:
        print("✅ Operation completed successfully!")
    else:
        print("❌ Operation failed or incomplete")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
