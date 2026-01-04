#!/usr/bin/env python3
import asyncio
import sys
from dotenv import load_dotenv
from app.grvt import GrvtClient, GrvtCredentials
import os

load_dotenv()

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
        print(f"\n原始open_orders数据: {open_orders}\n")

        if open_orders:
            print(f"当前挂单总数: {len(open_orders)}")
            for i, order in enumerate(open_orders):
                print(f"\n订单 {i+1}:")
                print(f"  ID: {order.get('id', 'N/A')}")
                print(f"  外部ID: {order.get('external_id', 'N/A')}")
                print(f"  Symbol: {order.get('symbol', order.get('instrument', 'N/A'))}")
                print(f"  Side: {order.get('side', 'N/A')}")
                print(f"  Size: {order.get('amount', order.get('size', 'N/A'))}")
                print(f"  Price: {order.get('price', 'N/A')}")
                print(f"  Status: {order.get('status', 'N/A')}")
                print(f"  Type: {order.get('type', 'N/A')}")
                print(f"  Reduce Only: {order.get('reduce_only', 'N/A')}")
                print(f"  时间戳: {order.get('timestamp', 'N/A')}")
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
