#!/usr/bin/env python3
"""
完整清理 EIGEN - 平仓 + 撤销挂单
使用 get_active_orders 查询然后逐个撤销
"""

import sys
sys.path.insert(0, '/src')

import asyncio
from perpbot.exchanges.lighter import LighterClient


async def complete_cleanup():
    """完整清理：平仓 + 撤单"""

    print('=' * 70)
    print('EIGEN 完整清理：平仓 + 撤销挂单')
    print('=' * 70)
    print()

    client = LighterClient(use_testnet=False)
    client.connect()

    quote = client.get_current_price('EIGEN/USDT')
    print(f'💰 当前价格: ${quote.mid:.5f}')
    print()

    # Step 1: 平仓
    print('=' * 70)
    print('Step 1: 平仓所有 EIGEN 持仓')
    print('=' * 70)
    print()

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if eigen_positions:
        print(f'📊 发现 {len(eigen_positions)} 个持仓')
        for i, pos in enumerate(eigen_positions, 1):
            print(f'\n持仓 {i}: {pos.order.symbol} {pos.order.size} ({pos.order.side})')
            try:
                close_order = client.place_close_order(pos, quote.mid)
                print(f'✅ 平仓订单: {close_order.id}')
                await asyncio.sleep(2)
            except Exception as e:
                print(f'❌ 平仓失败: {e}')
    else:
        print('✅ 没有持仓')

    # Step 2: 查询并撤销挂单
    print()
    print('=' * 70)
    print('Step 2: 查询并撤销所有 EIGEN 挂单')
    print('=' * 70)
    print()

    try:
        # 使用 get_active_orders 查询
        all_orders = client.get_active_orders()
        eigen_orders = [o for o in all_orders if 'EIGEN' in o.symbol]

        if not eigen_orders:
            print('✅ 没有 EIGEN 挂单')
        else:
            print(f'📋 发现 {len(eigen_orders)} 个挂单:')
            for i, order in enumerate(eigen_orders, 1):
                print(f'\n订单 {i}:')
                print(f'  ID: {order.id}')
                print(f'  Symbol: {order.symbol}')
                print(f'  Side: {order.side}')
                print(f'  Size: {order.size}')
                print(f'  Price: {order.price:.5f}')

                # 撤销此订单
                print(f'  🗑️  撤销中...')
                try:
                    client.cancel_order(order_id=order.id, symbol=order.symbol)
                    print(f'  ✅ 已撤销')
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f'  ❌ 撤销失败: {e}')

    except Exception as e:
        print(f'⚠️  查询/撤单过程出错: {e}')
        print()
        print('注意: get_active_orders 可能在 Lighter 上不可用')
        print('建议手动在 Lighter 平台检查并撤销挂单')
        import traceback
        traceback.print_exc()

    # Step 3: 验证
    print()
    print('=' * 70)
    print('Step 3: 验证清理结果')
    print('=' * 70)
    print()

    print('⏳ 等待 5 秒...')
    await asyncio.sleep(5)

    final_positions = client.get_account_positions()
    final_eigen = [p for p in final_positions if 'EIGEN' in p.order.symbol]

    if not final_eigen:
        print('✅ 所有持仓已清空')
    else:
        print(f'⚠️  还剩 {len(final_eigen)} 个持仓')

    try:
        final_orders = client.get_active_orders()
        final_eigen_orders = [o for o in final_orders if 'EIGEN' in o.symbol]

        if not final_eigen_orders:
            print('✅ 所有挂单已清空')
        else:
            print(f'⚠️  还剩 {len(final_eigen_orders)} 个挂单')
    except:
        print('ℹ️  无法查询挂单状态，请手动验证')

    print()
    print('=' * 70)
    print('清理完成')
    print('=' * 70)
    print()
    print('🌐 手动验证: https://mainnet.zklighter.elliot.ai/')
    print()


if __name__ == "__main__":
    asyncio.run(complete_cleanup())
