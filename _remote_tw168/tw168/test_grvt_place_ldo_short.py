#!/usr/bin/env python3
"""
Place a real short on LDO using GRVT client following the repository's risk logic.
Risk per trade: 100 USDT (fixed for this run)
This will place a market entry, then an algo stop-loss and take-profit.

CONFIRMATION: You already confirmed "确认下单".
"""

import asyncio
import os
import time
from decimal import Decimal, ROUND_DOWN
from dotenv import load_dotenv

load_dotenv('.env')

from app.grvt import GrvtClient, GrvtCredentials
from app.config import SETTINGS, get_lookback_bars
from app.risk import fetch_candles_paged, stop_loss_price_lookback, take_profit_price

RISK_USDT = 100.0
TF = os.getenv('TRADE_TF', '15m')
INST_ID = 'LDO-USDT-SWAP'

async def main():
    creds = GrvtCredentials(
        api_key=os.getenv('GRVT_API_KEY'),
        private_key=os.getenv('GRVT_PRIVATE_KEY'),
        trading_account_id=os.getenv('GRVT_TRADING_ACCOUNT_ID'),
    )
    client = GrvtClient(os.getenv('GRVT_BASE_URL', 'https://api.grvt.io'), creds)

    print('Connecting to GRVT...')
    await client.connect()
    print('Connected')

    # 1) Get current market price
    entry_price = await client.get_last_price(inst_id=INST_ID)
    if entry_price is None:
        print('Failed to fetch entry price')
        return
    print('Entry price:', entry_price)

    # 2) Fetch candles and compute stop-loss using lookback
    desired = max(300, SETTINGS.rsi_max_data + SETTINGS.rsi_length + 2)
    try:
        candles = await asyncio.to_thread(fetch_candles_paged, SETTINGS.okx_base_url, INST_ID, TF, desired)
    except Exception as e:
        print('Failed to fetch candles:', e)
        candles = []

    sl = None
    try:
        lookback = get_lookback_bars(TF)
        sl = stop_loss_price_lookback(
            side='sell',
            entry_price=float(entry_price),
            candles=candles,
            lookback_bars=lookback,
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    except Exception as e:
        print('SL calc error:', e)
        sl = None

    if sl is None:
        # Fallback: 2% stop distance above entry for short
        sl = float(entry_price) * 1.02
        print('Using fallback SL:', sl)
    else:
        print('Calculated SL:', sl)

    # Validate SL > entry for short
    if not (sl > entry_price):
        print('Computed SL is not above entry. Aborting.')
        return

    # 3) Compute r_value and size
    r_value = abs(entry_price - sl)
    if r_value <= 0:
        print('Invalid risk distance r_value=', r_value)
        return

    inst_info = await client.get_instrument_info(inst_id=INST_ID)
    ct_val = float(inst_info.get('ctVal') or 1.0) if inst_info else 1.0
    lot_step = Decimal(str(inst_info.get('lotStep'))) if inst_info and inst_info.get('lotStep') else Decimal('1')
    min_order = Decimal(str(inst_info.get('lotSz'))) if inst_info and inst_info.get('lotSz') else Decimal('1')

    # contracts = risk_usdt / r_value / ct_val
    contracts = Decimal(str(RISK_USDT)) / Decimal(str(r_value)) / Decimal(str(ct_val))
    # normalize to step
    qty = (contracts / lot_step).to_integral_value() * lot_step
    if qty < min_order:
        qty = min_order

    sz = str(qty)
    print('Computed size (contracts):', sz)

    # 4) Place market short
    ts = int(time.time() * 1000)
    # GRVT expects numeric client_order_id in metadata - use ms timestamp
    cl_ord_id = str(ts)
    print('Placing market short...', INST_ID, 'sz=', sz)
    resp = await client.place_order(
        inst_id=INST_ID,
        td_mode=SETTINGS.okx_td_mode,
        side='sell',
        pos_side='short',
        ord_type='market',
        sz=sz,
        px=None,
        cl_ord_id=cl_ord_id,
        sl_trigger_px=None,
        tp_trigger_px=None,
        reduce_only=False,
    )
    print('Entry response:', resp)

    # 5) Place SL and TP as algo orders
    # SL: trigger at sl price (market), TP: take profit at 1.5R
    tp_price = take_profit_price(side='sell', entry_price=float(entry_price), stop_loss=float(sl), rr=1.5)
    if tp_price is None:
        print('Failed to compute TP price')
        tp_price = None
    else:
        print('TP price:', tp_price)

    # Round SL/TP to instrument tick (use market metadata from client.api)
    sym = client._normalize_symbol(INST_ID)
    market = client.api.markets.get(sym) or {}
    tick = market.get('tick_size') or inst_info.get('tickSz') if inst_info else None
    try:
        if tick:
            t = Decimal(str(tick))
            sl_rd = (Decimal(str(sl)) / t).to_integral_value(rounding=ROUND_DOWN) * t
            tp_rd = (Decimal(str(tp_price)) / t).to_integral_value(rounding=ROUND_DOWN) * t if tp_price is not None else None
        else:
            sl_rd = Decimal(str(sl))
            tp_rd = Decimal(str(tp_price)) if tp_price is not None else None
    except Exception:
        sl_rd = Decimal(str(sl))
        tp_rd = Decimal(str(tp_price)) if tp_price is not None else None

    print('Placing algorithmic SL/TP...')
    algo_resp = await client.place_algo_order(
        inst_id=INST_ID,
        td_mode=SETTINGS.okx_td_mode,
        side='sell',
        pos_side='short',
        ord_type='conditional',
        sz=sz,
        sl_trigger_px=str(sl_rd),
        sl_ord_px='-1',
        tp_trigger_px=str(tp_rd) if tp_rd is not None else None,
        tp_ord_px='-1' if tp_rd is not None else None,
    )
    print('Algo response:', algo_resp)

if __name__ == '__main__':
    asyncio.run(main())
