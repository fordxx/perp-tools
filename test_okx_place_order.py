import os
from dotenv import load_dotenv
from src.perpbot.exchanges.okx import OKXClient
from src.perpbot.models import OrderRequest

# 加载环境变量，确保 OKX_API_KEY、OKX_API_SECRET、OKX_PASSPHRASE 已配置
env_file = ".env.tv168" if os.path.exists(".env.tv168") else ".env"
load_dotenv(env_file)

# 从环境变量读取 OKX_ENV 配置
okx_env = os.getenv("OKX_ENV", "testnet").lower()
use_testnet = okx_env in ["testnet", "test"]
print(f"📊 OKX 环境: {okx_env} (use_testnet={use_testnet})")

if not use_testnet:
    print("⚠️ ⚠️ ⚠️ 警告：即将使用真实资金下单！⚠️ ⚠️ ⚠️")
    print("请确认：")
    print("  1. 你理解这将使用真实资金")
    print("  2. 订单大小已设置为小仓位测试")
    print("  3. 账户余额充足且可承受风险")

# 初始化 OKX 客户端
okx = OKXClient(use_testnet=use_testnet, allow_mainnet=True)
okx.connect()

if not okx._trading_enabled:
    print("❌ OKX 交易未启用，请检查 API KEY/SECRET/PASSPHRASE 配置")
    exit(1)

# 下单参数
symbol = "XRP/USDT"
side = "buy"  # 或 "sell"
size = 1   # 下单数量

order_req = OrderRequest(symbol=symbol, side=side, size=size, limit_price=None)
order = okx.place_open_order(order_req)

print("下单结果：", order)
if hasattr(order, 'id'):
    print("订单ID:", order.id)
    if hasattr(order, 'status'):
        print("订单状态:", order.status)
