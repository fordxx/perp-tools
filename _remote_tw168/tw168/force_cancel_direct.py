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
    print("直接调用API取消所有订单")
    print("="*60)

    try:
        # 获取所有挂单
        open_orders = await client.api.fetch_open_orders(None)
        print(f"当前共有 {len(open_orders)} 个挂单\n")

        if open_orders:
            for i, order in enumerate(open_orders):
                order_id = order.get('order_id')
                client_order_id = order.get('metadata', {}).get('client_order_id', 'N/A')
                size = order.get('legs', [{}])[0].get('size', 'N/A')
                status = order.get('state', {}).get('status', 'N/A')
                
                print(f"订单 {i+1}:")
                print(f"  Order ID: {order_id}")
                print(f"  Client ID: {client_order_id}")
                print(f"  Size: {size}")
                print(f"  Status: {status}")

                # 直接调用API cancel_order方法
                try:
                    if order_id:
                        # API期望client_order_id而不是order_id
                        result = await client.api.cancel_order(
                            symbol="LDO_USDT_Perp", 
                            id=order_id,
                            params={"trading_account_id": client.trading_account_id}
                        )
                        print(f"  ✅ 取消结果: {result}")
                    else:
                        print(f"  ⚠️ 无法取消：order_id为空")
                except Exception as e:
                    print(f"  ❌ 取消失败: {e}")
                print()

    except Exception as e:
        print(f"❌ 获取挂单失败: {e}")
        import traceback
        traceback.print_exc()

    print("="*60)
    print("重新检查当前挂单状态")
    print("="*60)

    try:
        await asyncio.sleep(2)
        open_orders = await client.api.fetch_open_orders(None)
        print(f"当前还有 {len(open_orders)} 个挂单")
        if open_orders:
            print("⚠️ 还有未取消的订单")
            for order in open_orders:
                client_id = order.get('metadata', {}).get('client_order_id')
                print(f"  Client ID: {client_id}")
        else:
            print("✅ 所有订单已取消")
    except Exception as e:
        print(f"❌ 检查失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
