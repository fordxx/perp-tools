#!/usr/bin/env python3
"""
Extended 交易所订单调试脚本

用于诊断 HTTP 400 Bad Request 错误。
需要环境变量: EXTENDED_API_KEY, EXTENDED_API_SECRET, EXTENDED_ENV

使用:
    python test_extended_debug.py --symbol SUI/USD --size 10.0 --limit-offset 0.03
"""

import sys
import logging
import os
from decimal import Decimal

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv

# 配置日志为 DEBUG 级别以查看详细信息
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

load_dotenv()

def test_extended_order(symbol: str = "SUI/USD", size: float = 10.0, limit_offset: float = 0.03):
    """测试 Extended 订单提交"""
    
    print(f"\n{'='*80}")
    print(f"Extended 订单调试测试")
    print(f"{'='*80}\n")
    
    try:
        from perpbot.exchanges.extended import ExtendedClient
        from perpbot.models import OrderRequest
        
        # 初始化客户端
        print("📋 步骤 1: 初始化 Extended 客户端...")
        client = ExtendedClient()
        client.connect()
        print("✅ 连接成功\n")
        
        # 获取行情
        print(f"📊 步骤 2: 获取 {symbol} 行情...")
        quote = client.get_current_price(symbol)
        print(f"✅ 行情数据:")
        print(f"   Bid: {quote.bid}")
        print(f"   Ask: {quote.ask}\n")
        
        # 计算限价
        mid_price = (quote.bid + quote.ask) / 2
        limit_price = mid_price - (mid_price * limit_offset)  # 低于市价
        print(f"📈 步骤 3: 计算限价订单价格...")
        print(f"   中间价: {mid_price}")
        print(f"   偏移: {limit_offset*100}%")
        print(f"   限价: {limit_price}\n")
        
        # 创建订单请求
        print(f"🔧 步骤 4: 创建订单请求...")
        request = OrderRequest(
            symbol=symbol,
            side="buy",
            size=Decimal(str(size)),
            limit_price=limit_price
        )
        print(f"✅ 订单请求:")
        print(f"   Symbol: {request.symbol}")
        print(f"   Side: {request.side}")
        print(f"   Size: {request.size} (type: {type(request.size).__name__})")
        print(f"   Limit Price: {request.limit_price} (type: {type(request.limit_price).__name__})\n")
        
        # 提交订单
        print(f"📤 步骤 5: 提交限价订单...")
        print(f"   (此步骤可能会失败，检查下面的调试信息)\n")
        
        try:
            result = client.place_open_order(request)
            
            if result.order_id.startswith("error"):
                print(f"❌ 订单提交失败:")
                print(f"   错误: {result.error}\n")
            else:
                print(f"✅ 订单提交成功:")
                print(f"   Order ID: {result.order_id}")
                print(f"   Status: {result.status}")
                print(f"   Notional: {result.notional}\n")
                
                # 查询订单信息
                print(f"🔍 步骤 6: 查询订单信息...")
                order_info = client.get_order_info(result.order_id)
                if order_info:
                    print(f"✅ 订单信息: {order_info}\n")
                else:
                    print(f"⚠️  无法获取订单信息\n")
        
        except Exception as e:
            print(f"❌ 订单提交异常:")
            print(f"   异常类型: {type(e).__name__}")
            print(f"   异常信息: {e}\n")
        
        # 获取调试信息
        print(f"🔧 步骤 7: 获取调试信息...")
        
        last_payload = client.get_last_payload()
        if last_payload:
            print(f"📋 最后的 Payload:")
            for key, value in last_payload.items():
                print(f"   {key}: {value} (type: {type(value).__name__})\n")
        else:
            print(f"⚠️  无 Payload 信息\n")
        
        last_error = client.get_last_order_error()
        if last_error:
            print(f"❌ 最后的错误: {last_error}\n")
        
        last_response = client.get_last_response()
        if last_response:
            print(f"📨 最后的响应:")
            print(f"   {last_response}\n")
        
        client.disconnect()
        print("✅ 测试完成")
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print(f"   请确保已安装依赖: pip install -r requirements/extended.txt")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Extended 订单调试脚本")
    parser.add_argument("--symbol", default="SUI/USD", help="交易对 (默认: SUI/USD)")
    parser.add_argument("--size", type=float, default=10.0, help="订单大小 (默认: 10.0)")
    parser.add_argument("--limit-offset", type=float, default=0.03, help="限价偏移比例 (默认: 0.03)")
    
    args = parser.parse_args()
    
    test_extended_order(
        symbol=args.symbol,
        size=args.size,
        limit_offset=args.limit_offset
    )
