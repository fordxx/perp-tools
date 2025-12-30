#!/usr/bin/env python3
"""OKX SOL/USDT 主网下单测试"""
import os
from dotenv import load_dotenv
from src.perpbot.exchanges.okx import OKXClient
from src.perpbot.models import OrderRequest

# 加载环境变量
env_file = ".env.tv168" if os.path.exists(".env.tv168") else ".env"
load_dotenv(env_file)

# 从环境变量读取配置
okx_env = os.getenv("OKX_ENV", "testnet").lower()
use_testnet = okx_env in ["testnet", "test"]
order_size = float(os.getenv("PERPBOT_TV_ORDER_SIZE", "0.1"))
hedge_mode = os.getenv("PERPBOT_TV_HEDGE_MODE", "true").lower() in {"1", "true", "yes", "y", "on"}
place_sl = os.getenv("PERPBOT_TV_PLACE_STOP_LOSS", "true").lower() in {"1", "true", "yes", "y", "on"}

print("=" * 70)
print("SOL/USDT OKX 主网下单测试")
print("=" * 70)
print(f"📊 环境: {okx_env} (use_testnet={use_testnet})")
print(f"📊 订单大小: {order_size} SOL")
print(f"📊 双向持仓: {hedge_mode}")
print(f"📊 自动止损: {place_sl}")
print()

if not use_testnet:
    print("⚠️ ⚠️ ⚠️ 警告：即将使用真实资金下单！⚠️ ⚠️ ⚠️")
    print("请确认：")
    print(f"  1. 订单大小: {order_size} SOL")
    print("  2. 双向持仓模式: {hedge_mode}")
    print("  3. 你理解这将使用真实资金")
    print()
    confirmation = input("输入 'YES' 继续，其他键取消: ")
    if confirmation != "YES":
        print("❌ 已取消")
        exit(0)
    print()

# 初始化 OKX 客户端
print("连接 OKX...")
okx = OKXClient(use_testnet=use_testnet, allow_mainnet=True)
okx.connect()

if not okx._trading_enabled:
    print("❌ OKX 交易未启用，请检查 API KEY/SECRET/PASSPHRASE 配置")
    exit(1)

print("✅ OKX 连接成功")
print()

# 查询当前余额
try:
    print("查询账户余额...")
    balance = okx.get_balance()
    print(f"  USDT 余额: {balance.total_usdt:.2f} USDT (可用: {balance.free_usdt:.2f})")
    print()
except Exception as e:
    print(f"⚠️ 余额查询失败: {e}")
    print()

# 查询 SOL 当前价格
try:
    print("查询 SOL/USDT 价格...")
    price_quote = okx.get_current_price("SOL/USDT")
    print(f"  买一价: {price_quote.ask}")
    print(f"  卖一价: {price_quote.bid}")
    print(f"  中间价: {(price_quote.ask + price_quote.bid) / 2:.2f}")

    # 计算订单价值
    order_value = order_size * price_quote.ask
    print(f"  订单价值: {order_value:.2f} USDT ({order_size} SOL @ {price_quote.ask})")
    print()
except Exception as e:
    print(f"❌ 价格查询失败: {e}")
    exit(1)

# 下单参数
symbol = "SOL/USDT"
side = "buy"  # 做多

print(f"准备下单:")
print(f"  交易对: {symbol}")
print(f"  方向: {side} (做多)")
print(f"  数量: {order_size} SOL")
print(f"  预估成本: {order_value:.2f} USDT")
print(f"  双向持仓: {hedge_mode}")
print()

if not use_testnet:
    final_confirm = input("⚠️ 最后确认：输入 'EXECUTE' 下单，其他键取消: ")
    if final_confirm != "EXECUTE":
        print("❌ 已取消")
        exit(0)
    print()

# 下单
try:
    print("⏳ 下单中...")
    order_req = OrderRequest(symbol=symbol, side=side, size=order_size, limit_price=None)
    order = okx.place_open_order(order_req, hedge_mode=hedge_mode)

    print()
    print("=" * 70)
    print("✅ 下单成功！")
    print("=" * 70)
    print(f"订单 ID: {order.id}")
    print(f"交易对: {order.symbol}")
    print(f"方向: {order.side}")
    print(f"数量: {order.size} SOL")
    print(f"成交价: {order.price}")
    print(f"时间: {order.created_at}")

    if order.id.startswith("error-"):
        print()
        print("❌ 订单失败（返回了错误 ID）")
        print("请检查日志获取详细错误信息")
    else:
        print()
        print("🌐 请登录 OKX 验证：")
        print("  https://www.okx.com/trade-swap/sol-usdt-swap")
        print("  1. 持仓页面：应该有 SOL-USDT-SWAP 多仓")
        print("  2. 订单历史：查看成交记录")

        if place_sl:
            print()
            print("⚠️ 注意：自动止损功能需要在下单后单独调用")
            print("   当前测试脚本仅测试开仓订单")

except Exception as e:
    print()
    print("=" * 70)
    print("❌ 下单失败")
    print("=" * 70)
    print(f"错误: {e}")
    import traceback
    print()
    print("详细错误:")
    traceback.print_exc()
