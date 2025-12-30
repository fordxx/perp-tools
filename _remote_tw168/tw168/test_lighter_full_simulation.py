#!/usr/bin/env python3
"""Lighter完整模拟测试 - 从TradingView信号到订单计算的端到端流程"""
import asyncio
import sys
from pathlib import Path
from decimal import Decimal, ROUND_DOWN

sys.path.insert(0, str(Path(__file__).parent))

from app.lighter_adapter import create_lighter_adapter
from app.config import SETTINGS
from app.risk import stop_loss_price, stop_loss_price_lookback, take_profit_price


def _format_decimal(value: Decimal) -> str:
    """格式化Decimal为字符串"""
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _normalize_qty(qty: Decimal, *, step: Decimal | None, min_sz: Decimal | None) -> Decimal:
    """标准化数量到交易所精度"""
    if step and step > 0:
        qty = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
    else:
        qty = qty.to_integral_value(rounding=ROUND_DOWN)
    if min_sz and qty < min_sz:
        qty = min_sz
    return qty


async def simulate_trading_signal(
    adapter,
    *,
    inst_id: str,
    tf: str,
    side: str,
    signal_price: float | None = None,
) -> dict:
    """模拟处理一个交易信号的完整流程
    
    Args:
        adapter: Lighter adapter实例
        inst_id: 合约ID (e.g., "ETH-USDT-SWAP")
        tf: 时间周期 (e.g., "1h", "15m")
        side: 方向 ("buy" or "sell")
        signal_price: 信号价格（可选，None则使用最新K线收盘价）
    
    Returns:
        包含所有计算结果的字典
    """
    print(f"\n{'='*70}")
    print(f"📡 模拟信号: {inst_id} / {tf} / {side.upper()}")
    print("="*70)
    
    # 1. 获取K线数据
    print("\n📊 步骤1: 获取K线数据...")
    limit = 300  # 获取足够的历史数据用于计算
    candles = await adapter.fetch_candles(
        inst_id=inst_id,
        tf=tf,
        limit=limit
    )
    
    if not candles:
        print(f"❌ 无法获取K线数据")
        return {"ok": False, "error": "no_candles"}
    
    print(f"✅ 获取到 {len(candles)} 根K线")
    
    # 2. 确定入场价格
    if signal_price is None:
        entry_price = candles[-1].c
        print(f"💰 入场价格: {entry_price:.4f} (最新K线收盘价)")
    else:
        entry_price = signal_price
        print(f"💰 入场价格: {entry_price:.4f} (信号指定价格)")
    
    # 3. 计算止损价格 (两种方法)
    print("\n🛡️  步骤2: 计算止损价格...")
    
    # Pivot方法
    sl_pivot = stop_loss_price(
        side=side,
        entry_price=entry_price,
        candles=candles,
        pivot_len=SETTINGS.pivot_len,
        atr_len=SETTINGS.atr_len,
        atr_buffer_mult=SETTINGS.atr_buffer_mult,
        min_buffer_bps=SETTINGS.min_buffer_bps,
    )
    
    # Lookback方法
    from app.config import get_lookback_bars
    sl_lookback = stop_loss_price_lookback(
        side=side,
        entry_price=entry_price,
        candles=candles,
        lookback_bars=get_lookback_bars(tf),
        atr_len=SETTINGS.atr_len,
        atr_buffer_mult=SETTINGS.atr_buffer_mult,
        min_buffer_bps=SETTINGS.min_buffer_bps,
    )
    
    # 使用配置的方法
    if SETTINGS.stop_method == "pivot":
        sl = sl_pivot
        method = "Pivot"
    else:
        sl = sl_lookback
        method = "Lookback"
    
    if sl is None:
        print(f"❌ 无法计算止损价格")
        return {"ok": False, "error": "no_stoploss"}
    
    r_value = abs(entry_price - sl)
    risk_pct = (r_value / entry_price) * 100
    
    print(f"✅ 止损价格: {sl:.4f} ({method}方法)")
    print(f"   R值: {r_value:.4f} ({risk_pct:.2f}%)")
    if sl_pivot and sl_lookback:
        print(f"   对比: Pivot={sl_pivot:.4f} Lookback={sl_lookback:.4f}")
    
    # 4. 计算止盈价格 (多级)
    print("\n🎯 步骤3: 计算止盈价格...")
    
    tp_levels = []
    if SETTINGS.tp_enabled:
        for label, rr in [("TP1", SETTINGS.tp1_r), ("TP2", SETTINGS.tp2_r), 
                          ("TP3", SETTINGS.tp3_r), ("TP4", SETTINGS.tp4_r)]:
            tp = take_profit_price(
                side=side,
                entry_price=entry_price,
                stop_loss=sl,
                rr=rr,
            )
            if tp:
                profit = abs(tp - entry_price)
                profit_pct = (profit / entry_price) * 100
                tp_levels.append({
                    "label": label,
                    "rr": rr,
                    "price": tp,
                    "profit": profit,
                    "profit_pct": profit_pct,
                })
                print(f"   {label}: {tp:.4f} ({rr}R, +{profit_pct:.2f}%)")
    
    # 5. 计算仓位大小
    print("\n💼 步骤4: 计算仓位大小...")
    
    # 获取合约信息
    inst_info = await adapter.get_instrument_info(inst_id=inst_id)
    if not inst_info:
        print(f"❌ 无法获取合约信息")
        return {"ok": False, "error": "no_instrument_info"}
    
    lot_sz = Decimal(inst_info.get("lotSz", "0.01"))
    lot_step = Decimal(inst_info.get("lotStep", "0.01"))
    tick_sz = inst_info.get("tickSz", "0.01")
    
    print(f"   合约信息: lotSz={lot_sz} lotStep={lot_step} tickSz={tick_sz}")
    
    # 计算仓位（基于风险）
    from app.config import get_risk_per_trade
    risk_amount = get_risk_per_trade(tf)
    
    if risk_amount and risk_amount > 0 and r_value > 0:
        # 以损订仓模式
        risk_usdt = Decimal(str(risk_amount))
        r_value_dec = Decimal(str(r_value))
        ct_val_dec = Decimal("1")  # Lighter合约面值=1
        
        calculated_sz_coins = risk_usdt / r_value_dec
        calculated_sz_contracts = calculated_sz_coins / ct_val_dec
        order_sz = _normalize_qty(calculated_sz_contracts, step=lot_step, min_sz=lot_sz)
        
        print(f"   风险管理模式:")
        print(f"   - 风险金额: {risk_amount} USDT")
        print(f"   - R值: {r_value:.4f}")
        print(f"   - 计算数量: {calculated_sz_coins:.4f} 币")
        print(f"   - 标准化后: {order_sz} 张")
        print(f"   - 实际风险: {float(order_sz) * r_value:.2f} USDT")
    else:
        # 固定数量模式
        order_sz = _normalize_qty(Decimal(SETTINGS.order_sz), step=lot_step, min_sz=lot_sz)
        print(f"   固定数量模式: {order_sz} 张")
    
    # 6. 计算止盈分配
    print("\n📈 步骤5: 计算止盈分配...")
    
    def _floor_to_step(value: Decimal, step_value: Decimal) -> Decimal:
        if step_value <= 0:
            return value
        return (value / step_value).to_integral_value(rounding=ROUND_DOWN) * step_value
    
    tp1_sz = _floor_to_step(order_sz * Decimal(str(SETTINGS.tp1_pct)), lot_step)
    tp2_sz = _floor_to_step(order_sz * Decimal(str(SETTINGS.tp2_pct)), lot_step)
    tp3_sz = _floor_to_step(order_sz * Decimal(str(SETTINGS.tp3_pct)), lot_step)
    tp4_sz = order_sz - tp1_sz - tp2_sz - tp3_sz
    
    if tp4_sz < 0:
        tp4_sz = Decimal("0")
    
    tp_distribution = [
        ("TP1", tp1_sz, SETTINGS.tp1_r, SETTINGS.tp1_pct * 100),
        ("TP2", tp2_sz, SETTINGS.tp2_r, SETTINGS.tp2_pct * 100),
        ("TP3", tp3_sz, SETTINGS.tp3_r, SETTINGS.tp3_pct * 100),
        ("TP4", tp4_sz, SETTINGS.tp4_r, SETTINGS.tp4_pct * 100),
    ]
    
    for label, sz, rr, pct in tp_distribution:
        if sz > 0:
            print(f"   {label}: {_format_decimal(sz)} 张 ({pct:.0f}%, {rr}R)")
    
    # 7. 生成订单参数
    print("\n📋 步骤6: 生成订单参数...")
    
    pos_side = "long" if side == "buy" else "short"
    
    # 入场订单
    entry_order = {
        "inst_id": inst_id,
        "side": side,
        "pos_side": pos_side,
        "ord_type": "market",
        "sz": _format_decimal(order_sz),
        "px": None,
        "reduce_only": False,
    }
    
    # 止损订单
    sl_order = {
        "inst_id": inst_id,
        "side": "sell" if side == "buy" else "buy",
        "pos_side": pos_side,
        "ord_type": "conditional",
        "sz": _format_decimal(order_sz),
        "sl_trigger_px": f"{sl:.4f}",
        "sl_ord_px": "-1",
    }
    
    # 止盈订单
    tp_orders = []
    for (label, sz, rr, _), tp_info in zip(tp_distribution, tp_levels):
        if sz > 0 and tp_info:
            tp_orders.append({
                "label": label,
                "inst_id": inst_id,
                "side": "sell" if side == "buy" else "buy",
                "pos_side": pos_side,
                "ord_type": "conditional",
                "sz": _format_decimal(sz),
                "tp_trigger_px": f"{tp_info['price']:.4f}",
                "tp_ord_px": "-1",
            })
    
    print("✅ 订单参数已生成")
    
    # 8. 计算预期盈亏
    print("\n💹 步骤7: 预期盈亏分析...")
    
    # 最大亏损
    max_loss = float(order_sz) * r_value
    print(f"   最大亏损: -{max_loss:.2f} USDT (止损触发)")
    
    # 各级止盈利润
    total_profit = 0
    for (label, sz, rr, _), tp_info in zip(tp_distribution, tp_levels):
        if sz > 0 and tp_info:
            profit = float(sz) * tp_info['profit']
            total_profit += profit
            print(f"   {label}利润: +{profit:.2f} USDT ({_format_decimal(sz)}张 @ {rr}R)")
    
    if total_profit > 0:
        print(f"   总潜在利润: +{total_profit:.2f} USDT (全部止盈)")
        print(f"   风险回报比: 1:{total_profit/max_loss:.2f}")
    
    # 9. 返回完整结果
    return {
        "ok": True,
        "inst_id": inst_id,
        "tf": tf,
        "side": side,
        "pos_side": pos_side,
        "entry_price": entry_price,
        "stop_loss": sl,
        "r_value": r_value,
        "risk_pct": risk_pct,
        "stop_method": method,
        "tp_levels": tp_levels,
        "order_sz": _format_decimal(order_sz),
        "tp_distribution": [
            {"label": label, "sz": _format_decimal(sz), "rr": rr, "pct": pct}
            for label, sz, rr, pct in tp_distribution if sz > 0
        ],
        "entry_order": entry_order,
        "sl_order": sl_order,
        "tp_orders": tp_orders,
        "max_loss": max_loss,
        "total_profit": total_profit,
        "risk_reward": total_profit / max_loss if max_loss > 0 else 0,
        "candles_count": len(candles),
    }


async def run_simulation():
    """运行完整模拟测试"""
    print("="*70)
    print("🔥 Lighter完整模拟测试 - 端到端流程")
    print("="*70)
    print(f"\n配置信息:")
    print(f"  交易所: {SETTINGS.exchange}")
    print(f"  止损方法: {SETTINGS.stop_method}")
    print(f"  Pivot长度: {SETTINGS.pivot_len}")
    print(f"  ATR长度: {SETTINGS.atr_len}")
    print(f"  止盈启用: {SETTINGS.tp_enabled}")
    print(f"  交易启用: {SETTINGS.trading_enabled}")
    
    # 创建adapter
    adapter = create_lighter_adapter(use_testnet=False)
    
    try:
        # 连接
        print("\n🔌 连接Lighter...")
        await adapter.connect()
        print("✅ 连接成功\n")
        
        # 测试场景
        test_scenarios = [
            {
                "name": "ETH做多 (15分钟)",
                "inst_id": "ETH-USDT-SWAP",
                "tf": "15m",
                "side": "buy",
            },
            {
                "name": "BTC做空 (15分钟)",
                "inst_id": "BTC-USDT-SWAP",
                "tf": "15m",
                "side": "sell",
            },
            {
                "name": "ETH做空 (5分钟)",
                "inst_id": "ETH-USDT-SWAP",
                "tf": "5m",
                "side": "sell",
            },
        ]
        
        results = []
        for scenario in test_scenarios:
            print(f"\n{'#'*70}")
            print(f"# 场景: {scenario['name']}")
            print(f"{'#'*70}")
            
            result = await simulate_trading_signal(
                adapter,
                inst_id=scenario['inst_id'],
                tf=scenario['tf'],
                side=scenario['side'],
            )
            
            results.append({
                "scenario": scenario['name'],
                "result": result,
            })
        
        # 生成总结报告
        print("\n" + "="*70)
        print("📊 模拟测试总结")
        print("="*70)
        
        for item in results:
            scenario_name = item['scenario']
            result = item['result']
            
            if result.get('ok'):
                print(f"\n✅ {scenario_name}")
                print(f"   方向: {result['side'].upper()} ({result['pos_side']})")
                print(f"   入场: {result['entry_price']:.4f}")
                print(f"   止损: {result['stop_loss']:.4f} (R={result['r_value']:.4f}, {result['risk_pct']:.2f}%)")
                print(f"   数量: {result['order_sz']} 张")
                print(f"   最大亏损: -{result['max_loss']:.2f} USDT")
                print(f"   潜在利润: +{result['total_profit']:.2f} USDT")
                print(f"   风险回报: 1:{result['risk_reward']:.2f}")
            else:
                print(f"\n❌ {scenario_name}")
                print(f"   错误: {result.get('error', 'unknown')}")
        
        print("\n" + "="*70)
        print("✅ 模拟测试完成")
        print("="*70)
        
        # 验证关键功能
        print("\n🔍 功能验证清单:")
        all_ok = all(item['result'].get('ok') for item in results)
        print(f"   {'✅' if all_ok else '❌'} K线数据获取")
        print(f"   {'✅' if all_ok else '❌'} 止损价格计算")
        print(f"   {'✅' if all_ok else '❌'} 止盈价格计算")
        print(f"   {'✅' if all_ok else '❌'} 仓位大小计算")
        print(f"   {'✅' if all_ok else '❌'} 订单参数生成")
        
        return all_ok
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await adapter.disconnect()
        print("\n👋 连接已断开")


if __name__ == "__main__":
    success = asyncio.run(run_simulation())
    sys.exit(0 if success else 1)
