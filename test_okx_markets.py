import os
from dotenv import load_dotenv
import ccxt

# 加载环境变量
env_file = ".env.tv168" if os.path.exists(".env.tv168") else ".env"
load_dotenv(env_file)

api_key = os.getenv("OKX_API_KEY")
api_secret = os.getenv("OKX_API_SECRET")
passphrase = os.getenv("OKX_PASSPHRASE")

exchange = ccxt.okx({
    'apiKey': api_key,
    'secret': api_secret,
    'password': passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'sandboxMode': True,
    },
    'headers': {
        'x-simulated-trading': "1",
    },
})

print("正在拉取测试网支持的合约...")
markets = exchange.load_markets()
for symbol in markets:
    if symbol.endswith("-SWAP") or symbol.endswith("/USDT"):
        print(symbol)
print("总共支持:", len(markets), "个市场")
