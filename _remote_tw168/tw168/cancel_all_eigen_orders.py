#!/usr/bin/env python3
"""
撤销所有 EIGEN 挂单 - 使用 LighterClient 的内部配置
"""

import sys
sys.path.insert(0, '/src')

import asyncio
import time
from perpbot.exchanges.lighter import LighterClient


async def cancel_all_orders():
    """撤销所有 EIGEN 市场的挂单"""

    print('=' * 70)
    print('撤销所有 EIGEN 挂单')
    print('=' * 70)
    print()

    # 连接
    print('🔌 连接 Lighter...')
    client = LighterClient(use_testnet=False)
    client.connect()
    print('✅ 已连接')
    print()

    # 检查持仓（了解当前状态）
    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if eigen_positions:
        print(f'📊 当前有 {len(eigen_positions)} 个 EIGEN 持仓')
        total_size = sum(p.order.size for p in eigen_positions)
        print(f'   总仓位: {total_size}')
    else:
        print('✅ 没有 EIGEN 持仓')

    print()

    # 使用 SignerClient 撤销所有订单
    print('📤 发送撤销所有订单请求...')
    print()

    try:
        # 直接使用 client._signer_client (已经配置好的)
        signer_client = client._signer_client

        if not signer_client:
            print('❌ SignerClient 未初始化')
            print('   系统可能以只读模式运行')
            return

        # 撤销所有订单
        # time_in_force=0 (IMMEDIATE) 表示立即撤销所有订单
        timestamp_ms = int(time.time() * 1000)

        cancel_result, tx_hash, error = await signer_client.cancel_all_orders(
            time_in_force=0,  # SignerClient.CANCEL_ALL_TIF_IMMEDIATE
            timestamp_ms=timestamp_ms
        )

        if error:
            print(f'⚠️  撤单请求返回错误:')
            print(f'   {error}')
            print()
            print('   可能原因:')
            print('   1. 没有挂单需要撤销')
            print('   2. 所有订单已经成交')
            print('   3. API 参数问题')
        else:
            print(f'✅ 撤单请求已提交')
            if tx_hash:
                print(f'   TxHash: {tx_hash}')
            print()

            # 等待处理
            print('⏳ 等待 5 秒让交易处理...')
            await asyncio.sleep(5)

            print('✅ 所有挂单应该已撤销')

    except Exception as e:
        print(f'❌ 撤单过程出错: {e}')
        import traceback
        traceback.print_exc()

    print()
    print('=' * 70)
    print('完成')
    print('=' * 70)
    print()
    print('ℹ️  验证方法:')
    print('   1. 访问 Lighter 平台: https://mainnet.zklighter.elliot.ai/')
    print('   2. 检查 "Open Orders" 标签')
    print('   3. 确认 EIGEN 订单全部清空')
    print()


if __name__ == "__main__":
    asyncio.run(cancel_all_orders())
