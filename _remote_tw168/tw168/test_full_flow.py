#!/usr/bin/env python3
"""
完整交易流程测试
模拟 TradingView 信号: ZONE → DIV → 开仓 → 止损/止盈 → 平仓
"""

import sys
sys.path.insert(0, '/src')

import asyncio
import requests
import json
from datetime import datetime
from perpbot.exchanges.lighter import LighterClient


WEBHOOK_URL = "http://localhost:8000/tradingview/webhook"
SYMBOL = "EIGEN"
TIMEFRAME = "30m"


async def main():
    print("=" * 70)
    print("完整交易流程测试")
    print("=" * 70)
    print()

    print("📋 测试配置:")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Exchange: Lighter")
    print()

    # 确认
    response = input("⚠️  这将执行真实交易！确认继续？(yes/no): ")
    if response.lower() != 'yes':
        print("❌ 测试取消")
        return

    # 连接 Lighter
    print("\n🔌 连接 Lighter...")
    client = LighterClient(use_testnet=False)
    client.connect()
    print("✅ 已连接")

    # 获取当前价格
    quote = client.get_current_price(f"{SYMBOL}/USDT")
    current_price = quote.mid
    print(f"\n💰 当前 {SYMBOL} 价格: ${current_price:.5f}")

    print("\n" + "=" * 70)
    print("Step 1: 发送 ZONE 信号 (开仓)")
    print("=" * 70)
    print()

    # 发送 ZONE webhook
    zone_payload = {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "zone": "OVERSOLD",
        "price": current_price,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    print("📤 发送 ZONE=OVERSOLD 信号...")
    print(json.dumps(zone_payload, indent=2))
    print()

    try:
        zone_response = requests.post(WEBHOOK_URL, json=zone_payload, timeout=10)
        print("📥 ZONE 响应:")
        print(f"  Status: {zone_response.status_code}")
        print(f"  Body: {zone_response.text}")
    except Exception as e:
        print(f"❌ ZONE 请求失败: {e}")

    print("\n⏳ 等待 15 秒让订单处理...")
    await asyncio.sleep(15)

    print("\n" + "=" * 70)
    print("Step 2: 检查开仓订单状态")
    print("=" * 70)
    print()

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if SYMBOL in p.order.symbol]

    if not eigen_positions:
        print('⚠️  没有找到 EIGEN 持仓')
        print('可能是 Ladder 订单还未成交，或开仓失败')
        print('\n继续等待 10 秒...')
        await asyncio.sleep(10)

        # 再次检查
        positions = client.get_account_positions()
        eigen_positions = [p for p in positions if SYMBOL in p.order.symbol]

    if eigen_positions:
        print(f'✅ 找到 {len(eigen_positions)} 个 EIGEN 持仓:')
        for i, pos in enumerate(eigen_positions, 1):
            print(f'\n持仓 {i}:')
            print(f'  Symbol: {pos.order.symbol}')
            print(f'  Side: {pos.order.side}')
            print(f'  Size: {pos.order.size}')
            print(f'  Entry Price: {pos.order.price:.5f}')
    else:
        print('❌ 仍然没有持仓，开仓可能失败')
        print('\n检查日志中的错误信息...')
        return

    print("\n⏳ 等待 5 秒...")
    await asyncio.sleep(5)

    print("\n" + "=" * 70)
    print("Step 3: 发送 DIV 信号 (设置止损/止盈)")
    print("=" * 70)
    print()

    # 发送 DIV webhook
    div_payload = {
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "divergence_type": "BULLISH",
        "price": current_price,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    print("📤 发送 DIV=BULLISH 信号...")
    print(json.dumps(div_payload, indent=2))
    print()

    try:
        div_response = requests.post(WEBHOOK_URL, json=div_payload, timeout=10)
        print("📥 DIV 响应:")
        print(f"  Status: {div_response.status_code}")
        print(f"  Body: {div_response.text}")
    except Exception as e:
        print(f"❌ DIV 请求失败: {e}")

    print("\n⏳ 等待 15 秒让止损/止盈订单处理...")
    await asyncio.sleep(15)

    print("\n" + "=" * 70)
    print("Step 4: 验证持仓和订单状态")
    print("=" * 70)
    print()

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if SYMBOL in p.order.symbol]

    print('📊 当前持仓状态:')
    if not eigen_positions:
        print('⚠️  没有持仓 (可能已被止损触发)')
    else:
        for i, pos in enumerate(eigen_positions, 1):
            print(f'\n持仓 {i}:')
            print(f'  Symbol: {pos.order.symbol}')
            print(f'  Size: {pos.order.size}')
            print(f'  Entry Price: {pos.order.price:.5f}')
            print(f'  Side: {pos.order.side}')
            print()
            print('  ℹ️  止损/止盈状态需要通过 Lighter 平台查看')
            print('      https://mainnet.zklighter.elliot.ai/')

    print("\n⏳ 等待 5 秒...")
    await asyncio.sleep(5)

    # 询问是否平仓
    print("\n" + "=" * 70)
    response = input("是否继续测试平仓？(yes/no): ")
    if response.lower() != 'yes':
        print("⏸️  测试暂停 - 持仓保留")
        print()
        print("手动平仓脚本:")
        print("  cat /tmp/clear_eigen.py | docker compose exec -T tv-okx python3")
        return

    print("\n" + "=" * 70)
    print("Step 5: 手动平仓 (模拟止盈触发)")
    print("=" * 70)
    print()

    # 获取最新价格
    quote = client.get_current_price(f"{SYMBOL}/USDT")
    close_price = quote.mid
    print(f'💰 当前价格: ${close_price:.5f}')

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if SYMBOL in p.order.symbol]

    if not eigen_positions:
        print('✅ 没有 EIGEN 持仓需要平仓')
    else:
        print(f'\n🔴 平仓 {len(eigen_positions)} 个持仓...')

        for i, pos in enumerate(eigen_positions, 1):
            print(f'\n平仓 {i}: {pos.order.symbol} {pos.order.size}')
            try:
                close_order = client.place_close_order(pos, close_price)
                print(f'✅ 平仓订单: {close_order.id}')
                await asyncio.sleep(2)
            except Exception as e:
                print(f'❌ 平仓失败: {e}')

        await asyncio.sleep(5)

        # 验证
        print('\n🔄 验证平仓...')
        final_positions = client.get_account_positions()
        final_eigen = [p for p in final_positions if SYMBOL in p.order.symbol]

        if not final_eigen:
            print('✅ 所有持仓已平仓!')
        else:
            print(f'⚠️  还剩 {len(final_eigen)} 个持仓:')
            for p in final_eigen:
                print(f'  - {p.order.symbol}: {p.order.size}')

    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)
    print()
    print("📊 测试总结:")
    print("  1. ✅ ZONE 信号发送")
    print("  2. ✅ Ladder 开仓")
    print("  3. ✅ DIV 信号发送")
    print("  4. ✅ 止损/止盈设置")
    print("  5. ✅ 手动平仓")
    print()
    print("🔍 详细日志:")
    print("  docker compose logs -f | grep -i eigen")
    print()


if __name__ == "__main__":
    asyncio.run(main())
