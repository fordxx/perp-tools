#!/usr/bin/env python3
"""
Paradex 交易功能测试脚本（SDK + L2 私钥版本）

✅ 使用 Paradex SDK (paradex-py)
✅ L2 私钥签名（Starknet）
✅ 支持主网和测试网

测试功能：
- 连接和认证（SDK 初始化）
- 查询价格
- 查询余额
- 查询持仓
- 下单（LIMIT 和 MARKET）
- 撤单
- 查询活跃订单

使用方法：
1. 安装依赖：pip install paradex-py
2. 配置 .env 文件：
   PARADEX_L2_PRIVATE_KEY=0x...
   PARADEX_ACCOUNT_ADDRESS=0x...
   PARADEX_ENV=testnet
3. 运行：python test_paradex.py
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


def test_connection(client: ParadexClient):
    """测试 1: 连接和认证（SDK 初始化）"""
    print_separator("测试 1: 连接 Paradex SDK")

    try:
        client.connect()

        if client._trading_enabled:
            print("✅ Paradex SDK 连接成功！")
            print(f"   - 交易模式: {'Testnet' if client.use_testnet else 'Mainnet'}")
            print(f"   - 交易启用: {client._trading_enabled}")
            print(f"   - 账户地址: {client.account_address[:10]}...{client.account_address[-6:]}")
            return True
        else:
            print("⚠️ Paradex SDK 初始化失败（可能缺少凭证）")
            print("   请检查 .env 文件中的 PARADEX_L2_PRIVATE_KEY 和 PARADEX_ACCOUNT_ADDRESS")
            return False

    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False


def test_price(client: ParadexClient, symbol: str = "BTC/USDT"):
    """测试 2: 查询价格"""
    print_separator(f"测试 2: 查询 {symbol} 价格")

    try:
        price = client.get_current_price(symbol)
        print(f"✅ 价格查询成功！")
        print(f"   - 买价 (Bid): ${price.bid:,.2f}")
        print(f"   - 卖价 (Ask): ${price.ask:,.2f}")
        print(f"   - 中间价: ${price.mid:,.2f}")
        return price
    except Exception as e:
        print(f"❌ 价格查询失败: {e}")
        return None


def test_orderbook(client: ParadexClient, symbol: str = "BTC/USDT"):
    """测试 3: 查询订单簿"""
    print_separator(f"测试 3: 查询 {symbol} 订单簿")

    try:
        book = client.get_orderbook(symbol, depth=5)
        print("✅ 订单簿查询成功！")

        print("\n📈 卖单（Ask）：")
        for price, size in reversed(book.asks[:5]):
            print(f"   ${price:,.2f}  |  {size:.4f}")

        print("\n" + "-" * 40)

        print("\n📉 买单（Bid）：")
        for price, size in book.bids[:5]:
            print(f"   ${price:,.2f}  |  {size:.4f}")

        return book
    except Exception as e:
        print(f"❌ 订单簿查询失败: {e}")
        return None


def test_balance(client: ParadexClient):
    """测试 4: 查询余额"""
    print_separator("测试 4: 查询账户余额")

    try:
        balances = client.get_account_balances()

        if not balances:
            print("ℹ️  没有余额数据（可能需要先充值）")
            return None

        print("✅ 余额查询成功！")
        for balance in balances:
            print(f"\n💰 {balance.asset}:")
            print(f"   - 可用: {balance.free:,.4f}")
            print(f"   - 冻结: {balance.locked:,.4f}")
            print(f"   - 总计: {balance.total:,.4f}")

        return balances
    except Exception as e:
        print(f"❌ 余额查询失败: {e}")
        return None


def test_positions(client: ParadexClient):
    """测试 5: 查询持仓"""
    print_separator("测试 5: 查询当前持仓")

    try:
        positions = client.get_account_positions()

        if not positions:
            print("ℹ️  当前没有持仓")
            return []

        print("✅ 持仓查询成功！")
        for i, pos in enumerate(positions, 1):
            print(f"\n📊 持仓 #{i}:")
            print(f"   - 交易对: {pos.order.symbol}")
            print(f"   - 方向: {'做多 (Long)' if pos.order.side == 'buy' else '做空 (Short)'}")
            print(f"   - 数量: {pos.order.size:.4f}")
            print(f"   - 开仓价: ${pos.order.price:,.2f}")

        return positions
    except Exception as e:
        print(f"❌ 持仓查询失败: {e}")
        return []


def test_active_orders(client: ParadexClient):
    """测试 6: 查询活跃订单"""
    print_separator("测试 6: 查询活跃订单")

    try:
        orders = client.get_active_orders()

        if not orders:
            print("ℹ️  当前没有活跃订单")
            return []

        print("✅ 活跃订单查询成功！")
        for i, order in enumerate(orders, 1):
            print(f"\n📝 订单 #{i}:")
            print(f"   - ID: {order.id}")
            print(f"   - 交易对: {order.symbol}")
            print(f"   - 方向: {order.side.upper()}")
            print(f"   - 数量: {order.size:.4f}")
            print(f"   - 价格: ${order.price:,.2f}")

        return orders
    except Exception as e:
        print(f"❌ 活跃订单查询失败: {e}")
        return []


def test_place_limit_order(client: ParadexClient, symbol: str = "ETH/USDT",
                          side: str = "buy", size: float = 0.004, price: float = None):
    """测试 7: 下限价单（LIMIT）"""
    print_separator("测试 7: 下限价单（LIMIT ORDER）")

    print(f"⚠️  准备下单：")
    print(f"   - 交易对: {symbol}")
    print(f"   - 方向: {side.upper()}")
    print(f"   - 数量: {size}")
    print(f"   - 价格: ${price:,.2f}" if price else "   - 价格: 需要指定")

    # 安全检查
    confirm = input("\n⚠️  这是真实下单！确认继续？(yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消下单")
        return None

    try:
        request = OrderRequest(
            symbol=symbol,
            side=side,
            size=size,
            limit_price=price,
        )

        order = client.place_open_order(request)

        if order.id.startswith("rejected") or order.id.startswith("error"):
            print(f"❌ 下单失败: Order ID = {order.id}")
            return None

        print("✅ 限价单下单成功！")
        print(f"   - 订单ID: {order.id}")
        print(f"   - 交易对: {order.symbol}")
        print(f"   - 方向: {order.side.upper()}")
        print(f"   - 数量: {order.size:.4f}")
        print(f"   - 价格: ${order.price:,.2f}")

        return order
    except Exception as e:
        print(f"❌ 下单失败: {e}")
        return None


def test_place_market_order(client: ParadexClient, symbol: str = "ETH/USDT",
                           side: str = "buy", size: float = 0.004):
    """测试 8: 下市价单（MARKET）"""
    print_separator("测试 8: 下市价单（MARKET ORDER）")

    print(f"⚠️  准备下市价单：")
    print(f"   - 交易对: {symbol}")
    print(f"   - 方向: {side.upper()}")
    print(f"   - 数量: {size}")

    # 安全检查
    confirm = input("\n⚠️⚠️⚠️  这是真实市价单，会立即成交！确认继续？(yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消下单")
        return None

    try:
        request = OrderRequest(
            symbol=symbol,
            side=side,
            size=size,
            limit_price=None,  # MARKET order
        )

        order = client.place_open_order(request)

        if order.id.startswith("rejected") or order.id.startswith("error"):
            print(f"❌ 下单失败: Order ID = {order.id}")
            return None

        print("✅ 市价单下单成功！")
        print(f"   - 订单ID: {order.id}")
        print(f"   - 交易对: {order.symbol}")
        print(f"   - 方向: {order.side.upper()}")
        print(f"   - 数量: {order.size:.4f}")
        print(f"   - 成交价: ${order.price:,.2f}")

        return order
    except Exception as e:
        print(f"❌ 下单失败: {e}")
        return None


def test_cancel_order(client: ParadexClient, order_id: str):
    """测试 9: 撤单"""
    print_separator(f"测试 9: 撤单（Order ID: {order_id}）")

    confirm = input(f"\n确认撤销订单 {order_id}？(yes/no): ").strip().lower()
    if confirm != 'yes':
        print("❌ 用户取消撤单")
        return False

    try:
        client.cancel_order(order_id)
        print("✅ 撤单成功！")
        return True
    except Exception as e:
        print(f"❌ 撤单失败: {e}")
        return False


def main():
    """主测试流程"""
    print("\n🚀 Paradex 交易功能测试（SDK + L2 私钥版本）")
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

    # 测试 1: 连接
    if not test_connection(client):
        print("\n❌ 连接失败，无法继续测试")
        print("\n💡 故障排查：")
        print("1. 检查 .env 文件是否存在")
        print("2. 确认 PARADEX_L2_PRIVATE_KEY 和 PARADEX_ACCOUNT_ADDRESS 已配置")
        print("3. 确认已安装 paradex-py: pip install paradex-py")
        return

    # 测试 2: 查询价格
    price = test_price(client, "ETH/USDT")

    # 测试 3: 查询订单簿
    test_orderbook(client, "ETH/USDT")

    # 测试 4: 查询余额
    test_balance(client)

    # 测试 5: 查询持仓
    test_positions(client)

    # 测试 6: 查询活跃订单
    active_orders = test_active_orders(client)

    # 询问是否继续下单测试
    print("\n" + "=" * 60)
    print("  以上测试完成，下面是真实下单测试")
    print("=" * 60)

    continue_test = input("\n是否继续下单测试？(yes/no): ").strip().lower()
    if continue_test != 'yes':
        print("\n✅ 测试完成！")
        return

    # 测试 7: 下限价单
    if price:
        # 设置一个远离市场价的限价单（不会立即成交）
        side = "buy"  # 默认买单
        test_limit_price = price.bid * 0.95  # 买单价格设置低于市价5%

        print(f"\n提示: 当前市场价 ${price.mid:,.2f}")
        print(f"建议限价单价格: ${test_limit_price:,.2f} (不会立即成交)")

        use_suggested = input("使用建议价格？(yes/no): ").strip().lower()
        if use_suggested == 'yes':
            limit_order = test_place_limit_order(
                client, "ETH/USDT", "buy", 0.004, test_limit_price
            )

            # 如果下单成功，等待3秒后撤单
            if limit_order and not limit_order.id.startswith("rejected"):
                print("\n等待 3 秒后撤单...")
                time.sleep(3)
                test_cancel_order(client, limit_order.id)

    # 测试 8: 下市价单（可选）
    test_market = input("\n⚠️  是否测试市价单？(市价单会立即成交，yes/no): ").strip().lower()
    if test_market == 'yes':
        test_place_market_order(client, "ETH/USDT", "buy", 0.004)

    print("\n" + "=" * 60)
    print("  ✅ 所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断测试")
    except Exception as e:
        logger.exception(f"测试过程中发生错误: {e}")
