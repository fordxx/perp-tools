#!/usr/bin/env python3
"""
完整清理 EIGEN - 平仓 + 撤销所有挂单
"""

import sys
sys.path.insert(0, '/src')

import asyncio
import time
from perpbot.exchanges.lighter import LighterClient


async def complete_cleanup():
    """平仓并撤销所有 EIGEN 相关的挂单"""

    print('=' * 70)
    print('完整清理 EIGEN 持仓和挂单')
    print('=' * 70)
    print()

    # 连接
    print('🔌 连接 Lighter...')
    client = LighterClient(use_testnet=False)
    client.connect()
    print('✅ 已连接')
    print()

    # 获取当前价格
    quote = client.get_current_price('EIGEN/USDT')
    current_price = quote.mid
    print(f'💰 当前 EIGEN 价格: ${current_price:.5f}')
    print()

    # Step 1: 检查并平仓
    print('=' * 70)
    print('Step 1: 平仓所有 EIGEN 持仓')
    print('=' * 70)
    print()

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if not eigen_positions:
        print('✅ 没有 EIGEN 持仓')
    else:
        print(f'📊 发现 {len(eigen_positions)} 个 EIGEN 持仓')

        for i, pos in enumerate(eigen_positions, 1):
            print(f'\n持仓 {i}:')
            print(f'  Symbol: {pos.order.symbol}')
            print(f'  Side: {pos.order.side}')
            print(f'  Size: {pos.order.size}')

            print(f'\n🔴 平仓中...')
            try:
                close_order = client.place_close_order(pos, current_price)
                print(f'✅ 平仓订单: {close_order.id}')
                await asyncio.sleep(2)
            except Exception as e:
                print(f'❌ 平仓失败: {e}')

    # Step 2: 撤销所有 EIGEN 挂单
    print()
    print('=' * 70)
    print('Step 2: 撤销所有 EIGEN 挂单')
    print('=' * 70)
    print()

    try:
        # 使用 SignerClient 的 cancel_all_orders
        # time_in_force=0 表示立即撤销所有订单
        # timestamp_ms 使用当前时间戳

        from lighter.signer_client import SignerClient

        # 获取配置
        import os
        config = {}

        # 尝试多个可能的 .env 位置
        env_paths = ['/app/app/.env', '/app/.env', '.env']
        env_file = None

        for path in env_paths:
            if os.path.exists(path):
                env_file = path
                break

        if env_file:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key] = value
            print(f'✅ 配置文件: {env_file}')
        else:
            print(f'⚠️  未找到 .env 文件')

        api_private_key = config.get('LIGHTER_API_KEY_PRIVATE_KEY', '')
        account_index = int(config.get('LIGHTER_ACCOUNT_INDEX', '1'))
        api_key_index = int(config.get('LIGHTER_API_KEY_INDEX', '2'))

        if not api_private_key:
            print('⚠️  无法获取 API key，跳过撤单')
            print('   建议手动在 Lighter 平台检查并撤销挂单')
        else:
            print('📤 发送撤销所有订单请求...')

            # 创建 SignerClient
            signer_client = SignerClient(
                url="https://mainnet.zklighter.elliot.ai",
                account_index=account_index,
                api_private_keys={api_key_index: api_private_key}
            )

            # 撤销所有订单
            # time_in_force=0 (IMMEDIATE) 表示立即撤销
            timestamp_ms = int(time.time() * 1000)

            cancel_result, tx_hash, error = await signer_client.cancel_all_orders(
                time_in_force=0,  # CANCEL_ALL_TIF_IMMEDIATE
                timestamp_ms=timestamp_ms
            )

            if error:
                print(f'⚠️  撤单请求失败: {error}')
                print('   这可能意味着没有挂单，或者订单已经撤销')
            else:
                print(f'✅ 撤单请求已提交')
                print(f'   TxHash: {tx_hash}')

    except Exception as e:
        print(f'⚠️  撤单过程出错: {e}')
        print('   建议手动在 Lighter 平台检查挂单')

    # Step 3: 等待并验证
    print()
    print('=' * 70)
    print('Step 3: 验证清理结果')
    print('=' * 70)
    print()

    print('⏳ 等待 5 秒让交易处理...')
    await asyncio.sleep(5)

    # 再次检查持仓
    final_positions = client.get_account_positions()
    final_eigen = [p for p in final_positions if 'EIGEN' in p.order.symbol]

    print('\n📊 最终状态:')
    if not final_eigen:
        print('✅ 所有 EIGEN 持仓已清空')
    else:
        print(f'⚠️  还剩 {len(final_eigen)} 个持仓:')
        for p in final_eigen:
            print(f'  - {p.order.symbol}: {p.order.size}')

    print()
    print('=' * 70)
    print('清理完成')
    print('=' * 70)
    print()
    print('ℹ️  注意:')
    print('  - 挂单状态需要在 Lighter 平台验证')
    print('  - 访问: https://mainnet.zklighter.elliot.ai/')
    print('  - 检查 "Open Orders" 确认所有订单已撤销')
    print()


if __name__ == "__main__":
    asyncio.run(complete_cleanup())
