#!/usr/bin/env python3
"""
Attach SL/TP to existing LDO position found in GRVT raw positions.
"""
import asyncio
import os
import json
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

load_dotenv('.env')

from app.grvt import GrvtClient, GrvtCredentials
from app.config import SETTINGS, get_lookback_bars
from app.risk import fetch_candles_paged, stop_loss_price_lookback, take_profit_price

INST_ID = 'LDO-USDT-SWAP'
TF = os.getenv('TRADE_TF', '15m')


async def run():
    creds = GrvtCredentials(api_key=os.getenv('GRVT_API_KEY'), private_key=os.getenv('GRVT_PRIVATE_KEY'), trading_account_id=os.getenv('GRVT_TRADING_ACCOUNT_ID'))
    client = GrvtClient(os.getenv('GRVT_BASE_URL', 'https://api.grvt.io'), creds)
    await client.connect()

    # Fetch raw positions and find LDO
    raw_positions = []
    try:
        raw_positions = await client.api.fetch_positions()
    except Exception as e:
        print('fetch_positions error', e)
        return

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

    print('Raw position:', json.dumps(found, ensure_ascii=False))

    # Extract size and entry price from raw position
    try:
        size_raw = found.get('size') or found.get('contracts') or found.get('position')
        entry_raw = found.get('entry_price') or found.get('entryPrice') or found.get('entry_price') or found.get('entry_price')
        size = abs(float(size_raw)) if size_raw is not None else 0.0
        entry_px = float(entry_raw) if entry_raw is not None else 0.0
    except Exception as e:
        print('parse pos failed', e)
        return

    if size <= 0 or entry_px <= 0:
        print('Invalid position size/entry', size, entry_px)
        return

    pos_side = 'short' if float(found.get('size', 0)) < 0 else 'long'
    entry_side = 'sell' if pos_side == 'short' else 'buy'
    close_side = 'buy' if entry_side == 'sell' else 'sell'

    print(f'Position detected: side={pos_side} entry_side={entry_side} size={size} entry={entry_px}')

    # Fetch candles from OKX (fallback) to compute lookback SL
    desired = max(300, SETTINGS.rsi_max_data + SETTINGS.rsi_length + 2)
    try:
        candles = await asyncio.to_thread(fetch_candles_paged, SETTINGS.okx_base_url, INST_ID, TF, desired)
    except Exception as e:
        print('fetch_candles_paged failed', e)
        candles = []

    sl = None
    try:
        lookback = get_lookback_bars(TF)
        sl = stop_loss_price_lookback(
            side=entry_side,
            entry_price=entry_px,
            candles=candles,
            lookback_bars=lookback,
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    except Exception as e:
        print('sl compute error', e)

    if sl is None:
        # fallback 2% from entry
        if entry_side == 'sell':
            sl = entry_px * 1.02
        else:
            sl = entry_px * 0.98
        print('Using fallback SL', sl)
    else:
        print('Computed SL', sl)

    tp = take_profit_price(side=entry_side, entry_price=entry_px, stop_loss=sl, rr=1.5)
    print('Computed TP', tp)

    # Round to market tick
    market = client.api.markets.get(sym) or {}
    tick = market.get('tick_size') or market.get('min_price') or market.get('pricePrecision') or '0.000000001'
    try:
        t = Decimal(str(tick))
        sl_rd = (Decimal(str(sl)) / t).to_integral_value(rounding=ROUND_DOWN) * t
        tp_rd = (Decimal(str(tp)) / t).to_integral_value(rounding=ROUND_DOWN) * t if tp is not None else None
    except Exception:
        sl_rd = Decimal(str(sl))
        tp_rd = Decimal(str(tp)) if tp is not None else None

    print('Rounded SL', str(sl_rd), 'Rounded TP', str(tp_rd))

    # Place conditional orders via API (attempt via wrapper first)
    try:
        resp = await client.place_algo_order(
            inst_id=INST_ID,
            td_mode=SETTINGS.okx_td_mode,
            side=close_side,
            pos_side=pos_side,
            ord_type='conditional',
            sz=str(size),
            sl_trigger_px=str(sl_rd),
            sl_ord_px='-1',
            tp_trigger_px=str(tp_rd) if tp_rd is not None else None,
            tp_ord_px='-1' if tp_rd is not None else None,
        )
        print('place_algo_order resp:', json.dumps(resp, ensure_ascii=False))
    except Exception as e:
        print('place_algo_order exception', e)

    # If wrapper failed, try direct create_order with params including reduce_only
    try:
        params = {
            'stopLossPrice': float(sl_rd),
            'takeProfitPrice': float(tp_rd) if tp_rd is not None else None,
            'reduce_only': True,
        }
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        create_resp = await client.api.create_order(
            symbol=sym,
            order_type='limit',
            side=close_side,
            amount=Decimal(str(size)),
            price=float(sl_rd),
            params=params,
        )
        print('direct create_order resp:', json.dumps(create_resp, ensure_ascii=False, default=str))
    except Exception as e:
        print('direct create_order exception', e)


if __name__ == '__main__':
    asyncio.run(run())
