#!/usr/bin/env python3
import asyncio
import sys
from dotenv import load_dotenv
from app.grvt import GrvtClient, GrvtCredentials
import os
from datetime import datetime, timezone

load_dotenv()

def _fmt_ts_ns(ns: str | int | None) -> str:
    if ns is None:
        return "N/A"
    try:
        ns_i = int(ns)
        dt = datetime.fromtimestamp(ns_i / 1_000_000_000, tz=timezone.utc)
        return dt.isoformat()
    except Exception:
        return str(ns)


async def main():
    client = GrvtClient(
        os.getenv("GRVT_BASE_URL", "https://api.grvt.io"),
        GrvtCredentials(
            api_key=os.getenv("GRVT_API_KEY", ""),
            private_key=os.getenv("GRVT_PRIVATE_KEY", ""),
            trading_account_id=os.getenv("GRVT_TRADING_ACCOUNT_ID", ""),
        ),
    )
    await client.connect()

    print("="*60)
    print("检查GRVT当前所有挂单状态")
    print("="*60)

    try:
        # 获取所有挂单
        open_orders = await client.api.fetch_open_orders(None)
        print(f"\n当前挂单总数: {len(open_orders) if open_orders else 0}")
        if open_orders:
            print("（如需排查来源，可把下面每条的 instrument/price/size/client_order_id/create_time 发我）")

        if open_orders:
            for i, order in enumerate(open_orders, start=1):
                legs = order.get("legs") or []
                leg0 = legs[0] if legs else {}
                instrument = leg0.get("instrument", "N/A")
                limit_price = leg0.get("limit_price", "N/A")
                size = leg0.get("size", "N/A")
                is_buying_asset = leg0.get("is_buying_asset")
                side = "buy" if is_buying_asset is True else ("sell" if is_buying_asset is False else "N/A")

                meta = order.get("metadata") or {}
                print(f"\n订单 {i}:")
                print(f"  order_id: {order.get('order_id', 'N/A')}")
                print(f"  client_order_id: {meta.get('client_order_id', 'N/A')}")
                print(f"  create_time(UTC): {_fmt_ts_ns(meta.get('create_time'))}")
                print(f"  status: {(order.get('state') or {}).get('status', 'N/A')}")
                print(f"  instrument: {instrument}")
                print(f"  side: {side}")
                print(f"  size: {size}")
                print(f"  limit_price: {limit_price}")
                print(f"  is_market: {order.get('is_market', 'N/A')}")
                print(f"  reduce_only: {order.get('reduce_only', 'N/A')}")
        else:
            print("当前没有挂单")

    except Exception as e:
        print(f"❌ 获取挂单失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*60)
    print("检查当前仓位")
    print("="*60)

    try:
        positions = await client.api.fetch_positions(None)
        print(f"\n当前仓位: {positions}")
        if positions:
            for pos in positions:
                print(f"  {pos.get('symbol', pos.get('instrument', 'N/A'))}: {pos.get('contracts', pos.get('size', 0))}")
    except Exception as e:
        print(f"❌ 获取仓位失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
