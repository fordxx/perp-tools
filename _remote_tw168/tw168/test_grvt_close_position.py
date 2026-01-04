#!/usr/bin/env python3
from __future__ import annotations
import os
import asyncio
from dotenv import load_dotenv
from app.grvt import GrvtClient, GrvtCredentials

load_dotenv()

API_KEY = os.getenv("GRVT_API_KEY")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY")
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

async def main():
    creds = GrvtCredentials(api_key=API_KEY, private_key=API_SECRET, trading_account_id=TRADING_ACCOUNT)
    client = GrvtClient(BASE_URL, creds)
    await client.connect()

    inst_id = "LDO_USDT_Perp"

    print(f"交易账户ID: {TRADING_ACCOUNT}")
    print("正在平掉当前仓位...")

    # 先取消所有挂单
    print("正在取消所有挂单...")
    try:
        await client.cancel_all_orders(inst_id=inst_id)
        print("✅ 已取消所有挂单")
    except Exception as e:
        print(f"取消挂单失败: {e}")

    await asyncio.sleep(2)

    # 检查当前仓位
    try:
        positions = await client.api.fetch_positions(params={"trading_account_id": TRADING_ACCOUNT})
        print(f"所有仓位: {[pos.get('instrument') for pos in positions]}")
        ldo_position = None
        for pos in positions:
            if pos.get('instrument') == inst_id:
                ldo_position = pos
                break

        if ldo_position:
            size = float(ldo_position.get('size', 0))
            print(f"当前仓位: {size} {inst_id}")
            if size >= 0:
                print("当前是多头仓位，无需平仓")
                return
        else:
            print("未找到LDO仓位")
            return

    except Exception as e:
        print(f"获取仓位失败: {e}")
        return

    # 平仓：空头仓位需要买单来平仓
    # size是负数（空头），我们需要下正数的买单来平仓
    close_size = abs(size)  # 取绝对值作为平仓数量

    # 获取当前市场价格
    try:
        # 尝试不同的ticker获取方式
        ticker = await client.api.fetch_ticker("LDO_USDT_Perp")
        print(f"原始ticker数据: {ticker}")
        current_price = float(ticker.get("last_price", 0)) if ticker else 0
        if current_price == 0:
            # 尝试其他价格字段
            current_price = float(ticker.get("last", 0)) if ticker else 0
        print(f"解析的市场价: {current_price}")
    except Exception as e:
        print(f"获取市场价失败: {e}")
        current_price = 0

    print(f"将下限价买单平仓，数量: {close_size}")

    # 如果获取不到市场价，使用一个高价来确保成交
    if current_price <= 0:
        current_price = 10.0  # 使用一个足够高的价格
        print(f"使用默认高价: {current_price}")

    # 如果获取不到市场价，使用一个高价来确保成交
    if current_price <= 0:
        current_price = 10.0  # 使用一个足够高的价格
        print(f"使用默认高价: {current_price}")

    try:
        # 使用限价单，价格设为当前价的1.01倍确保成交
        limit_price = current_price * 1.01 if current_price > 0 else 0.62
        print(f"使用限价: {limit_price}")

        # 使用包装器方法下单
        resp = await client.place_order(
            inst_id=inst_id,
            td_mode="cross",
            side="buy",  # 买单平空头
            pos_side="short",
            ord_type="limit",
            sz=str(close_size),
            px=str(limit_price),  # 限价
            cl_ord_id=str(int(asyncio.get_event_loop().time())),
            reduce_only=True,  # 只减仓
        )

        if str(resp.get("code", "")) in {"0", "success"}:
            print("✅ 平仓订单提交成功")
            print(f"响应: {resp}")

            # 获取订单ID用于后续检查
            order_data = resp.get("data", [{}])[0]
            cl_ord_id = order_data.get("clOrdId", str(int(asyncio.get_event_loop().time())))

            # 等待更长时间让订单成交
            await asyncio.sleep(10)

            # 检查是否有挂单
            try:
                open_orders = await client.api.fetch_open_orders(symbol="LDO_USDT_Perp", params={"trading_account_id": TRADING_ACCOUNT})
                print(f"当前挂单数量: {len(open_orders)}")
                for order in open_orders:
                    print(f"  挂单: {order.get('id')} {order.get('side')} {order.get('amount')} @ {order.get('price')}")
            except Exception as e:
                print(f"检查挂单失败: {e}")

            # 再次检查仓位确认平仓

            # 再次检查仓位确认平仓
            try:
                positions_after = await client.api.fetch_positions(params={"trading_account_id": TRADING_ACCOUNT})
                ldo_position_after = None
                for pos in positions_after:
                    if pos.get('instrument') == inst_id:
                        ldo_position_after = pos
                        break

                if ldo_position_after:
                    size_after = float(ldo_position_after.get('size', 0))
                    print(f"平仓后仓位: {size_after} {inst_id}")
                    if abs(size_after) < 0.001:  # 几乎为0
                        print("✅ 仓位已完全平掉")
                    else:
                        print(f"⚠️ 仍有残余仓位: {size_after}")
                else:
                    print("✅ 仓位已完全平掉")

            except Exception as e:
                print(f"检查平仓结果失败: {e}")

        else:
            print(f"❌ 平仓订单失败: {resp}")

    except Exception as e:
        print(f"❌ 平仓异常: {e}")

if __name__ == "__main__":
    asyncio.run(main())