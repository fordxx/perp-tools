#!/usr/bin/env python3
"""
Attach SL and TP by splitting reduce-only orders into chunks if needed.
"""
import asyncio
import os
import json
import math
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

load_dotenv('.env')

from app.grvt import GrvtClient, GrvtCredentials
from app.config import SETTINGS, get_lookback_bars
from app.risk import fetch_candles_paged, stop_loss_price_lookback, take_profit_price

INST_ID = 'LDO-USDT-SWAP'
TF = os.getenv('TRADE_TF', '15m')
MAX_CHUNK = int(os.getenv('GRVT_SL_CHUNK', '3000'))

async def run():
    creds = GrvtCredentials(api_key=os.getenv('GRVT_API_KEY'), private_key=os.getenv('GRVT_PRIVATE_KEY'), trading_account_id=os.getenv('GRVT_TRADING_ACCOUNT_ID'))
    client = GrvtClient(os.getenv('GRVT_BASE_URL', 'https://api.grvt.io'), creds)
    await client.connect()

    raw_positions = await client.api.fetch_positions()
    sym = client._normalize_symbol(INST_ID)
    found = None
    for p in raw_positions or []:
        instr = p.get('instrument') or p.get('symbol') or p.get('inst')
        if instr == sym:
            found = p
            break
    if not found:
        print('No raw position for', INST_ID)
        return

    size = abs(float(found.get('size') or 0.0))
    entry_px = float(found.get('entry_price') or found.get('entryPrice') or 0.0)
    pos_side = 'short' if float(found.get('size', 0)) < 0 else 'long'
    entry_side = 'sell' if pos_side == 'short' else 'buy'
    close_side = 'buy' if entry_side == 'sell' else 'sell'

    print(f'Position: side={pos_side} size={size} entry={entry_px}')

    # compute SL/TP (same logic as before)
    desired = max(300, SETTINGS.rsi_max_data + SETTINGS.rsi_length + 2)
    try:
        candles = await asyncio.to_thread(fetch_candles_paged, SETTINGS.okx_base_url, INST_ID, TF, desired)
    except Exception:
        candles = []

    sl = None
    try:
        sl = stop_loss_price_lookback(
            side=entry_side,
            entry_price=entry_px,
            candles=candles,
            lookback_bars=get_lookback_bars(TF),
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    except Exception:
        sl = None
    if sl is None:
        sl = entry_px * (1.02 if entry_side == 'sell' else 0.98)
    tp = take_profit_price(side=entry_side, entry_price=entry_px, stop_loss=sl, rr=1.5)

    market = client.api.markets.get(sym) or {}
    tick = market.get('tick_size') or market.get('min_price') or '0.000000001'
    t = Decimal(str(tick))
    sl_rd = (Decimal(str(sl)) / t).to_integral_value(rounding=ROUND_DOWN) * t
    tp_rd = (Decimal(str(tp)) / t).to_integral_value(rounding=ROUND_DOWN) * t

    print('SL rounded:', sl_rd, 'TP rounded:', tp_rd)

    # Break into chunks
    chunks = []
    remaining = int(math.floor(size))
    while remaining > 0:
        this = min(remaining, MAX_CHUNK)
        chunks.append(this)
        remaining -= this

    print('Chunks:', chunks)

    sl_responses = []
    for idx, chunk in enumerate(chunks, 1):
        params = {'stopLossPrice': float(sl_rd), 'reduce_only': True}
        try:
            resp = await client.api.create_order(
                symbol=sym,
                order_type='limit',
                side=close_side,
                amount=Decimal(str(chunk)),
                price=float(sl_rd),
                params=params,
            )
            print(f'SL chunk {idx} resp:', json.dumps(resp, ensure_ascii=False, default=str))
            sl_responses.append(resp)
        except Exception as e:
            print(f'SL chunk {idx} exception:', e)

    tp_responses = []
    for idx, chunk in enumerate(chunks, 1):
        params = {'takeProfitPrice': float(tp_rd), 'reduce_only': True}
        try:
            resp = await client.api.create_order(
                symbol=sym,
                order_type='limit',
                side=close_side,
                amount=Decimal(str(chunk)),
                price=float(tp_rd),
                params=params,
            )
            print(f'TP chunk {idx} resp:', json.dumps(resp, ensure_ascii=False, default=str))
            tp_responses.append(resp)
        except Exception as e:
            print(f'TP chunk {idx} exception:', e)

    print('Done')

if __name__ == '__main__':
    asyncio.run(run())
