#!/usr/bin/env python3
"""测试Lighter K线数据获取功能"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.lighter_adapter import create_lighter_adapter
from app.risk import stop_loss_price, take_profit_price


async def test_lighter_candles():
    """测试从Lighter获取K线并计算止盈止损"""
    print("=" * 60)
    print("🔥 测试Lighter K线数据获取")
    print("=" * 60)
    
    # Create adapter
    adapter = create_lighter_adapter(use_testnet=False)
    
    try:
        # Connect
        await adapter.connect()
        print("✅ 连接成功\n")
        
        # Test symbols and timeframes
        test_cases = [
            ("EIGEN-USDT-SWAP", "1h", 100),
            ("ETH-USDT-SWAP", "15m", 50),
            ("BTC-USDT-SWAP", "5m", 200),
        ]
        
        for inst_id, tf, limit in test_cases:
            print(f"\n{'='*60}")
            print(f"📊 测试: {inst_id} / {tf} / limit={limit}")
            print("=" * 60)
            
            # Fetch candles
            candles = await adapter.fetch_candles(
                inst_id=inst_id,
                tf=tf,
                limit=limit
            )
            
            if not candles:
                print(f"❌ 未获取到K线数据")
                continue
            
            print(f"✅ 获取到 {len(candles)} 根K线")
            
            # Show first and last candle
            first = candles[0]
            last = candles[-1]
            
            print(f"\n首根K线:")
            print(f"  时间: {first.ts_ms}")
            print(f"  开: {first.o:.4f}  高: {first.h:.4f}")
            print(f"  低: {first.l:.4f}  收: {first.c:.4f}")
            
            print(f"\n末根K线:")
            print(f"  时间: {last.ts_ms}")
            print(f"  开: {last.o:.4f}  高: {last.h:.4f}")
            print(f"  低: {last.l:.4f}  收: {last.c:.4f}")
            
            # Calculate stop loss and take profit
            entry_price = last.c
            
            # Test buy (long) scenario
            sl = stop_loss_price(
                side="buy",
                entry_price=entry_price,
                candles=candles,
                pivot_len=3,
                atr_len=14,
                atr_buffer_mult=0.2,
                min_buffer_bps=3.0,
            )
            
            if sl:
                tp = take_profit_price(
                    side="buy",
                    entry_price=entry_price,
                    stop_loss=sl,
                    rr=2.0,
                )
                
                r_value = entry_price - sl
                risk_pct = (r_value / entry_price) * 100
                
                print(f"\n💡 做多场景 (基于pivot方法):")
                print(f"  入场: {entry_price:.4f}")
                print(f"  止损: {sl:.4f} (距离 {r_value:.4f}, {risk_pct:.2f}%)")
                if tp:
                    print(f"  止盈: {tp:.4f} (2R)")
            
            # Test sell (short) scenario  
            sl_short = stop_loss_price(
                side="sell",
                entry_price=entry_price,
                candles=candles,
                pivot_len=3,
                atr_len=14,
                atr_buffer_mult=0.2,
                min_buffer_bps=3.0,
            )
            
            if sl_short:
                tp_short = take_profit_price(
                    side="sell",
                    entry_price=entry_price,
                    stop_loss=sl_short,
                    rr=2.0,
                )
                
                r_value_short = sl_short - entry_price
                risk_pct_short = (r_value_short / entry_price) * 100
                
                print(f"\n💡 做空场景 (基于pivot方法):")
                print(f"  入场: {entry_price:.4f}")
                print(f"  止损: {sl_short:.4f} (距离 {r_value_short:.4f}, {risk_pct_short:.2f}%)")
                if tp_short:
                    print(f"  止盈: {tp_short:.4f} (2R)")
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await adapter.disconnect()
        print("\n👋 连接已断开")
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_lighter_candles())
    sys.exit(0 if success else 1)
