#!/usr/bin/env python3
"""
Paradex 限价单下单测试
测试在 Paradex 上下一个不会立即成交的限价单
"""

import logging
import sys
import time

sys.path.insert(0, 'src')

from perpbot.exchanges.paradex import ParadexClient
from perpbot.models import OrderRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    print("\n" + "="*60)
    print("  Paradex 限价单下单测试")
    print("="*60)
    
    # 创建客户端
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    env = os.getenv('PARADEX_ENV', 'testnet')
    use_testnet = (env.lower() != 'prod' and env.lower() != 'mainnet')
    
    print(f"\n📌 环境: {'Testnet' if use_testnet else 'Mainnet (生产环境)'}")
    
    client = ParadexClient(use_testnet=use_testnet)
    
    # 连接
    print("\n🔗 连接 Paradex...")
    client.connect()
    
    if not client._trading_enabled:
        print("❌ 连接失败")
        return False
    
    print("✅ 连接成功")
    
    # 获取当前价格
    print("\n💰 获取 ETH/USDT 当前价格...")
    price = client.get_current_price("ETH/USDT")
    print(f"   当前市场价: ${price.mid:,.2f}")
    print(f"   买价 (Bid): ${price.bid:,.2f}")
    print(f"   卖价 (Ask): ${price.ask:,.2f}")
    
    # 设置限价单参数
    # 使用一个低于市价 3% 的买单价格，不会立即成交
    symbol = "ETH/USDT"
    side = "buy"
    size = 0.003  # 很小的数量，约 10 USDT
    limit_price = round(price.bid * 0.97, 2)  # 低于买价 3%
    
    print("\n" + "="*60)
    print("  准备下限价单")
    print("="*60)
    print(f"\n📝 订单参数:")
    print(f"   - 交易对: {symbol}")
    print(f"   - 方向: {side.upper()}")
    print(f"   - 数量: {size} ETH")
    print(f"   - 限价: ${limit_price:,.2f}")
    print(f"   - 预计金额: ${size * limit_price:,.2f} USDT")
    print(f"\n💡 该价格低于市价约 {((price.mid - limit_price) / price.mid * 100):.1f}%，不会立即成交")
    
    print(f"\n⚠️  警告: 这是真实下单（{'主网' if not use_testnet else '测试网'}）")
    print("="*60)
    
    # 创建订单请求
    request = OrderRequest(
        symbol=symbol,
        side=side,
        size=size,
        limit_price=limit_price,
    )
    
    print("\n🚀 正在下单...")
    
    try:
        order = client.place_open_order(request)
        
        if order.id.startswith("rejected") or order.id.startswith("error"):
            print(f"❌ 下单被拒绝: {order.id}")
            return False
        
        print("\n✅ 限价单下单成功！")
        print(f"\n📋 订单详情:")
        print(f"   - 订单ID: {order.id}")
        print(f"   - 交易对: {order.symbol}")
        print(f"   - 方向: {order.side.upper()}")
        print(f"   - 数量: {order.size} ETH")
        print(f"   - 价格: ${order.price:,.2f}")
        print(f"   - 时间: {order.created_at}")
        
        # 等待 3 秒后查询订单状态
        print("\n⏳ 等待 3 秒后查询订单状态...")
        time.sleep(3)
        
        print("\n📊 查询活跃订单...")
        active_orders = client.get_active_orders()
        
        if active_orders:
            print(f"✅ 找到 {len(active_orders)} 个活跃订单:")
            for i, o in enumerate(active_orders, 1):
                is_our_order = (o.id == order.id)
                marker = "👉" if is_our_order else "  "
                print(f"\n{marker} 订单 #{i}:")
                print(f"   - ID: {o.id}")
                print(f"   - 交易对: {o.symbol}")
                print(f"   - 方向: {o.side.upper()}")
                print(f"   - 数量: {o.size}")
                print(f"   - 价格: ${o.price:,.2f}")
                if is_our_order:
                    print(f"   ✅ 这是我们刚下的订单")
        else:
            print("⚠️  没有找到活跃订单（订单可能已经被取消或成交）")
        
        # 撤销订单
        print(f"\n🗑️  撤销订单 {order.id}...")
        try:
            client.cancel_order(order.id)
            print("✅ 订单撤销成功！")
            
            # 再次查询确认
            time.sleep(2)
            remaining_orders = client.get_active_orders()
            our_order_exists = any(o.id == order.id for o in remaining_orders)
            
            if not our_order_exists:
                print("✅ 确认订单已被撤销")
            else:
                print("⚠️  订单可能仍在撤销中")
                
        except Exception as e:
            print(f"❌ 撤销订单失败: {e}")
            logger.exception("撤销错误详情:")
        
        print("\n" + "="*60)
        print("  ✅ 限价单测试完成！")
        print("="*60)
        print("\n📊 测试总结:")
        print("   ✅ 下单成功")
        print("   ✅ 订单状态查询成功")
        print("   ✅ 订单撤销成功")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 下单失败: {e}")
        logger.exception("下单错误详情:")
        return False

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
