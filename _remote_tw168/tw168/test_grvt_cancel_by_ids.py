#!/usr/bin/env python3
from __future__ import annotations
import os
import asyncio
from app.grvt import GrvtClient, GrvtCredentials

API_KEY = os.getenv("GRVT_API_KEY")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY")
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

# Provide CANCEL_IDS env var as comma-separated client_order_ids, otherwise use defaults
DEFAULT_IDS = [
    "2111599471",  # large pending limit (reported earlier)
    "2812317874",
    "3706547850",
    "961204888",
    "2034688839",
]

async def main():
    ids_raw = os.getenv("CANCEL_IDS")
    if ids_raw:
        ids = [s.strip() for s in ids_raw.split(",") if s.strip()]
    else:
        ids = DEFAULT_IDS

    creds = GrvtCredentials(api_key=API_KEY, private_key=API_SECRET, trading_account_id=TRADING_ACCOUNT)
    client = GrvtClient(BASE_URL, creds)
    try:
        conn = client.connect()
        if asyncio.iscoroutine(conn):
            await conn
    except Exception as e:
        print("connect error:", e)
        return

    inst = "LDO-USDT-SWAP"
    for cid in ids:
        try:
            print(f"Cancelling client_order_id={cid} for {inst} ...")
            resp = await client.cancel_order(inst_id=inst, cl_ord_id=cid)
            print("->", resp)
        except Exception as e:
            print(f"Error cancelling {cid}:", e)

if __name__ == '__main__':
    asyncio.run(main())
