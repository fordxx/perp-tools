#!/usr/bin/env python3
from __future__ import annotations
import os
import asyncio
import json
from dotenv import load_dotenv
from app.grvt import GrvtClient, GrvtCredentials

load_dotenv()

API_KEY = os.getenv("GRVT_API_KEY")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY")
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

async def main():
    creds = GrvtCredentials(api_key=API_KEY, private_key=API_SECRET, trading_account_id=TRADING_ACCOUNT)
    client = GrvtClient(BASE_URL, creds)
    try:
        await client.connect()
    except Exception as e:
        print("connect error:", e)
        return

    # Inspect SDK methods
    print("SDK methods:")
    methods = [m for m in dir(client.api) if not m.startswith('_')]
    for method in sorted(methods):
        print(f"  {method}")

    # Check trading account ID
    print(f"\nTrading account ID from env: {TRADING_ACCOUNT}")
    try:
        account_id = await client.api.get_trading_account_id()
        print(f"SDK get_trading_account_id(): {account_id}")
    except Exception as e:
        print("get_trading_account_id failed:", repr(e))

    # Try raw API calls
    print("\nTrying raw fetch_open_orders...")
    try:
        symbol = client._normalize_symbol("LDO-USDT-SWAP")
        print(f"Symbol: {symbol}")
        # Try without params first
        orders = await client.api.fetch_open_orders(symbol)
        print("Raw fetch_open_orders (no params):", orders)
    except Exception as e:
        print("Raw fetch_open_orders failed:", repr(e))

    # Try with trading_account_id in different ways
    try:
        orders = await client.api.fetch_open_orders(symbol, {"trading_account_id": TRADING_ACCOUNT})
        print("Raw fetch_open_orders (with params):", orders)
    except Exception as e:
        print("Raw fetch_open_orders with params failed:", repr(e))

    # Try cancel_all_orders raw
    print("\nTrying raw cancel_all_orders...")
    try:
        result = await client.api.cancel_all_orders({"trading_account_id": TRADING_ACCOUNT})
        print("Raw cancel_all_orders:", result)
    except Exception as e:
        print("Raw cancel_all_orders failed:", repr(e))


if __name__ == '__main__':
    asyncio.run(main())
