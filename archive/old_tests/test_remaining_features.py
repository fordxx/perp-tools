#!/usr/bin/env python3
"""
Paradex 剩余功能测试脚本
专门测试：撤单、平仓、WebSocket推送、止盈止损
"""

import sys
import time
import asyncio
import logging
from decimal import Decimal

sys.path.insert(0, 'src')

from perpbot.exchanges.paradex import ParadexClient
from perpbot.models import OrderRequest

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_cancel_order():
    """测试 1: 撤单功能"""
    print_section("测试 1: 撤单功能")

    client = ParadexClient(use_testnet=False)  # 使用主网
    client.connect()

    if not client._trading_enabled:
        print("❌ 交易未启用，跳过测试")
        return

    # 1. 查询当前活跃订单
    print("\n📋 查询当前活跃订单...")
    active_orders = client.get_active_orders()

    if not active_orders:
        print("ℹ️  当前没有活跃订单")
        print("\n💡 测试计划：")
        print("   1. 先下一个远离市价的限价单")
        print("   2. 然后立即撤销它")

        # 获取当前价格
        price = client.get_current_price("ETH/USDT")
        print(f"\n当前市价: ${price.mid:.2f}")

        # 下一个不会成交的限价买单（价格低于市价20%）
        test_price = round(price.bid * 0.80, 2)
        print(f"下限价买单: 0.004 ETH @ ${test_price:.2f}")

        request = OrderRequest(
            symbol="ETH/USDT",
            side="buy",
            size=0.004,
            limit_price=test_price,
        )

        order = client.place_open_order(request)

        if order.id.startswith("rejected") or order.id.startswith("error"):
            print(f"❌ 下单失败: {order.id}")
            return

        print(f"✅ 订单已创建: ID = {order.id}")
        time.sleep(2)  # 等待订单确认

        # 撤销订单
        print(f"\n🔄 撤销订单 {order.id}...")
        try:
            client.cancel_order(order.id)
            print("✅ 撤单成功！")
        except Exception as e:
            print(f"❌ 撤单失败: {e}")
    else:
        print(f"\n找到 {len(active_orders)} 个活跃订单：")
        for i, order in enumerate(active_orders, 1):
            print(f"\n订单 #{i}:")
            print(f"  - ID: {order.id}")
            print(f"  - 交易对: {order.symbol}")
            print(f"  - 方向: {order.side.upper()}")
            print(f"  - 数量: {order.size}")
            print(f"  - 价格: ${order.price:.2f}")

        # 撤销第一个订单
        first_order = active_orders[0]
        print(f"\n🔄 撤销第一个订单 {first_order.id}...")
        try:
            client.cancel_order(first_order.id)
            print("✅ 撤单成功！")
        except Exception as e:
            print(f"❌ 撤单失败: {e}")


def test_close_position():
    """测试 2: 平仓功能"""
    print_section("测试 2: 平仓功能")

    client = ParadexClient(use_testnet=False)  # 使用主网
    client.connect()

    if not client._trading_enabled:
        print("❌ 交易未启用，跳过测试")
        return

    # 查询当前持仓
    print("\n📊 查询当前持仓...")
    positions = client.get_account_positions()

    if not positions:
        print("ℹ️  当前没有持仓")
        print("\n💡 测试计划：")
        print("   1. 先开一个小仓位（0.004 ETH）")
        print("   2. 然后立即平仓")

        # 获取当前价格
        price = client.get_current_price("ETH/USDT")
        print(f"\n当前市价: ${price.mid:.2f}")

        # 下市价单开仓
        print("\n📈 开仓: 买入 0.004 ETH...")
        request = OrderRequest(
            symbol="ETH/USDT",
            side="buy",
            size=0.004,
            limit_price=None,  # 市价单
        )

        open_order = client.place_open_order(request)

        if open_order.id.startswith("rejected") or open_order.id.startswith("error"):
            print(f"❌ 开仓失败: {open_order.id}")
            return

        print(f"✅ 开仓成功: ID = {open_order.id}")
        time.sleep(3)  # 等待持仓确认

        # 重新查询持仓
        positions = client.get_account_positions()
        if not positions:
            print("⚠️  开仓后仍未发现持仓，请稍后手动检查")
            return

    # 显示持仓信息
    print(f"\n找到 {len(positions)} 个持仓：")
    for i, pos in enumerate(positions, 1):
        print(f"\n持仓 #{i}:")
        print(f"  - 交易对: {pos.order.symbol}")
        print(f"  - 方向: {'做多 (Long)' if pos.order.side == 'buy' else '做空 (Short)'}")
        print(f"  - 数量: {pos.order.size}")
        print(f"  - 开仓价: ${pos.order.price:.2f}")

    # 平仓第一个持仓
    first_pos = positions[0]
    current_price = client.get_current_price(first_pos.order.symbol)

    print(f"\n🔄 平仓 {first_pos.order.symbol}...")
    print(f"   当前市价: ${current_price.mid:.2f}")

    try:
        close_order = client.place_close_order(first_pos, current_price.mid)

        if close_order.id.startswith("rejected") or close_order.id.startswith("error"):
            print(f"❌ 平仓失败: {close_order.id}")
        else:
            print(f"✅ 平仓成功: ID = {close_order.id}")
            print(f"   成交价: ${close_order.price:.2f}")
    except Exception as e:
        print(f"❌ 平仓失败: {e}")


def test_websocket_updates():
    """测试 3: WebSocket 订单和持仓更新"""
    print_section("测试 3: WebSocket 实时推送")

    print("💡 这个测试需要使用异步脚本")
    print("   请运行: python test_paradex_ws_tp_sl.py")
    print("\nWebSocket 功能包括：")
    print("  - 订单状态更新（ORDERS 频道）")
    print("  - 持仓变动推送（POSITIONS 频道）")
    print("  - 实时价格推送（BBO 频道）")


def test_local_tp_sl():
    """测试 4: 本地止盈止损"""
    print_section("测试 4: 本地止盈止损")

    print("💡 这个测试需要使用异步脚本")
    print("   请运行: python test_paradex_ws_tp_sl.py")
    print("\n本地止盈止损功能：")
    print("  - 定期轮询价格（非挂单）")
    print("  - 到达止盈价时自动平仓")
    print("  - 到达止损价时自动平仓")
    print("  - 支持做多和做空")


def main():
    """主测试流程"""
    print("\n🧪 Paradex 剩余功能测试")
    print("⚠️  测试环境: MAINNET（主网 - 真实资金）")
    print("\n已测试的功能: ✅ 连接、价格查询、余额查询、开单")
    print("待测试的功能: ❌ 撤单、平仓、WebSocket、止盈止损")

    print("\n请选择要测试的功能：")
    print("1. 撤单功能")
    print("2. 平仓功能")
    print("3. WebSocket 推送（需要运行异步脚本）")
    print("4. 本地止盈止损（需要运行异步脚本）")
    print("5. 全部测试（1+2）")

    # 非交互模式：默认测试全部
    choice = "5"

    if choice == "1":
        test_cancel_order()
    elif choice == "2":
        test_close_position()
    elif choice == "3":
        test_websocket_updates()
    elif choice == "4":
        test_local_tp_sl()
    elif choice == "5":
        test_cancel_order()
        test_close_position()
        test_websocket_updates()
        test_local_tp_sl()

    print("\n" + "=" * 70)
    print("  测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断测试")
    except Exception as e:
        logger.exception(f"测试出错: {e}")
