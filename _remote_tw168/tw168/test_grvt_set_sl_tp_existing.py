#!/usr/bin/env python3
"""
Find existing LDO position and place stop-loss + take-profit (1.5R) via GRVT.
"""
import asyncio
import os
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

load_dotenv('.env')

from app.grvt import GrvtClient, GrvtCredentials
from app.config import SETTINGS, get_lookback_bars
from app.risk import fetch_candles_paged, stop_loss_price_lookback, take_profit_price

INST_ID = 'LDO-USDT-SWAP'
TF = os.getenv('TRADE_TF', '15m')

async def main():
    creds = GrvtCredentials(api_key=os.getenv('GRVT_API_KEY'), private_key=os.getenv('GRVT_PRIVATE_KEY'), trading_account_id=os.getenv('GRVT_TRADING_ACCOUNT_ID'))
    client = GrvtClient(os.getenv('GRVT_BASE_URL', 'https://api.grvt.io'), creds)
    await client.connect()

    # Try get existing position (short or long)
    pos = await client.get_position(inst_id=INST_ID, pos_side='short')
    if pos is None:
        pos = await client.get_position(inst_id=INST_ID, pos_side='long')
    if pos is None:
        print('No existing position found for', INST_ID)
        return

    print('Found position:', pos)
    pos_side = pos.get('posSide')
    side = 'buy' if pos_side == 'long' else 'sell'
    entry_px = float(pos.get('avgPx') or pos.get('open_price') or 0)
    size = Decimal(str(pos.get('pos') or '0'))

    if size <= 0 or entry_px <= 0:
        print('Invalid position size or entry price')
        return

    # Fetch candles to compute lookback SL
    desired = max(300, SETTINGS.rsi_max_data + SETTINGS.rsi_length + 2)
    try:
        candles = await asyncio.to_thread(fetch_candles_paged, SETTINGS.okx_base_url, INST_ID, TF, desired)
    except Exception:
        candles = []

    sl = None
    try:
        lookback = get_lookback_bars(TF)
        sl = stop_loss_price_lookback(
            side=side,
            entry_price=entry_px,
            candles=candles,
            lookback_bars=lookback,
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    except Exception:
        sl = None

    if sl is None:
        # fallback: 2% from entry
        if side == 'sell':
            sl = entry_px * 1.02
        else:
            sl = entry_px * 0.98
        print('Using fallback SL:', sl)
    else:
        print('Computed SL:', sl)

    # Compute TP at 1.5R
    tp = take_profit_price(side=side, entry_price=entry_px, stop_loss=sl, rr=1.5)
    print('Computed TP:', tp)

    # Round SL/TP to market tick
    sym = client._normalize_symbol(INST_ID)
    market = client.api.markets.get(sym) or {}
    tick = market.get('tick_size') or market.get('tickSz') or '0.000000001'
    try:
        t = Decimal(str(tick))
        sl_rd = (Decimal(str(sl)) / t).to_integral_value(rounding=ROUND_DOWN) * t
        tp_rd = (Decimal(str(tp)) / t).to_integral_value(rounding=ROUND_DOWN) * t if tp is not None else None
    except Exception:
        sl_rd = Decimal(str(sl))
        tp_rd = Decimal(str(tp)) if tp is not None else None

    print('Rounded SL:', str(sl_rd), 'Rounded TP:', str(tp_rd))

    # Place algo order to attach SL and TP
    cl_ord = str(int(asyncio.get_event_loop().time() * 1000))
    resp = await client.place_algo_order(
        inst_id=INST_ID,
        td_mode=SETTINGS.okx_td_mode,
        side=side,
        pos_side=pos_side,
        ord_type='conditional',
        sz=str(size),
        sl_trigger_px=str(sl_rd),
        sl_ord_px='-1',
        tp_trigger_px=str(tp_rd) if tp_rd is not None else None,
        tp_ord_px='-1' if tp_rd is not None else None,
    )

    print('place_algo_order response:', resp)

if __name__ == '__main__':
    asyncio.run(main())
