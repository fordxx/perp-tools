#!/usr/bin/env python3
from __future__ import annotations
import os
import asyncio
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
    await client.connect()

    inst_id = "LDO_USDT_Perp"

    print(f"Trading account ID: {TRADING_ACCOUNT}")

    # Try raw API calls like in cancel script
    print("\nTrying raw fetch_positions...")
    try:
        positions = await client.api.fetch_positions(params={"trading_account_id": TRADING_ACCOUNT})
        print(f"Raw positions: {positions}")
    except Exception as e:
        print(f"Raw fetch_positions failed: {e}")

    print("\nTrying raw fetch_open_orders...")
    try:
        orders = await client.api.fetch_open_orders(symbol="LDO_USDT_Perp", params={"trading_account_id": TRADING_ACCOUNT})
        print(f"Raw open orders: {len(orders) if orders else 0}")
        if orders:
            for order in orders:
                print(f"  - {order}")
    except Exception as e:
        print(f"Raw fetch_open_orders failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())