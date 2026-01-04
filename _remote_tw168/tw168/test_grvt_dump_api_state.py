#!/usr/bin/env python3
from __future__ import annotations
import os
import asyncio
from app.grvt import GrvtClient, GrvtCredentials

API_KEY = os.getenv("GRVT_API_KEY")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY")
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

async def main():
    creds = GrvtCredentials(api_key=API_KEY, private_key=API_SECRET, trading_account_id=TRADING_ACCOUNT)
    client = GrvtClient(BASE_URL, creds)
    try:
        conn = client.connect()
        if asyncio.iscoroutine(conn):
            await conn
    except Exception as e:
        print("connect error:", e)

    api = client.api
    print("\n--- api attributes ---")
    try:
        print("has attribute 'parameters'? ->", hasattr(api, 'parameters'))
        if hasattr(api, 'parameters'):
            print('api.parameters =', getattr(api, 'parameters'))
    except Exception as e:
        print('parameters read error', e)
    try:
        print("has attribute 'options'? ->", hasattr(api, 'options'))
        if hasattr(api, 'options'):
            print('api.options =', getattr(api, 'options'))
    except Exception as e:
        print('options read error', e)
    try:
        print('has attr markets ->', hasattr(api, 'markets'))
        if hasattr(api, 'markets'):
            print('markets count ->', len(getattr(api, 'markets', {})))
    except Exception as e:
        print('markets read error', e)
    print('\n--- dir(api) sample ---')
    try:
        names = [n for n in dir(api) if not n.startswith('_')]
        print(names[:80])
    except Exception as e:
        print('dir error', e)

if __name__ == '__main__':
    asyncio.run(main())
