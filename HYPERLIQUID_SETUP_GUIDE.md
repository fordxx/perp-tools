# Hyperliquid 交易所集成指南

## 概述

Hyperliquid 是一个高性能链上永续合约交易所，运行在自有的 L1 区块链上。本指南讲解如何在 PerpBot 中集成和使用 Hyperliquid 客户端。

## 关键特性

| 特性 | 说明 |
|------|------|
| **区块链** | Hyperliquid L1 |
| **合约类型** | 永续期货 + 现货 |
| **费用** | Maker 2.0bps, Taker 2.5bps |
| **杠杆** | 最高 20x |
| **单块吞吐** | 200k 订单/秒 |
| **最小细粒度** | 毫秒级（链上） |

## 环境变量配置

在 `.env` 文件中配置以下环境变量：

```bash
# Hyperliquid 账户配置
HYPERLIQUID_ACCOUNT_ADDRESS=0x...          # 你的钱包地址
HYPERLIQUID_PRIVATE_KEY=0x...              # 私钥（用于签署交易）
HYPERLIQUID_VAULT_ADDRESS=0x...            # 金库地址（可选）

# 环境选择
HYPERLIQUID_ENV=testnet                    # 或 mainnet（不推荐）
```

### 安全建议

1. **不要提交私钥到版本控制**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **使用专用钱包**
   - 不要用主钱包的私钥
   - 为测试分配少量资金

3. **测试环境优先**
   ```bash
   HYPERLIQUID_ENV=testnet  # 默认使用测试网
   ```

## 快速开始

### 1. 基础连接测试

```bash
# 运行完整测试套件
python test_hyperliquid.py --symbol BTC/USDC

# 输出:
# ======================================================================
#   TEST 1: Connection
# ======================================================================
# ✅ Connection successful
#    Base URL: https://testnet.api.hyperliquid.xyz
#    Trading enabled: False
#    Account: Not configured
```

### 2. 启用交易功能

设置环境变量后重新运行：

```bash
python test_hyperliquid.py --symbol ETH/USDC --size 0.01
```

### 3. 在 PerpBot 中使用

```python
from perpbot.exchanges.hyperliquid import HyperliquidClient
from perpbot.models import OrderRequest, Side

# 初始化客户端
client = HyperliquidClient(use_testnet=True)
client.connect()

# 获取价格
price_quote = client.get_current_price("BTC/USDC")
print(f"BTC/USDC: {price_quote.bid:.2f} / {price_quote.ask:.2f}")

# 查看订单簿
orderbook = client.get_orderbook("ETH/USDC", depth=20)
print(f"Top bid: {orderbook.bids[0][0]}, size: {orderbook.bids[0][1]}")
print(f"Top ask: {orderbook.asks[0][0]}, size: {orderbook.asks[0][1]}")

# 查看持仓
positions = client.get_account_positions()
for pos in positions:
    print(f"{pos.symbol}: {pos.size} @ {pos.entry_price}")

# 查看余额
balances = client.get_account_balances()
for bal in balances:
    print(f"{bal.asset}: {bal.total:.2f} (free: {bal.free:.2f})")

# 下单
order_req = OrderRequest(
    symbol="BTC/USDC",
    side=Side.BUY,
    price=42000.0,
    quantity=0.01,
    order_type="limit"
)
order = client.place_open_order(order_req)
print(f"Order placed: {order.id}")

# 平仓
if positions:
    pos = positions[0]
    close_order = client.place_close_order(pos, price_quote.bid)
    print(f"Close order: {close_order.id}")
```

## API 方法参考

### get_current_price(symbol: str) -> PriceQuote

获取当前价格报价。

**参数：**
- `symbol`: 交易对（如 "BTC/USDC"）

**返回：**
- `PriceQuote` 对象，包含 bid, ask, timestamp

**示例：**
```python
quote = client.get_current_price("ETH/USDC")
mid_price = (quote.bid + quote.ask) / 2
spread_pct = (quote.ask - quote.bid) / quote.bid * 100
print(f"Mid: ${mid_price:.2f}, Spread: {spread_pct:.3f}%")
```

### get_orderbook(symbol: str, depth: int = 20) -> OrderBookDepth

获取订单簿快照。

**参数：**
- `symbol`: 交易对
- `depth`: 深度（默认20层）

**返回：**
- `OrderBookDepth` 对象，包含 bids, asks 数组

**示例：**
```python
ob = client.get_orderbook("BTC/USDC", depth=50)
total_bid_size = sum(size for _, size in ob.bids)
total_ask_size = sum(size for _, size in ob.asks)
print(f"Bid depth: {total_bid_size:.2f} BTC")
print(f"Ask depth: {total_ask_size:.2f} BTC")
```

### place_open_order(request: OrderRequest) -> Order

下单开仓。

**参数：**
- `request`: OrderRequest 对象

**返回：**
- `Order` 对象，包含 order_id 和状态

**示例：**
```python
order = client.place_open_order(OrderRequest(
    symbol="BTC/USDC",
    side=Side.BUY,
    price=42500.0,
    quantity=0.1,
    order_type="limit"
))
if not order.id.startswith("error"):
    print(f"Order {order.id} placed successfully")
else:
    print(f"Order failed: {order.id}")
```

### place_close_order(position: Position, current_price: float) -> Order

平仓。

**参数：**
- `position`: Position 对象
- `current_price`: 当前价格

**返回：**
- `Order` 对象

**示例：**
```python
positions = client.get_account_positions()
if positions:
    price = client.get_current_price(positions[0].symbol)
    close_order = client.place_close_order(positions[0], price.mid)
```

### get_active_orders(symbol: Optional[str] = None) -> List[Order]

获取活跃订单。

**参数：**
- `symbol`: 可选，按交易对过滤

**返回：**
- Order 列表

**示例：**
```python
orders = client.get_active_orders("ETH/USDC")
print(f"Active orders for ETH/USDC: {len(orders)}")
for order in orders:
    pct_filled = (order.filled_quantity / order.quantity * 100) if order.quantity > 0 else 0
    print(f"  {order.id}: {pct_filled:.1f}% filled")
```

### get_account_positions() -> List[Position]

获取所有持仓。

**返回：**
- Position 列表

**示例：**
```python
for pos in client.get_account_positions():
    pnl_pct = (pos.current_price - pos.entry_price) / pos.entry_price * 100
    print(f"{pos.symbol}: {pos.size} @ {pos.entry_price:.2f}, PnL {pnl_pct:+.2f}%")
```

### get_account_balances() -> List[Balance]

获取账户余额。

**返回：**
- Balance 列表

**示例：**
```python
for bal in client.get_account_balances():
    print(f"{bal.asset}: {bal.total:.2f} (free: {bal.free:.2f}, locked: {bal.locked:.2f})")
```

### cancel_order(order_id: str, symbol: Optional[str] = None) -> None

取消订单。

**参数：**
- `order_id`: 订单 ID
- `symbol`: 可选，交易对

**示例：**
```python
orders = client.get_active_orders()
if orders:
    client.cancel_order(orders[0].id)
    print(f"Cancelled {orders[0].id}")
```

## 测试网交易

### 获取测试网 USDC

1. 访问 [Hyperliquid Testnet Faucet](https://app.hyperliquid-testnet.xyz/)
2. 连接钱包
3. 领取测试 USDC

### 测试工作流

```bash
# 1. 查看价格和订单簿
python test_hyperliquid.py --symbol BTC/USDC --depth 20

# 2. 下小额测试单（价外限价）
python test_hyperliquid.py --symbol ETH/USDC --size 0.001

# 3. 查看活跃订单
python -c "
from src.perpbot.exchanges.hyperliquid import HyperliquidClient
client = HyperliquidClient(use_testnet=True)
client.connect()
for order in client.get_active_orders():
    print(f'{order.id}: {order.symbol} {order.quantity} @ {order.price}')
"

# 4. 取消订单
python -c "
from src.perpbot.exchanges.hyperliquid import HyperliquidClient
client = HyperliquidClient(use_testnet=True)
client.connect()
orders = client.get_active_orders()
if orders:
    client.cancel_order(orders[0].id)
"
```

## 集成到 PerpBot

### 1. 添加 Hyperliquid 到配置

编辑 `config.example.yaml`：

```yaml
exchanges:
  hyperliquid:
    maker_fee_bps: 2.0
    taker_fee_bps: 2.5
    funding_rate: 0.0
```

### 2. 在交易逻辑中使用

```python
from perpbot.exchanges.hyperliquid import HyperliquidClient
from perpbot.capital_orchestrator import CapitalOrchestrator

# 初始化所有交易所
hl_client = HyperliquidClient(use_testnet=True)
hl_client.connect()

# 用于套利/对冲逻辑
def execute_arbitrage():
    hl_price = hl_client.get_current_price("BTC/USDC")
    # ... 与其他交易所价格对比
    # ... 执行套利
```

## 性能优化

### 价格缓存

客户端内置了 2 秒的价格缓存：

```python
import time

# 第一次获取（实时API）- ~200ms
start = time.time()
price1 = client.get_current_price("BTC/USDC")
print(f"First: {time.time() - start:.3f}s")

# 第二次获取（缓存）- ~1ms
start = time.time()
price2 = client.get_current_price("BTC/USDC")
print(f"Second: {time.time() - start:.3f}s")
```

## 常见问题

### Q: 如何区分测试网和主网？

```python
# 测试网（推荐）
client = HyperliquidClient(use_testnet=True)

# 主网（谨慎使用）
client = HyperliquidClient(use_testnet=False)
```

### Q: 怎样启用交易功能？

设置环境变量：
```bash
export HYPERLIQUID_ACCOUNT_ADDRESS=0x...
export HYPERLIQUID_PRIVATE_KEY=0x...
export HYPERLIQUID_ENV=testnet
```

### Q: 订单没有填充？

检查：
1. 价格是否太离市场（设置合理的 limit price）
2. 账户余额是否足够（包括保证金要求）
3. 交易对是否有流动性

### Q: 怎样监控订单状态？

```python
orders = client.get_active_orders("BTC/USDC")
for order in orders:
    filled_pct = (order.filled_quantity / order.quantity) * 100
    print(f"{order.id}: {filled_pct:.1f}% filled")
```

## API 限制

- 请求频率：不超过 10 req/s
- 单个持仓大小：符合资金要求
- 订单有效期：直到取消或填充

## 故障排除

### 连接错误

```
❌ Connection failed: <HTTPError>
```

**解决：**
1. 检查网络连接
2. 检查 BASE_URL 是否正确
3. 检查防火墙设置

### 订单被拒绝

```
Order status: rejected
```

**可能原因：**
1. 交易未启用（缺少私钥）
2. 价格格式错误
3. 余额不足
4. 维护窗口

### 账户信息为空

```
Account address not set - read-only mode
```

**解决：**
设置 `HYPERLIQUID_ACCOUNT_ADDRESS` 环境变量

## 下一步

1. ✅ 在测试网上测试所有功能
2. 💰 在测试网上模拟套利交易
3. 📊 集成到实时风控系统
4. 🚀 与其他交易所组建跨交易所对冲池

## 参考资源

- [Hyperliquid 官方文档](https://hyperliquid.gitbook.io/hyperliquid-docs)
- [API 端点](https://hyperliquid.gitbook.io/hyperliquid-docs/api)
- [Python 客户端](https://github.com/hyperliquid-dex/hyperliquid-python-sdk)
- [测试网应用](https://app.hyperliquid-testnet.xyz/)

## 支持

有问题？提交 Issue 或查看项目 README。
