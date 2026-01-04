#!/usr/bin/env python3
from __future__ import annotations
import os
import json
import asyncio
from app.grvt import GrvtClient, GrvtCredentials

API_KEY = os.getenv("GRVT_API_KEY")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY")
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

# Known client_order_ids / ordIds observed
CLIENT_ORDER_IDS = ["2111599471", "961204888", "2034688839", "2812317874", "3706547850"]
ORD_IDS = []


async def try_call_async(obj, name, *args, **kwargs):
    fn = getattr(obj, name, None)
    if not callable(fn):
        return (False, f"no method {name}")
    try:
        res = fn(*args, **kwargs)
        if asyncio.iscoroutine(res):
            res = await res
        return (True, res)
    except Exception as e:
        return (False, repr(e))


async def main_async():
    creds = GrvtCredentials(api_key=API_KEY, private_key=API_SECRET, trading_account_id=TRADING_ACCOUNT)
    try:
        client = GrvtClient(BASE_URL, creds)
    except Exception as e:
        print("client init failed:", e)
        return

    try:
        conn_res = client.connect()
        if asyncio.iscoroutine(conn_res):
            await conn_res
    except Exception as e:
        print("connect failed:", e)

    api = getattr(client, "api", None) or client

    print("\n-- Candidate API methods --")
    methods = [m for m in dir(api) if ("order" in m or "ord" in m or "trade" in m or "fetch" in m or "history" in m) and not m.startswith("_")]
    methods = sorted(set(methods))
    for m in methods:
        print(m)

    # Debug: show api internal parameter storage
    print("\n-- API internal attrs (parameters/options) --")
    for attr in ("parameters", "params", "options", "_parameters", "_params"):
        try:
            print(attr, getattr(api, attr, None))
        except Exception as e:
            print(attr, "ERR", e)

    print("\n-- Query wrapper get_order for known client_order_id values (LDO) --")
    inst = "LDO-USDT-SWAP"
    for coid in CLIENT_ORDER_IDS:
        ok, res = await try_call_async(client, "get_order", inst_id=inst, cl_ord_id=coid)
        if ok:
            print(f"client.get_order cl_ord_id={coid} ->", json.dumps(res, indent=2, ensure_ascii=False, default=str) if res else "None")
        else:
            print(f"client.get_order cl_ord_id={coid} -> ERR: {res}")

    print("\n-- Try different param keys for api.fetch_order (raw api) --")
    candidate_keys = [
        "trading_account_id",
        "tradingAccountId",
        "tradingAccount",
        "account_id",
        "accountId",
        "investor_id",
        "trader",
    ]
    test_coid = CLIENT_ORDER_IDS[0]
    for candidate in candidate_keys:
        params = {"client_order_id": test_coid, candidate: TRADING_ACCOUNT}
        ok, res = await try_call_async(api, "fetch_order", params=params)
        print(f"api.fetch_order with {candidate}: {'OK' if ok else 'ERR'} -> {res}")

    print("\n-- Try get_order / get_orders / fetch_open_orders --")
    for name in ("get_order", "get_orders", "fetch_orders", "fetch_open_orders", "get_open_orders", "orders_history", "get_orders_history"):
        ok, res = await try_call_async(api, name)
        print(f"{name}: {'OK' if ok else 'NO'} -> {res if not ok else 'returned'}")

    print("\n-- get_open_orders for instrument LDO --")
    ok, open_orders = await try_call_async(client, "get_open_orders", inst_id=inst)
    if ok and isinstance(open_orders, list):
        for o in open_orders:
            try:
                print(json.dumps(o, indent=2, ensure_ascii=False, default=str))
            except Exception:
                print(repr(o))
    else:
        print("client.get_open_orders failed:", open_orders)

    print("\n-- get_position for LDO (long/short) --")
    ok_long, pos_long = await try_call_async(client, "get_position", inst_id=inst, pos_side="long")
    ok_short, pos_short = await try_call_async(client, "get_position", inst_id=inst, pos_side="short")
    if ok:
        pass
    print("long:", pos_long)
    print("short:", pos_short)


def main():
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
