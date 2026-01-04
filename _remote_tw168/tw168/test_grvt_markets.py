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

    print("正在获取GRVT可用市场...")
    try:
        markets = await client.api.load_markets()
        print(f"总共加载了 {len(markets)} 个市场")

        # 查找LDO相关的市场
        ldo_markets = [k for k in markets.keys() if 'LDO' in k.upper()]
        print(f"找到的LDO相关市场: {ldo_markets}")

        # 显示LDO市场的详细信息
        for symbol in ldo_markets:
            print(f"LDO市场详情: {symbol}")
            market_info = markets.get(symbol)
            if market_info:
                print(f"  市场信息: {market_info}")

        # 显示前10个市场作为示例
        print("\n前10个市场示例:")
        for i, symbol in enumerate(list(markets.keys())[:10]):
            print(f"  {symbol}")

    except Exception as e:
        print(f"获取市场失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())