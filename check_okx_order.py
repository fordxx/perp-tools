#!/usr/bin/env python3
"""查询 OKX 订单详情和持仓"""
import os
import sys
from dotenv import load_dotenv
from src.perpbot.exchanges.okx import OKXClient

# 加载环境变量
env_file = ".env.tv168" if os.path.exists(".env.tv168") else ".env"
load_dotenv(env_file)

# 从环境变量读取配置
okx_env = os.getenv("OKX_ENV", "testnet").lower()
use_testnet = okx_env in ["testnet", "test"]

print("=" * 70)
print("OKX 账户状态查询")
print("=" * 70)
print(f"环境: {okx_env}")
print()

# 连接 OKX
okx = OKXClient(use_testnet=use_testnet, allow_mainnet=True)
okx.connect()

if not okx._trading_enabled:
    print("❌ OKX 未连接")
    sys.exit(1)

print("✅ OKX 已连接")
print()

# 查询特定订单（如果提供了订单 ID）
if len(sys.argv) > 1:
    order_id = sys.argv[1]
    print(f"查询订单 ID: {order_id}")
    print("-" * 70)
    try:
        order_detail = okx.exchange.fetch_order(order_id, symbol="SOL/USDT:USDT")
        print(f"  订单 ID: {order_detail['id']}")
        print(f"  交易对: {order_detail['symbol']}")
        print(f"  方向: {order_detail['side']}")
        print(f"  类型: {order_detail['type']}")
        print(f"  状态: {order_detail['status']}")
        print(f"  数量: {order_detail.get('amount', 'N/A')}")
        print(f"  成交数量: {order_detail.get('filled', 'N/A')}")
        print(f"  成交均价: {order_detail.get('average', 'N/A')}")
        print(f"  成交价: {order_detail.get('price', 'N/A')}")
        print(f"  时间: {order_detail.get('datetime', 'N/A')}")
        print()
    except Exception as e:
        print(f"❌ 查询订单失败: {e}")
        print()

# 查询当前持仓
print("查询当前持仓...")
print("-" * 70)
try:
    positions = okx.exchange.fetch_positions()
    sol_positions = [p for p in positions if 'SOL' in p.get('symbol', '')]

    if sol_positions:
        for pos in sol_positions:
            print(f"  交易对: {pos.get('symbol', 'N/A')}")
            print(f"  方向: {pos.get('side', 'N/A')}")
            print(f"  数量: {pos.get('contracts', pos.get('contractSize', 'N/A'))}")
            print(f"  持仓价值: {pos.get('notional', 'N/A')} USDT")
            print(f"  开仓均价: {pos.get('entryPrice', 'N/A')}")
            print(f"  未实现盈亏: {pos.get('unrealizedPnl', 'N/A')} USDT")
            print(f"  杠杆: {pos.get('leverage', 'N/A')}x")
            print()
    else:
        print("  ⚠️ 没有 SOL 持仓")
        print()

    print(f"总持仓数: {len(positions)}")
    if len(positions) > 0 and not sol_positions:
        print("其他持仓:")
        for pos in positions[:5]:  # 只显示前 5 个
            if pos.get('contracts', 0) != 0:
                print(f"  - {pos.get('symbol', 'N/A')}: {pos.get('side', 'N/A')} {pos.get('contracts', 'N/A')}")

except Exception as e:
    print(f"❌ 查询持仓失败: {e}")
    import traceback
    traceback.print_exc()

print()

# 查询最近订单历史
print("查询最近订单...")
print("-" * 70)
try:
    orders = okx.exchange.fetch_orders(symbol="SOL/USDT:USDT", limit=5)
    if orders:
        for order in orders:
            print(f"  [{order['datetime']}] {order['side'].upper()} {order.get('filled', 0)} SOL")
            print(f"    ID: {order['id']} | 状态: {order['status']} | 均价: {order.get('average', 'N/A')}")
            print()
    else:
        print("  ⚠️ 没有最近订单")
except Exception as e:
    print(f"❌ 查询订单历史失败: {e}")

print("=" * 70)
