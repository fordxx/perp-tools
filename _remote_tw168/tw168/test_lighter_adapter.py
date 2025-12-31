#!/usr/bin/env python3
"""测试 Lighter 异步适配器

验证适配器是否正确工作：
1. 连接测试
2. 查询测试
3. 撤单测试（如果有挂单）
"""
import asyncio
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lighter_adapter import create_lighter_adapter


async def test_adapter():
    """测试适配器的各项功能"""
    print("=" * 60)
    print("Lighter 异步适配器测试")
    print("=" * 60)
    
    # 创建适配器
    print("\n1️⃣  创建适配器...")
    try:
        adapter = create_lighter_adapter(use_testnet=False)
        print(f"✅ 适配器创建成功")
        print(f"   异步模式: {adapter.is_async_mode}")
    except Exception as e:
        print(f"❌ 适配器创建失败: {e}")
        return False
    
    # 连接
    print("\n2️⃣  连接到交易所...")
    try:
        await adapter.connect()
        print("✅ 连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    
    # 查询价格
    print("\n3️⃣  查询价格...")
    test_symbols = ["EIGEN-USDT-SWAP", "ETH-USDT-SWAP", "BTC-USDT-SWAP"]
    for symbol in test_symbols:
        try:
            price = await adapter.get_last_price(inst_id=symbol)
            if price:
                print(f"✅ {symbol}: ${price:.2f}")
            else:
                print(f"⚠️  {symbol}: 无法获取价格")
        except Exception as e:
            print(f"❌ {symbol}: {e}")
    
    # 查询持仓
    print("\n4️⃣  查询持仓...")
    for symbol in test_symbols[:2]:  # 只查前2个
        for pos_side in ["long", "short"]:
            try:
                pos = await adapter.get_position(
                    inst_id=symbol,
                    pos_side=pos_side
                )
                if pos and float(pos.get("pos", 0)) > 0:
                    size = pos.get("pos")
                    avg_px = pos.get("avgPx", "N/A")
                    print(f"✅ {symbol} {pos_side}: {size} @ {avg_px}")
            except Exception as e:
                # 没有持仓很正常，不报错
                pass
    
    # 查询未成交订单
    print("\n5️⃣  查询未成交订单...")
    total_orders = 0
    for symbol in test_symbols[:2]:
        try:
            orders = await adapter.get_open_orders(inst_id=symbol)
            if orders:
                print(f"✅ {symbol}: {len(orders)} 个未成交订单")
                total_orders += len(orders)
                for order in orders[:3]:  # 最多显示3个
                    order_id = order.get("ordId", "N/A")
                    side = order.get("side", "N/A")
                    price = order.get("price", "N/A")
                    print(f"   - {order_id}: {side} @ {price}")
        except Exception as e:
            print(f"⚠️  {symbol}: {e}")
    
    # 测试撤单功能（如果有未成交订单）
    print("\n6️⃣  测试撤单功能...")
    if total_orders > 0:
        print("⚠️  检测到未成交订单")
        if sys.stdin.isatty():
            response = input("是否测试 cancel_all_orders()? (y/N): ").strip().lower()
        else:
            response = "n"
        if response == "y":
            try:
                # 测试撤销 EIGEN 的订单
                symbol = "EIGEN/USDT"  # Lighter 格式
                print(f"撤销 {symbol} 的所有订单...")
                success = await adapter.cancel_all_orders(symbol=symbol)
                if success:
                    print("✅ 撤单成功")
                else:
                    print("⚠️  撤单未执行或失败")
            except RuntimeError as e:
                if "Timeout context manager" in str(e):
                    print("❌ 遇到 aiohttp 超时问题 - LighterClient 需要重构为 async")
                else:
                    print(f"❌ 撤单失败: {e}")
            except Exception as e:
                print(f"❌ 撤单失败: {e}")
        else:
            print("⏭️  跳过撤单测试")
    else:
        print("ℹ️  没有未成交订单，跳过撤单测试")
    
    # 断开连接
    print("\n7️⃣  断开连接...")
    try:
        await adapter.disconnect()
        print("✅ 断开成功")
    except Exception as e:
        print(f"⚠️  断开时出现错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    return True


async def test_concurrent():
    """测试并发查询性能"""
    print("\n" + "=" * 60)
    print("并发查询性能测试")
    print("=" * 60)
    
    adapter = create_lighter_adapter(use_testnet=False)
    await adapter.connect()
    
    symbols = ["EIGEN-USDT-SWAP", "ETH-USDT-SWAP", "BTC-USDT-SWAP"]
    
    # 串行查询
    print("\n🐌 串行查询（一个接一个）...")
    import time
    start = time.time()
    for symbol in symbols:
        try:
            await adapter.get_last_price(inst_id=symbol)
        except:
            pass
    serial_time = time.time() - start
    print(f"   耗时: {serial_time:.2f}s")
    
    # 并发查询
    print("\n🚀 并发查询（同时执行）...")
    start = time.time()
    tasks = [
        adapter.get_last_price(inst_id=symbol)
        for symbol in symbols
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    parallel_time = time.time() - start
    print(f"   耗时: {parallel_time:.2f}s")
    
    speedup = serial_time / parallel_time if parallel_time > 0 else 0
    print(f"\n⚡ 加速比: {speedup:.1f}x")
    
    await adapter.disconnect()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="测试 Lighter 异步适配器")
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="运行并发性能测试"
    )
    args = parser.parse_args()
    
    try:
        if args.concurrent:
            asyncio.run(test_concurrent())
        else:
            asyncio.run(test_adapter())
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
