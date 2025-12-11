#!/usr/bin/env python3
"""
Paradex 完整止盈止损（TP/SL）测试脚本

测试功能：
1. 开仓（市价单）
2. 设置止盈止损价格
3. 实时监控价格变化
4. 触发止盈或止损后自动平仓

使用方法：
1. 配置 .env 文件
2. 运行：python test_tp_sl_complete.py
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import Optional, Literal

from dotenv import load_dotenv

# 添加 src 到 Python 路径
sys.path.insert(0, 'src')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

load_dotenv()


@dataclass
class TPSLConfig:
    """止盈止损配置"""
    symbol: str
    size: float
    side: Literal["buy", "sell"]
    take_profit: Optional[float] = None       # 止盈价格
    stop_loss: Optional[float] = None         # 止损价格
    poll_interval: float = 2.0                # 价格轮询间隔（秒）


def build_paradex_client():
    """构建 Paradex SDK 客户端"""
    from paradex_py import Paradex
    from paradex_py.environment import Environment
    from paradex_py.signer import PrivateKeySigner
    
    env_str = os.getenv("PARADEX_ENV", "TESTNET").upper()
    env = Environment.TESTNET if env_str == "TESTNET" else Environment.PROD
    
    l2_key = os.environ["PARADEX_L2_PRIVATE_KEY"]
    account_addr = os.environ["PARADEX_ACCOUNT_ADDRESS"]
    
    signer = PrivateKeySigner(l2_key)
    client = Paradex(env=env, signer=signer, account_address=account_addr)
    
    logger.info("✅ Paradex SDK 初始化完成，环境=%s", env.value)
    return client


def normalize_symbol(symbol: str) -> str:
    """Symbol 转换: ETH/USDT -> ETH-USD-PERP"""
    if "PERP" in symbol or "-" in symbol:
        return symbol
    base = symbol.split("/")[0]
    return f"{base}-USD-PERP"


async def place_market_order(client, symbol: str, size: float, side: str) -> dict:
    """下市价单"""
    from paradex_py.api.models.order import Order, OrderType, OrderSide, TimeInForce
    
    market = normalize_symbol(symbol)
    side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
    
    order = Order(
        market=market,
        price=None,  # 市价单
        size=size,
        side=side_enum,
        type=OrderType.MARKET,
        time_in_force=TimeInForce.FILL_OR_KILL,
        reduce_only=False,
        client_order_id=None,
    )
    
    result = client.submit_order(order)
    logger.info("✅ 下单成功: %s %s size=%s, 结果=%s", symbol, side, size, result)
    return result


async def fetch_current_price(client, symbol: str) -> float:
    """获取当前价格（BBO 中间价）"""
    market = normalize_symbol(symbol)
    bbo = client.fetch_bbo(market)
    
    best_bid = float(bbo["bestBidPrice"])
    best_ask = float(bbo["bestAskPrice"])
    mid = (best_bid + best_ask) / 2
    
    return mid


async def fetch_position(client, symbol: str) -> Optional[dict]:
    """查询指定交易对的持仓"""
    market = normalize_symbol(symbol)
    pos_res = client.fetch_positions()
    positions = pos_res.get("results", [])
    
    for p in positions:
        if p.get("market") == market and float(p.get("size", 0)) != 0:
            return p
    
    return None


async def close_position(client, symbol: str) -> Optional[dict]:
    """平仓（市价单）"""
    market = normalize_symbol(symbol)
    pos = await fetch_position(client, symbol)
    
    if not pos:
        logger.info("当前没有 %s 仓位，无需平仓", symbol)
        return None
    
    side = pos["side"]  # "BUY" 或 "SELL"
    size = abs(float(pos["size"]))
    
    logger.info("检测到仓位: market=%s side=%s size=%s avgEntryPrice=%s",
                market, side, size, pos.get("avgEntryPrice"))
    
    # 反向平仓
    close_side = "sell" if side.upper() == "BUY" else "buy"
    return await place_market_order(client, symbol, size, close_side)


async def run_tpsl_monitor(client, cfg: TPSLConfig) -> None:
    """
    止盈止损监控循环
    
    - 每隔 poll_interval 秒检查一次价格
    - 触发止盈或止损时自动平仓
    """
    logger.info("🚀 启动止盈止损监控:")
    logger.info("   - 交易对: %s", cfg.symbol)
    logger.info("   - 方向: %s", cfg.side.upper())
    logger.info("   - 数量: %s", cfg.size)
    logger.info("   - 止盈价: %s", cfg.take_profit)
    logger.info("   - 止损价: %s", cfg.stop_loss)
    logger.info("   - 轮询间隔: %.1f 秒", cfg.poll_interval)
    
    while True:
        try:
            # 获取当前价格
            price = await fetch_current_price(client, cfg.symbol)
            logger.info("📈 当前价格: $%.2f", price)
            
            triggered = False
            trigger_reason = ""
            
            # 检查止盈
            if cfg.take_profit is not None:
                if cfg.side == "buy" and price >= cfg.take_profit:
                    trigger_reason = f"止盈触发 (价格 ${price:.2f} >= 止盈价 ${cfg.take_profit:.2f})"
                    triggered = True
                elif cfg.side == "sell" and price <= cfg.take_profit:
                    trigger_reason = f"止盈触发 (价格 ${price:.2f} <= 止盈价 ${cfg.take_profit:.2f})"
                    triggered = True
            
            # 检查止损
            if not triggered and cfg.stop_loss is not None:
                if cfg.side == "buy" and price <= cfg.stop_loss:
                    trigger_reason = f"止损触发 (价格 ${price:.2f} <= 止损价 ${cfg.stop_loss:.2f})"
                    triggered = True
                elif cfg.side == "sell" and price >= cfg.stop_loss:
                    trigger_reason = f"止损触发 (价格 ${price:.2f} >= 止损价 ${cfg.stop_loss:.2f})"
                    triggered = True
            
            # 触发平仓
            if triggered:
                logger.warning("⚠️  %s，开始平仓...", trigger_reason)
                close_result = await close_position(client, cfg.symbol)
                
                if close_result:
                    logger.info("✅ 平仓成功！结果: %s", close_result)
                else:
                    logger.error("❌ 平仓失败")
                
                logger.info("🏁 止盈止损监控结束")
                return
            
            # 等待下次检查
            await asyncio.sleep(cfg.poll_interval)
        
        except Exception as e:
            logger.error("❌ 监控循环出错: %s", e)
            await asyncio.sleep(cfg.poll_interval)


async def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("  🚀 Paradex 止盈止损（TP/SL）完整测试")
    print("=" * 60)
    
    # 构建客户端
    client = build_paradex_client()
    
    # 测试参数
    symbol = "ETH/USDT"
    size = 0.004
    side = "buy"  # 做多
    
    # 获取当前价格
    current_price = await fetch_current_price(client, symbol)
    logger.info("📊 当前 %s 价格: $%.2f", symbol, current_price)
    
    # 设置止盈止损（示例）
    print("\n请设置止盈止损价格（示例基于当前价格）:")
    print(f"   当前价格: ${current_price:.2f}")
    print(f"   建议止盈（+2%）: ${current_price * 1.02:.2f}")
    print(f"   建议止损（-1%）: ${current_price * 0.99:.2f}")
    
    use_suggested = input("\n使用建议价格？(yes/no): ").strip().lower()
    
    if use_suggested == 'yes':
        take_profit = current_price * 1.02
        stop_loss = current_price * 0.99
    else:
        tp_input = input(f"请输入止盈价格（留空则不设置）: ").strip()
        sl_input = input(f"请输入止损价格（留空则不设置）: ").strip()
        
        take_profit = float(tp_input) if tp_input else None
        stop_loss = float(sl_input) if sl_input else None
    
    # 确认测试
    print("\n" + "=" * 60)
    print("  测试配置:")
    print(f"   - 交易对: {symbol}")
    print(f"   - 方向: {side.upper()}")
    print(f"   - 数量: {size}")
    print(f"   - 止盈价: ${take_profit:.2f}" if take_profit else "   - 止盈价: 未设置")
    print(f"   - 止损价: ${stop_loss:.2f}" if stop_loss else "   - 止损价: 未设置")
    print("=" * 60)
    
    confirm = input("\n⚠️  确认开始测试？(会真实下单，yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消测试")
        return
    
    # 步骤 1: 开仓
    logger.info("📝 步骤 1: 开仓（市价单）")
    order_result = await place_market_order(client, symbol, size, side)
    logger.info("开仓结果: %s", order_result)
    
    # 等待成交
    logger.info("⏳ 等待 5 秒让订单成交...")
    await asyncio.sleep(5)
    
    # 步骤 2: 查询持仓
    logger.info("📝 步骤 2: 查询持仓")
    position = await fetch_position(client, symbol)
    
    if not position:
        logger.error("❌ 未找到持仓，测试终止")
        return
    
    logger.info("✅ 持仓确认: side=%s size=%s avgEntryPrice=%s",
                position.get("side"), position.get("size"), position.get("avgEntryPrice"))
    
    # 步骤 3: 启动止盈止损监控
    logger.info("📝 步骤 3: 启动止盈止损监控")
    
    cfg = TPSLConfig(
        symbol=symbol,
        size=size,
        side=side,
        take_profit=take_profit,
        stop_loss=stop_loss,
        poll_interval=3.0,  # 每 3 秒检查一次
    )
    
    await run_tpsl_monitor(client, cfg)
    
    print("\n" + "=" * 60)
    print("  ✅ 止盈止损测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
    except Exception as e:
        logger.exception(f"测试过程中发生错误: %s", e)
