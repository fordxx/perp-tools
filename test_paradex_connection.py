#!/usr/bin/env python3
"""
Paradex 连接验证测试 - 非交互式版本
"""

import logging
import sys

sys.path.insert(0, 'src')

from perpbot.exchanges.paradex import ParadexClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    print("\n" + "="*60)
    print("  Paradex 连接验证测试")
    print("="*60)
    
    # 根据 .env 配置判断环境
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    env = os.getenv('PARADEX_ENV', 'testnet')
    use_testnet = (env.lower() != 'prod' and env.lower() != 'mainnet')
    
    print(f"\n📌 环境: {'Testnet' if use_testnet else 'Mainnet (生产环境)'}")
    print(f"   (从 .env 读取: PARADEX_ENV={env})")
    
    # 创建客户端
    client = ParadexClient(use_testnet=use_testnet)
    
    # 测试 1: 连接
    print("\n" + "-"*60)
    print("🔗 测试 1: 连接 Paradex SDK...")
    print("-"*60)
    
    try:
        client.connect()
        
        if client._trading_enabled:
            print("✅ Paradex SDK 连接成功！")
            print(f"   - 交易模式: {'Testnet' if client.use_testnet else 'Mainnet'}")
            print(f"   - 交易启用: {client._trading_enabled}")
            print(f"   - 账户地址: {client.account_address[:10]}...{client.account_address[-6:]}")
        else:
            print("⚠️  Paradex SDK 初始化失败（可能缺少凭证）")
            print("   请检查 .env 文件中的 PARADEX_L2_PRIVATE_KEY 和 PARADEX_ACCOUNT_ADDRESS")
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        logger.exception("连接错误详情:")
        return False
    
    # 测试 2: 查询价格
    print("\n" + "-"*60)
    print("💰 测试 2: 查询 ETH/USDT 价格...")
    print("-"*60)
    
    try:
        price = client.get_current_price("ETH/USDT")
        print("✅ 价格查询成功！")
        print(f"   - 买价 (Bid): ${price.bid:,.2f}")
        print(f"   - 卖价 (Ask): ${price.ask:,.2f}")
        print(f"   - 中间价: ${price.mid:,.2f}")
    except Exception as e:
        print(f"❌ 价格查询失败: {e}")
        logger.exception("价格查询错误详情:")
        return False
    
    # 测试 3: 查询订单簿
    print("\n" + "-"*60)
    print("📊 测试 3: 查询 ETH/USDT 订单簿...")
    print("-"*60)
    
    try:
        book = client.get_orderbook("ETH/USDT", depth=5)
        print("✅ 订单簿查询成功！")
        
        print("\n📈 卖单（Ask）前5档：")
        for i, (price, size) in enumerate(reversed(book.asks[:5]), 1):
            print(f"   {i}. ${price:,.2f}  |  {size:.4f}")
        
        print("\n📉 买单（Bid）前5档：")
        for i, (price, size) in enumerate(book.bids[:5], 1):
            print(f"   {i}. ${price:,.2f}  |  {size:.4f}")
            
    except Exception as e:
        print(f"❌ 订单簿查询失败: {e}")
        logger.exception("订单簿查询错误详情:")
        return False
    
    # 测试 4: 查询余额
    print("\n" + "-"*60)
    print("💼 测试 4: 查询账户余额...")
    print("-"*60)
    
    try:
        balances = client.get_account_balances()
        
        if not balances:
            print("ℹ️  没有余额数据（可能账户为空）")
        else:
            print("✅ 余额查询成功！")
            for balance in balances:
                print(f"\n💰 {balance.asset}:")
                print(f"   - 可用: {balance.free:,.4f}")
                print(f"   - 冻结: {balance.locked:,.4f}")
                print(f"   - 总计: {balance.total:,.4f}")
                
    except Exception as e:
        print(f"⚠️  余额查询失败: {e}")
        logger.warning("余额查询错误详情:", exc_info=True)
    
    # 测试 5: 查询持仓
    print("\n" + "-"*60)
    print("📋 测试 5: 查询当前持仓...")
    print("-"*60)
    
    try:
        positions = client.get_account_positions()
        
        if not positions:
            print("ℹ️  当前没有持仓")
        else:
            print("✅ 持仓查询成功！")
            for i, pos in enumerate(positions, 1):
                print(f"\n📊 持仓 #{i}:")
                print(f"   - 交易对: {pos.order.symbol}")
                print(f"   - 方向: {'做多 (Long)' if pos.order.side == 'buy' else '做空 (Short)'}")
                print(f"   - 数量: {pos.order.size:.4f}")
                print(f"   - 开仓价: ${pos.order.price:,.2f}")
                
    except Exception as e:
        print(f"⚠️  持仓查询失败: {e}")
        logger.warning("持仓查询错误详情:", exc_info=True)
    
    # 测试 6: 查询活跃订单
    print("\n" + "-"*60)
    print("📝 测试 6: 查询活跃订单...")
    print("-"*60)
    
    try:
        orders = client.get_active_orders()
        
        if not orders:
            print("ℹ️  当前没有活跃订单")
        else:
            print("✅ 活跃订单查询成功！")
            for i, order in enumerate(orders, 1):
                print(f"\n📝 订单 #{i}:")
                print(f"   - ID: {order.id}")
                print(f"   - 交易对: {order.symbol}")
                print(f"   - 方向: {order.side.upper()}")
                print(f"   - 数量: {order.size:.4f}")
                print(f"   - 价格: ${order.price:,.2f}")
                
    except Exception as e:
        print(f"⚠️  活跃订单查询失败: {e}")
        logger.warning("活跃订单查询错误详情:", exc_info=True)
    
    print("\n" + "="*60)
    print("  ✅ 基础连接验证测试完成！")
    print("="*60)
    print("\n💡 提示：")
    print("   - 连接和市场数据查询都正常工作")
    print("   - 如需测试下单功能，请运行: python test_paradex.py")
    print("   - 该脚本提供交互式下单测试（需要手动确认）")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"测试过程中发生未预期错误: {e}")
        sys.exit(1)
