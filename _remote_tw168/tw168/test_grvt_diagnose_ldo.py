#!/usr/bin/env python3
"""
Diagnostic: list positions and open orders for LDO and overall via GRVT client.
"""
import asyncio
import os
import json
from dotenv import load_dotenv

load_dotenv('.env')

from app.grvt import GrvtClient, GrvtCredentials

INST_ID = 'LDO-USDT-SWAP'

async def run():
    creds = GrvtCredentials(api_key=os.getenv('GRVT_API_KEY'), private_key=os.getenv('GRVT_PRIVATE_KEY'), trading_account_id=os.getenv('GRVT_TRADING_ACCOUNT_ID'))
    client = GrvtClient(os.getenv('GRVT_BASE_URL', 'https://api.grvt.io'), creds)
    await client.connect()

    print('\n=== Checking specific position (short then long) ===')
    for side in ('short','long'):
        try:
            pos = await client.get_position(inst_id=INST_ID, pos_side=side)
            print(f'Position {side}:', json.dumps(pos, ensure_ascii=False))
        except Exception as e:
            print('get_position error', e)

    print('\n=== Open orders for LDO ===')
    try:
        orders = await client.get_open_orders(inst_id=INST_ID)
        print('open_orders:', json.dumps(orders, ensure_ascii=False, default=str))
    except Exception as e:
        print('get_open_orders error', e)

    print('\n=== Raw API: fetch_positions (all) ===')
    try:
        raw_positions = await client.api.fetch_positions()
        print('raw positions:', json.dumps(raw_positions, ensure_ascii=False, default=str))
    except Exception as e:
        print('fetch_positions error', e)

    print('\n=== Raw API: fetch_open_orders (all) ===')
    try:
        raw_open = await client.api.fetch_open_orders()
        print('raw open orders:', json.dumps(raw_open, ensure_ascii=False, default=str))
    except Exception as e:
        print('fetch_open_orders(all) error', e)

    print('\n=== Recent orders via fetch_orders (last 50) ===')
    try:
        recent = await client.api.fetch_orders(params={'limit':50})
        print('recent orders:', json.dumps(recent, ensure_ascii=False, default=str))
    except Exception as e:
        print('fetch_orders error', e)

if __name__ == '__main__':
    asyncio.run(run())
