#!/usr/bin/env python3
"""
Lighter 交易功能测试脚本
----------------------------------

该脚本用于对 Lighter DEX 进行快速冒烟测试，覆盖以下能力：
1. 连接与凭证校验
2. 行情数据（价格 / 订单簿）
3. 账户信息（余额 / 持仓 / 活跃订单）
4. 交易流程（限价单、撤单、市价开仓、平仓）

运行前请确认：
- 已在 .env 中配置 LIGHTER_API_KEY / LIGHTER_PRIVATE_KEY
- (可选) 设置 LIGHTER_ENV=mainnet/testnet，或通过 --env 覆盖
- 已安装 lighter-v1-python SDK (pip install lighter-v1-python)

Usage:
    python test_lighter.py --symbol ETH/USDT --size 0.002 --limit-offset 0.03
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from typing import List, Optional

# 将 src 加入路径，确保可以导入 perpbot
sys.path.insert(0, "src")

from perpbot.exchanges.lighter import LighterClient
from perpbot.models import Order, OrderRequest, Position


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lighter-test")


def print_section(title: str) -> None:
    """统一的分隔输出。"""
    bar = "=" * 70
    print(f"\n{bar}\n{title}\n{bar}")


def confirm(prompt: str) -> bool:
    """简单的 yes/no 确认，默认拒绝。"""
    answer = input(f"{prompt} (yes/no): ").strip().lower()
    return answer in {"y", "yes"}


def test_connection(client: LighterClient) -> bool:
    print_section("测试 1：连接与凭证")
    try:
        client.connect()
        if client._trading_enabled:
            env = "Testnet" if client.use_testnet else "Mainnet"
            print(f"✅ Lighter 已连接 ({env})，交易功能可用")
            return True
        print("⚠️ Lighter 连接成功，但交易功能未启用（缺少凭证？）")
    except Exception as exc:
        print(f"❌ 连接失败: {exc}")
    return False


def test_price(client: LighterClient, symbol: str):
    print_section(f"测试 2：{symbol} 价格")
    try:
        quote = client.get_current_price(symbol)
        print(
            f"✅ Bid: {quote.bid:.2f} | Ask: {quote.ask:.2f} | Mid: {quote.mid:.2f}"
        )
        return quote
    except Exception as exc:
        print(f"❌ 价格查询失败: {exc}")
        return None


def test_orderbook(client: LighterClient, symbol: str, depth: int = 5):
    print_section(f"测试 3：{symbol} 订单簿 (Top {depth})")
    try:
        book = client.get_orderbook(symbol, depth=depth)
        print("卖盘 (Ask):")
        for price, size in reversed(book.asks[:depth]):
            print(f"   {price:>10.2f} | {size:.4f}")
        print("买盘 (Bid):")
        for price, size in book.bids[:depth]:
            print(f"   {price:>10.2f} | {size:.4f}")
        return book
    except Exception as exc:
        print(f"❌ 订单簿查询失败: {exc}")
        return None


def test_balances(client: LighterClient):
    print_section("测试 4：账户余额")
    try:
        balances = client.get_account_balances()
        if not balances:
            print("ℹ️ 无余额数据（可能未充值或凭证缺失）")
            return []
        for bal in balances:
            print(
                f"💰 {bal.asset} | 可用: {bal.free:.4f} | 冻结: {bal.locked:.4f} | 总计: {bal.total:.4f}"
            )
        return balances
    except Exception as exc:
        print(f"❌ 余额查询失败: {exc}")
        return []


def test_positions(client: LighterClient):
    print_section("测试 5：持仓")
    try:
        positions = client.get_account_positions()
        if not positions:
            print("ℹ️ 当前无持仓")
            return []
        for pos in positions:
            direction = "做多" if pos.order.side == "buy" else "做空"
            print(
                f"📊 {pos.order.symbol} | {direction} | 数量: {pos.order.size:.4f} | 开仓价: {pos.order.price:.2f}"
            )
        return positions
    except Exception as exc:
        print(f"❌ 持仓查询失败: {exc}")
        return []


def test_active_orders(client: LighterClient):
    print_section("测试 6：活跃订单")
    try:
        orders = client.get_active_orders()
        if not orders:
            print("ℹ️ 当前无活跃订单")
            return []
        for order in orders:
            print(
                f"📝 {order.id} | {order.symbol} | {order.side.upper()} | {order.size:.4f} @ {order.price:.2f}"
            )
        return orders
    except Exception as exc:
        print(f"❌ 活跃订单查询失败: {exc}")
        return []


def place_limit_order(
    client: LighterClient, symbol: str, side: str, size: float, limit_price: float
) -> Optional[Order]:
    print_section("交易测试 A：限价单 + 撤单")
    print(
        f"准备提交 LIMIT {side.upper()} {size} {symbol} @ {limit_price:.2f}\n"
        "建议在远离市价的位置下单，避免立即成交。"
    )
    if not confirm("这是实盘限价单，是否继续？"):
        print("❌ 用户取消限价单测试")
        return None

    try:
        order = client.place_open_order(
            OrderRequest(symbol=symbol, side=side, size=size, limit_price=limit_price)
        )
        if order.id.startswith("error") or order.id.startswith("rejected"):
            print(f"❌ 下单失败: {order.id}")
            return None

        print(
            f"✅ 限价单已提交 | ID={order.id} | 价格={order.price:.2f} | 数量={order.size:.4f}"
        )
        time.sleep(2)

        if confirm("是否立即撤单？"):
            client.cancel_order(order.id, symbol=symbol)
            print("✅ 撤单成功")
        else:
            print("⚠️ 未自动撤单，请在 Lighter 界面手动处理")
        return order
    except Exception as exc:
        print(f"❌ 限价单流程失败: {exc}")
        return None


def place_market_order_and_close(
    client: LighterClient, symbol: str, side: str, size: float
) -> Optional[Order]:
    print_section("交易测试 B：市价开仓 + 平仓")
    print(f"准备提交 MARKET {side.upper()} {size} {symbol}")
    print("该操作会立即成交并产生真实持仓。")

    if not confirm("确认提交市价单？"):
        print("❌ 用户取消市价单测试")
        return None

    try:
        order = client.place_open_order(
            OrderRequest(symbol=symbol, side=side, size=size, limit_price=None)
        )
        if order.id.startswith("error") or order.id.startswith("rejected"):
            print(f"❌ 市价单失败: {order.id}")
            return None

        print(f"✅ 市价单成功，订单 ID={order.id}")
        time.sleep(3)

        if not confirm("是否立即平仓（市价）？"):
            print("⚠️ 未执行平仓，请自行管理该持仓")
            return order

        positions = client.get_account_positions()
        match = find_position(positions, symbol, side)
        if not match:
            print("⚠️ 未找到刚才的持仓，跳过平仓")
            return order

        close_order = client.place_close_order(match, current_price=order.price)
        print(f"✅ 平仓提交完成，ID={close_order.id}")
        return close_order
    except Exception as exc:
        print(f"❌ 市价单流程失败: {exc}")
        return None


def find_position(
    positions: List[Position], symbol: str, side: str
) -> Optional[Position]:
    """查找符合买卖方向的第一条持仓。"""
    closing_side = "sell" if side == "buy" else "buy"
    for pos in positions:
        if pos.order.symbol == symbol and pos.order.side == closing_side:
            return pos
    return None


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Lighter 交易所测试脚本")
    parser.add_argument("--symbol", default="ETH/USDT", help="交易对 (默认 ETH/USDT)")
    parser.add_argument("--size", type=float, default=0.002, help="测试下单数量")
    parser.add_argument(
        "--side", choices=["buy", "sell"], default="buy", help="下单方向"
    )
    parser.add_argument(
        "--limit-offset",
        type=float,
        default=0.03,
        help="限价偏移百分比 (例如 0.03 表示偏离 3%)",
    )
    parser.add_argument(
        "--skip-trading",
        action="store_true",
        help="只跑查询类测试，跳过真实下单",
    )
    parser.add_argument(
        "--env",
        choices=["mainnet", "testnet"],
        help="覆盖 LIGHTER_ENV，强制指定运行环境",
    )
    return parser


def suggest_limit_price(quote, side: str, offset: float) -> float:
    """根据方向和偏移量给出不易成交的价格。"""
    offset = max(offset, 0.0)
    if side == "buy":
        reference = quote.bid or quote.mid
        return reference * (1 - offset)
    reference = quote.ask or quote.mid
    return reference * (1 + offset)


def main():
    args = build_arg_parser().parse_args()

    if args.env:
        os.environ["LIGHTER_ENV"] = args.env

    client = LighterClient(use_testnet=(args.env == "testnet"))
    if not test_connection(client):
        print("\n❌ 无法继续后续测试，请检查环境变量或 API Key。")
        return

    quote = test_price(client, args.symbol)
    test_orderbook(client, args.symbol)
    test_balances(client)
    test_positions(client)
    test_active_orders(client)

    if args.skip_trading:
        print("\n✅ 已完成所有查询类测试（跳过实盘交易）。")
        return

    if not client._trading_enabled:
        print("\n⚠️ Trading 未启用，跳过交易测试。")
        return

    if quote:
        limit_price = suggest_limit_price(quote, args.side, args.limit_offset)
    else:
        limit_price = None

    if limit_price:
        place_limit_order(client, args.symbol, args.side, args.size, limit_price)
    else:
        print("⚠️ 无法计算限价参考价，跳过限价单测试。")

    place_market_order_and_close(client, args.symbol, args.side, args.size)


if __name__ == "__main__":
    main()
