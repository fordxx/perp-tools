import time
from perpbot.exchanges.extended import ExtendedClient
from perpbot.models import OrderRequest, Side


# ----------------------------------------------------------
# Helpers
# ----------------------------------------------------------
def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def wait(seconds=1):
    time.sleep(seconds)


# ----------------------------------------------------------
# Limit Order Test
# ----------------------------------------------------------
def test_limit_order(client: ExtendedClient, symbol: str, size: float, limit_price: float):
    print_header("测试：限价单 + 撤单")

    print(f"准备提交 LIMIT BUY {size} {symbol} @ {limit_price}")

    req = OrderRequest(
        symbol=symbol,
        side="buy",
        size=size,
        limit_price=limit_price,
    )

    order = client.place_open_order(req)

    print(f"➡️ 已提交 | ID={order.id} | 价格={order.price}")
    wait(1)

    print("尝试撤单...")
    client.cancel_order(order.id)

    print(f"➡️ 撤单完成 | ID={order.id}")


# ----------------------------------------------------------
# Market(IOC Limit) Test
# ----------------------------------------------------------
def test_market_order(client: ExtendedClient, symbol: str, size: float):
    print_header("测试：市价（IOC-Limit）开仓 + 平仓")

    req = OrderRequest(
        symbol=symbol,
        side="buy",
        size=size,
    )

    order = client.place_open_order(req)
    print(f"➡️ 市价单提交 | ID={order.id}")

    wait(1)

    # Try close position
    print("检查是否有持仓用于平仓...")
    positions = client.get_account_positions()

    if not positions:
        print("⚠️ 无持仓，跳过平仓")
        return

    pos = positions[0]
    current_price = client.get_order_price(symbol)

    print(f"➡️ 平仓 {size} @ {current_price}")
    close_order = client.place_close_order(pos, current_price)

    print(f"➡️ 平仓提交 | ID={close_order.id}")


# ----------------------------------------------------------
# Main
# ----------------------------------------------------------
def main():
    symbol = "SUI/USD"
    size = 10
    limit_offset = 0.03

    print_header("测试 1：连接 Extended")

    client = ExtendedClient(use_testnet=False)
    client.connect()
    print("✅ Extended 已连接")

    # ------------------------------------------------------
    print_header("测试 2：价格")
    quote = client.get_current_price(symbol)
    print(f"Bid={quote.bid} | Ask={quote.ask} | Mid={quote.mid}")

    # ------------------------------------------------------
    print_header("测试 3：订单簿")
    ob = client.get_orderbook(symbol)
    if ob.asks:
        print(f"最佳卖盘: {ob.asks[0]}")
    else:
        print("ℹ️ 当前卖盘无数据")
    if ob.bids:
        print(f"最佳买盘: {ob.bids[0]}")
    else:
        print("ℹ️ 当前买盘无数据")

    # ------------------------------------------------------
    print_header("测试 4：账户余额")
    balances = client.get_account_balances()
    for b in balances:
        print(f"💰 {b.asset} | 可用={b.free} | 锁定={b.locked} | 总计={b.total}")

    # ------------------------------------------------------
    print_header("测试 5：持仓")
    positions = client.get_account_positions()
    if not positions:
        print("ℹ️ 当前无持仓")
    else:
        for pos in positions:
            print(f"📊 {pos.order.symbol} | {pos.order.side.upper()} | 数量={pos.order.size} | 价格={pos.order.price}")

    # ======================================================
    # 实盘测试 A：Limit + Cancel
    # ======================================================
    quote = client.get_current_price(symbol)
    limit_price = quote.bid * (1 - limit_offset)
    test_limit_order(client, symbol, size, limit_price)

    # ======================================================
    # 实盘测试 B：Market (IOC-Limit)
    # ======================================================
    test_market_order(client, symbol, size)


if __name__ == "__main__":
    main()
