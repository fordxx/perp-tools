#!/usr/bin/env python3
"""
Paradex 平仓功能测试脚本

测试功能：
1. 开仓（市价单）
2. 查询持仓
3. 市价平仓
4. 验证平仓结果

使用方法：
1. 配置 .env 文件
2. 运行：python test_close_position.py
"""

import logging
import sys
import time

# 添加 src 到 Python 路径
sys.path.insert(0, 'src')

from perpbot.exchanges.paradex import ParadexClient
from perpbot.models import OrderRequest

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def print_separator(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def test_open_position(client: ParadexClient, symbol: str = "ETH/USDT", 
                       side: str = "buy", size: float = 0.004):
    """步骤 1: 开仓（市价单）"""
    print_separator(f"步骤 1: 开仓 - {side.upper()} {size} {symbol}")
    
    confirm = input(f"\n⚠️  确认开仓？({side.upper()} {size} {symbol}，市价单，yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消开仓")
        return None
    
    try:
        request = OrderRequest(
            symbol=symbol,
            side=side,
            size=size,
            limit_price=None,  # 市价单
        )
        
        order = client.place_open_order(request)
        
        if order.id.startswith("rejected") or order.id.startswith("error"):
            print(f"❌ 开仓失败: {order.id}")
            return None
        
        print("✅ 开仓成功！")
        print(f"   - 订单ID: {order.id}")
        print(f"   - 交易对: {order.symbol}")
        print(f"   - 方向: {order.side.upper()}")
        print(f"   - 数量: {order.size:.4f}")
        print(f"   - 成交价: ${order.price:,.2f}")
        
        return order
    
    except Exception as e:
        print(f"❌ 开仓失败: {e}")
        return None


def test_query_position(client: ParadexClient, symbol: str = "ETH/USDT"):
    """步骤 2: 查询持仓"""
    print_separator("步骤 2: 查询当前持仓")
    
    try:
        positions = client.get_account_positions()
        
        if not positions:
            print("ℹ️  当前没有持仓")
            return None
        
        print(f"✅ 查询到 {len(positions)} 个持仓：")
        
        target_position = None
        for i, pos in enumerate(positions, 1):
            print(f"\n📊 持仓 #{i}:")
            print(f"   - 交易对: {pos.order.symbol}")
            print(f"   - 方向: {'做多 (Long)' if pos.order.side == 'buy' else '做空 (Short)'}")
            print(f"   - 数量: {pos.order.size:.4f}")
            print(f"   - 开仓价: ${pos.order.price:,.2f}")
            
            if pos.order.symbol == symbol:
                target_position = pos
        
        return target_position
    
    except Exception as e:
        print(f"❌ 持仓查询失败: {e}")
        return None


def test_close_position(client: ParadexClient, position):
    """步骤 3: 平仓（市价单）"""
    if not position:
        print("\n❌ 没有持仓，无法平仓")
        return None
    
    print_separator("步骤 3: 平仓（市价单）")
    
    print(f"\n准备平仓：")
    print(f"   - 交易对: {position.order.symbol}")
    print(f"   - 方向: {position.order.side.upper()}")
    print(f"   - 数量: {position.order.size:.4f}")
    print(f"   - 开仓价: ${position.order.price:,.2f}")
    
    confirm = input(f"\n⚠️⚠️  确认平仓？(yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消平仓")
        return None
    
    try:
        # 获取当前价格
        price = client.get_current_price(position.order.symbol)
        
        # 使用 place_close_order 平仓
        close_order = client.place_close_order(position, price.mid)
        
        if close_order.id.startswith("rejected") or close_order.id.startswith("error"):
            print(f"❌ 平仓失败: {close_order.id}")
            return None
        
        print("✅ 平仓成功！")
        print(f"   - 订单ID: {close_order.id}")
        print(f"   - 交易对: {close_order.symbol}")
        print(f"   - 方向: {close_order.side.upper()}")
        print(f"   - 数量: {close_order.size:.4f}")
        print(f"   - 成交价: ${close_order.price:,.2f}")
        
        return close_order
    
    except Exception as e:
        print(f"❌ 平仓失败: {e}")
        return None


def test_verify_closed(client: ParadexClient, symbol: str = "ETH/USDT"):
    """步骤 4: 验证平仓结果"""
    print_separator("步骤 4: 验证平仓结果")
    
    print("\n等待 3 秒后查询持仓...")
    time.sleep(3)
    
    try:
        positions = client.get_account_positions()
        
        # 查找目标交易对的持仓
        target_found = False
        for pos in positions:
            if pos.order.symbol == symbol:
                target_found = True
                print(f"\n⚠️  {symbol} 仍有持仓：")
                print(f"   - 数量: {pos.order.size:.4f}")
                print(f"   - 方向: {pos.order.side.upper()}")
                break
        
        if not target_found:
            print(f"\n✅ 验证通过：{symbol} 持仓已完全平仓")
        
        # 查询余额
        print("\n查询最新余额：")
        balances = client.get_account_balances()
        for balance in balances:
            print(f"   💰 {balance.asset}:")
            print(f"      - 可用: {balance.free:,.4f}")
            print(f"      - 总计: {balance.total:,.4f}")
        
    except Exception as e:
        print(f"❌ 验证失败: {e}")


def main():
    """主测试流程"""
    print("\n🚀 Paradex 平仓功能测试")
    print("=" * 60)
    
    # 选择环境
    env = input("\n选择环境 (1=Mainnet, 2=Testnet): ").strip()
    use_testnet = (env == "2")
    
    if not use_testnet:
        confirm = input("\n⚠️ 警告：你选择了主网！这会使用真实资金。确认继续？(yes/no): ").strip().lower()
        if confirm != 'yes':
            print("已取消，建议先在测试网测试")
            return
    
    # 创建客户端
    client = ParadexClient(use_testnet=use_testnet)
    client.connect()
    
    if not client._trading_enabled:
        print("\n❌ 连接失败，无法继续测试")
        return
    
    symbol = "ETH/USDT"
    
    # 测试流程
    print("\n" + "=" * 60)
    print("  测试流程：开仓 → 查询 → 平仓 → 验证")
    print("=" * 60)
    
    # 步骤 1: 开仓
    order = test_open_position(client, symbol=symbol, side="buy", size=0.004)
    
    if not order:
        print("\n❌ 开仓失败，测试终止")
        return
    
    # 等待几秒让订单成交
    print("\n⏳ 等待 5 秒让订单成交...")
    time.sleep(5)
    
    # 步骤 2: 查询持仓
    position = test_query_position(client, symbol=symbol)
    
    if not position:
        print("\n⚠️  未找到持仓，可能订单还未成交或已被平仓")
        return
    
    # 步骤 3: 平仓
    close_order = test_close_position(client, position)
    
    if not close_order:
        print("\n❌ 平仓失败")
        return
    
    # 步骤 4: 验证
    test_verify_closed(client, symbol=symbol)
    
    print("\n" + "=" * 60)
    print("  ✅ 平仓功能测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
    except Exception as e:
        logger.exception(f"测试过程中发生错误: {e}")
