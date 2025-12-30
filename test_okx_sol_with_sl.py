#!/usr/bin/env python3
"""OKX SOL/USDT 完整测试：开仓 + 止损单"""
import os
import sys
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
print("SOL/USDT 完整测试：开仓 + 止损单")
print("=" * 70)
print(f"📊 环境: {okx_env} (use_testnet={use_testnet})")
print(f"📊 订单大小: {order_size} SOL")
print(f"📊 双向持仓: {hedge_mode}")
print(f"📊 自动止损: {place_sl}")
print()

if not use_testnet:
    print("⚠️ ⚠️ ⚠️ 警告：将使用真实资金下单！⚠️ ⚠️ ⚠️")
    print(f"  订单大小: {order_size} SOL")
    print(f"  双向持仓: {hedge_mode}")
    print(f"  自动止损: {place_sl}")
    print()

# 初始化 OKX 客户端
print("Step 1: 连接 OKX...")
print("-" * 70)
try:
    okx = OKXClient(use_testnet=use_testnet, allow_mainnet=True)
    okx.connect()
except Exception as e:
    print(f"❌ OKX 初始化失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

if not okx._trading_enabled:
    print("❌ OKX 交易未启用")
    sys.exit(1)

print("✅ OKX 连接成功")
print()

# 查询 SOL 当前价格
print("Step 2: 查询 SOL/USDT 价格...")
print("-" * 70)
try:
    price_quote = okx.get_current_price("SOL/USDT")
    current_price = (price_quote.ask + price_quote.bid) / 2
    print(f"  买一价: {price_quote.ask}")
    print(f"  卖一价: {price_quote.bid}")
    print(f"  中间价: {current_price:.2f}")

    order_value = order_size * price_quote.ask
    print(f"  订单价值: {order_value:.2f} USDT")
    print()
except Exception as e:
    print(f"❌ 价格查询失败: {e}")
    sys.exit(1)

# 计算止损价（示例：当前价格下方 2%）
sl_percentage = 0.02  # 2%
stop_loss_price = current_price * (1 - sl_percentage)
print(f"Step 3: 计算止损价")
print("-" * 70)
print(f"  当前价格: {current_price:.2f} USDT")
print(f"  止损比例: {sl_percentage * 100}%")
print(f"  止损价格: {stop_loss_price:.2f} USDT")
print(f"  风险金额: {(current_price - stop_loss_price) * order_size:.2f} USDT")
print()

# 下单参数
symbol = "SOL/USDT"
side = "buy"  # 做多

print(f"Step 4: 下开仓单")
print("-" * 70)
print(f"  交易对: {symbol}")
print(f"  方向: {side} (做多)")
print(f"  数量: {order_size} SOL")
print(f"  预估成本: {order_value:.2f} USDT")
print()

# 下开仓单
try:
    print("⏳ 下单中...")
    order_req = OrderRequest(symbol=symbol, side=side, size=order_size, limit_price=None)
    entry_order = okx.place_open_order(order_req, hedge_mode=hedge_mode)

    print()
    print("✅ 开仓单成功！")
    print(f"  订单 ID: {entry_order.id}")
    print(f"  成交价: {entry_order.price}")
    print(f"  数量: {entry_order.size} SOL")
    print()

    if entry_order.id.startswith("error-"):
        print("❌ 开仓失败，终止测试")
        sys.exit(1)

    # 使用实际成交价计算止损价（如果成交价可用）
    if entry_order.price > 0:
        stop_loss_price = entry_order.price * (1 - sl_percentage)
        print(f"  📊 根据成交价重新计算止损价: {stop_loss_price:.2f} USDT")
        print()

except Exception as e:
    print()
    print(f"❌ 开仓失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 下止损单
if place_sl:
    print(f"Step 5: 下止损单")
    print("-" * 70)
    print(f"  止损方向: sell (平多仓)")
    print(f"  止损价格: {stop_loss_price:.2f} USDT")
    print(f"  止损数量: {order_size} SOL")
    print()

    try:
        print("⏳ 下止损单中...")
        sl_order = okx.place_stop_loss_order(
            symbol=symbol,
            side="sell",  # 平多仓用 sell
            size=order_size,
            stop_price=stop_loss_price,
            hedge_mode=hedge_mode
        )

        print()
        print("✅ 止损单成功！")
        print(f"  止损单 ID: {sl_order.id}")
        print(f"  触发价格: {sl_order.price}")
        print(f"  数量: {sl_order.size} SOL")
        print()

        if sl_order.id.startswith("error-"):
            print("⚠️ 止损单下单失败，但开仓已成功")
            print("   请手动在 OKX 设置止损！")
        else:
            print("✅✅✅ 开仓 + 止损单全部成功！")

    except Exception as e:
        print()
        print(f"❌ 止损单失败: {e}")
        print("⚠️ 开仓已成功，但止损单失败！请手动设置止损！")
        import traceback
        traceback.print_exc()
else:
    print("Step 5: 跳过止损单（PERPBOT_TV_PLACE_STOP_LOSS=false）")
    print()

print()
print("=" * 70)
print("📊 测试总结")
print("=" * 70)
print(f"开仓单 ID: {entry_order.id}")
print(f"开仓价格: {entry_order.price}")
if place_sl and 'sl_order' in locals() and not sl_order.id.startswith("error-"):
    print(f"止损单 ID: {sl_order.id}")
    print(f"止损价格: {stop_loss_price:.2f}")
    print()
    print("🌐 验证订单：")
    print("  1. 持仓页面：https://www.okx.com/trade-swap/sol-usdt-swap")
    print("  2. 委托页面：应该看到止损条件单")
else:
    print("止损单: 未下单或失败")
    print()
    print("⚠️ 请手动设置止损保护！")

print("=" * 70)
