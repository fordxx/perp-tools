#!/usr/bin/env python3
"""
列出 GRVT 支持的所有交易对
"""
from __future__ import annotations
import os
import asyncio
from dotenv import load_dotenv
from app.grvt import GrvtClient, GrvtCredentials

load_dotenv()

# 使用dummy凭证来加载市场（不需要真实凭证）
API_KEY = os.getenv("GRVT_API_KEY", "dummy")
API_SECRET = os.getenv("GRVT_PRIVATE_KEY", "0" * 64)
TRADING_ACCOUNT = os.getenv("GRVT_TRADING_ACCOUNT_ID", "dummy")
BASE_URL = os.getenv("GRVT_BASE_URL", "https://api.grvt.io")

async def main():
    print("=" * 70)
    print("GRVT 交易所支持的交易对列表")
    print("=" * 70)

    try:
        creds = GrvtCredentials(
            api_key=API_KEY,
            private_key=API_SECRET,
            trading_account_id=TRADING_ACCOUNT
        )
        client = GrvtClient(BASE_URL, creds)
        await client.connect()

        markets = await client.api.load_markets()
        print(f"\n✅ 总共加载了 {len(markets)} 个市场\n")

        # 分类交易对
        perp_usdt = []
        perp_other = []
        spot = []

        for symbol, info in markets.items():
            market_type = info.get('type', '').lower()
            quote = info.get('quote', '')

            if 'swap' in market_type or 'perpetual' in market_type or '/USDT:USDT' in symbol:
                if 'USDT' in quote or '/USDT' in symbol:
                    perp_usdt.append(symbol)
                else:
                    perp_other.append(symbol)
            else:
                spot.append(symbol)

        # 显示USDT永续合约
        print(f"📊 USDT 永续合约 ({len(perp_usdt)} 个):")
        print("-" * 70)

        # 分类显示
        categories = {
            '🏆 主流币': ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'ADA', 'DOGE', 'AVAX', 'DOT', 'MATIC', 'LTC', 'BCH', 'TRX'],
            '💎 DeFi': ['UNI', 'LINK', 'AAVE', 'MKR', 'SUSHI', 'CRV', 'COMP', 'YFI', 'PENDLE', 'LDO', 'ONDO'],
            '🔗 Layer1/2': ['ARB', 'OP', 'ATOM', 'TIA', 'SUI', 'APT', 'SEI', 'NEAR', 'FTM', 'ALGO', 'TON'],
            '🤖 AI': ['TAO', 'RNDR', 'FET', 'OCEAN', 'AGIX', 'GRT', 'EIGEN'],
            '🐕 Meme': ['SHIB', 'PEPE', 'WIF', 'BONK', 'FLOKI', 'TRUMP', 'FARTCOIN', 'PUMP'],
        }

        categorized = {k: [] for k in categories.keys()}
        categorized['📊 其他'] = []

        for symbol in sorted(perp_usdt):
            base = symbol.split('/')[0] if '/' in symbol else symbol.split('-')[0]
            found = False
            for cat_name, tokens in categories.items():
                if base in tokens:
                    categorized[cat_name].append(symbol)
                    found = True
                    break
            if not found:
                categorized['📊 其他'].append(symbol)

        # 打印分类结果
        for cat_name, symbols in categorized.items():
            if symbols:
                print(f"\n{cat_name} ({len(symbols)} 个):")
                # 提取base币种
                bases = [s.split('/')[0] if '/' in s else s.split('-')[0] for s in symbols]
                for i in range(0, len(bases), 8):
                    print("  " + ", ".join(bases[i:i+8]))

        # 显示其他类型
        if perp_other:
            print(f"\n\n⚠️ 非USDT永续合约 ({len(perp_other)} 个):")
            for s in perp_other[:10]:
                print(f"  {s}")
            if len(perp_other) > 10:
                print(f"  ... 还有 {len(perp_other) - 10} 个")

        if spot:
            print(f"\n\n💱 现货交易对 ({len(spot)} 个):")
            for s in spot[:10]:
                print(f"  {s}")
            if len(spot) > 10:
                print(f"  ... 还有 {len(spot) - 10} 个")

        print("\n" + "=" * 70)
        print(f"总计: {len(markets)} 个市场")
        print(f"USDT永续: {len(perp_usdt)} 个")
        print(f"其他永续: {len(perp_other)} 个")
        print(f"现货: {len(spot)} 个")
        print("=" * 70)

        # 生成SYMBOL_ALLOWLIST配置
        print("\n\n📝 推荐的 SYMBOL_ALLOWLIST 配置（OKX格式）:")
        print("-" * 70)

        # 转换为OKX格式
        okx_symbols = []
        for symbol in perp_usdt:
            # GRVT: BTC/USDT:USDT -> OKX: BTC-USDT-SWAP
            base = symbol.split('/')[0] if '/' in symbol else symbol.split('-')[0]
            okx_symbol = f"{base}-USDT-SWAP"
            okx_symbols.append(okx_symbol)

        # 主流币优先
        priority_bases = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'LINK', 'AVAX', 'DOT']
        priority_symbols = [s for s in okx_symbols if any(s.startswith(b) for b in priority_bases)]

        print("\n主流币（推荐）:")
        print("SYMBOL_ALLOWLIST=" + ",".join(sorted(priority_symbols)[:20]))

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
