# Lighter DEX Integration - Implementation Summary

## 概述

Lighter是一个基于Ethereum Layer 2的去中心化永续合约交易所，使用zk-rollup技术实现零手续费交易。

本实现为perp-tools添加了完整的Lighter DEX交易支持，包括：
- 市价单/限价单
- 止损单（Stop-Loss）
- 止盈单（Take-Profit）
- 平仓功能

## 技术特性

- **零手续费**: 链上交易无gas费用
- **非托管**: 资金留在用户钱包，直到订单执行
- **可验证**: 使用zk-rollup保证订单匹配的可验证性
- **SDK**: 使用官方`lighter-sdk` (elliottech/lighter-python)

## 实现的功能

### 1. 连接与初始化 ✅

```python
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()
```

**环境变量**:
```bash
# 必需（交易功能）
LIGHTER_API_KEY_PRIVATE_KEY=0x...  # API密钥私钥（66字符，含0x）
LIGHTER_ACCOUNT_INDEX=123          # 账户索引（十进制）
LIGHTER_API_KEY_INDEX=0            # API密钥索引（通常为0）

# 可选
LIGHTER_ENV=mainnet                # mainnet或testnet
LIGHTER_API_BASE_URL=https://...   # 自定义API地址
LIGHTER_ORDERBOOK_CACHE_MS=250     # 订单簿缓存时间（毫秒）
```

### 2. 开仓订单 ✅

#### 市价单
```python
from perpbot.models import OrderRequest

# 市价买入
request = OrderRequest(
    symbol="ETH/USDT",
    side="buy",
    size=1.0,
    limit_price=None,  # 市价单
)

order = client.place_open_order(request)
```

#### 限价单
```python
# 限价买入
request = OrderRequest(
    symbol="ETH/USDT",
    side="buy",
    size=1.0,
    limit_price=3000.0,  # 限价
)

order = client.place_open_order(request)
```

### 3. 止损单 (Stop-Loss) ✅

```python
# 市价止损
order = client.place_stop_loss(
    symbol="ETH/USDT",
    side="sell",  # 平多仓
    size=1.0,
    trigger_price=2950.0,  # 触发价
    limit_price=None,      # 市价成交
)

# 限价止损
order = client.place_stop_loss(
    symbol="ETH/USDT",
    side="sell",
    size=1.0,
    trigger_price=2950.0,  # 触发价
    limit_price=2945.0,    # 限价成交
)
```

### 4. 止盈单 (Take-Profit) ✅

```python
# 市价止盈
order = client.place_take_profit(
    symbol="ETH/USDT",
    side="sell",  # 平多仓
    size=1.0,
    trigger_price=3100.0,  # 触发价
    limit_price=None,      # 市价成交
)

# 限价止盈
order = client.place_take_profit(
    symbol="ETH/USDT",
    side="sell",
    size=1.0,
    trigger_price=3100.0,  # 触发价
    limit_price=3105.0,    # 限价成交
)
```

### 5. 平仓 ✅

```python
from perpbot.models import Position, Order

# 假设有一个持仓
position = Position(
    id="pos123",
    order=Order(
        id="order123",
        exchange="lighter",
        symbol="ETH/USDT",
        side="buy",
        size=1.0,
        price=3000.0,
    ),
    target_profit_pct=0.0,
)

# 市价平仓（reduce_only=True）
current_price = 3050.0
close_order = client.place_close_order(position, current_price)
```

### 6. 行情查询 ✅

```python
# 获取当前价格
quote = client.get_current_price("ETH/USDT")
print(f"Bid: {quote.bid}, Ask: {quote.ask}")

# 获取订单簿
orderbook = client.get_orderbook("ETH/USDT", depth=20)
print(f"Best bid: {orderbook.bids[0]}")
print(f"Best ask: {orderbook.asks[0]}")
```

## 核心实现细节

### 市场配置获取

Lighter使用multipliers将人类可读的价格/数量转换为链上整数：

```python
async def _get_market_config_async(self, symbol: str) -> Tuple[int, int, int]:
    """获取市场配置（market_id, base_multiplier, price_multiplier）

    Returns:
        - market_id: 市场ID
        - base_multiplier: 数量乘数（size * multiplier = chain integer）
        - price_multiplier: 价格乘数（price * multiplier = chain integer）
    """
```

**示例**:
- ETH市场: `base_multiplier=10^18`, `price_multiplier=10^6`
- 下单1 ETH @ $3000: `base_amount=1*10^18`, `price=3000*10^6`

### 订单类型映射

Lighter SDK订单类型：

| 类型 | 常量 | 值 | 说明 |
|------|------|-----|------|
| LIMIT | ORDER_TYPE_LIMIT | 0 | 限价单 |
| MARKET | ORDER_TYPE_MARKET | 1 | 市价单 |
| STOP_LOSS | ORDER_TYPE_STOP_LOSS | 2 | 市价止损 |
| STOP_LOSS_LIMIT | ORDER_TYPE_STOP_LOSS_LIMIT | 3 | 限价止损 |
| TAKE_PROFIT | ORDER_TYPE_TAKE_PROFIT | 4 | 市价止盈 |
| TAKE_PROFIT_LIMIT | ORDER_TYPE_TAKE_PROFIT_LIMIT | 5 | 限价止盈 |

### 时效性 (Time in Force)

| 类型 | 常量 | 值 | 使用场景 |
|------|------|-----|----------|
| IOC | ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL | 0 | 市价单 |
| GTT | ORDER_TIME_IN_FORCE_GOOD_TILL_TIME | 1 | 限价/止损/止盈 |
| POST_ONLY | ORDER_TIME_IN_FORCE_POST_ONLY | 2 | 只做Maker |

### Reduce-Only 标志

- **开仓订单**: `reduce_only=False`
- **平仓订单**: `reduce_only=True`
- **止损/止盈**: `reduce_only=True`（必须）

## 测试

运行测试脚本验证实现：

```bash
# 设置环境变量
export LIGHTER_API_KEY_PRIVATE_KEY="0x..."
export LIGHTER_ACCOUNT_INDEX="123"
export LIGHTER_API_KEY_INDEX="0"

# 运行测试（只读测试，不执行交易）
python test_lighter_trading.py

# 测试网测试
LIGHTER_ENV=testnet python test_lighter_trading.py
```

测试内容：
1. ✅ 连接测试
2. ✅ 价格查询
3. ✅ 订单簿查询
4. ⚠️ 市价单（需确认）
5. ⚠️ 限价单（需确认）
6. ⚠️ 止损单（需确认）
7. ⚠️ 止盈单（需确认）

## 文件结构

```
perp-tools/
├── src/perpbot/exchanges/
│   └── lighter.py                 # Lighter客户端实现 ✅
├── test_lighter_trading.py        # 测试脚本 ✅
└── LIGHTER_IMPLEMENTATION.md      # 本文档 ✅
```

## API参考

### LighterClient 主要方法

| 方法 | 说明 | 状态 |
|------|------|------|
| `connect()` | 连接到Lighter | ✅ |
| `disconnect()` | 断开连接 | ✅ |
| `get_current_price(symbol)` | 获取当前价格 | ✅ |
| `get_orderbook(symbol, depth)` | 获取订单簿 | ✅ |
| `place_open_order(request)` | 下开仓单（市价/限价） | ✅ |
| `place_close_order(position, price)` | 平仓 | ✅ |
| `place_stop_loss(...)` | 下止损单 | ✅ |
| `place_take_profit(...)` | 下止盈单 | ✅ |
| `cancel_order(order_id)` | 撤单 | 🔄 (已有接口) |
| `get_active_orders(symbol)` | 获取活跃订单 | 🔄 (已有接口) |
| `get_account_positions()` | 获取持仓 | 🔄 (已有接口) |
| `get_account_balances()` | 获取余额 | 🔄 (已有接口) |

## 注意事项

### 1. 私钥格式
- Lighter私钥必须是66字符（0x + 64 hex）
- 示例: `0x1234567890abcdef...`（共66字符）
- 错误格式会导致SignerClient初始化失败

### 2. Account Index
- Account index是十进制整数
- 通常从1开始（不是0）
- 可在Lighter前端查看

### 3. API Key Index
- API key index通常为0
- 一个账户可以有多个API key（索引0,1,2...）
- 使用Lighter前端生成API key时会显示索引

### 4. 订单簿缓存
- 默认缓存250ms以减少API调用
- 可通过`LIGHTER_ORDERBOOK_CACHE_MS`调整
- 设为0禁用缓存

### 5. 市价单实现
- Lighter的市价单是通过当前最优价格的限价单实现
- 买入使用ask价格，卖出使用bid价格
- 使用`IMMEDIATE_OR_CANCEL`时效性

## 已知限制

1. **cancel_order**: 当前实现使用旧API，需要更新为SignerClient的cancel_order方法
2. **WebSocket**: 尚未实现订单更新和持仓更新的WebSocket监听
3. **批量订单**: 未实现grouped orders功能（OCO等）

## 后续改进

- [ ] 更新cancel_order使用SignerClient
- [ ] 实现WebSocket订单/持仓更新监听
- [ ] 添加批量订单支持（OCO、One-Triggers-Other等）
- [ ] 添加更详细的错误处理和重试逻辑
- [ ] 性能优化：缓存market config避免重复查询

## 参考资料

- [Lighter官网](https://lighter.xyz)
- [Lighter SDK文档](https://github.com/elliottech/lighter-python)
- [Lighter API文档](https://docs.lighter.xyz)

## 版本历史

- **2025-12-29**: 初始实现
  - 实现基础连接和行情查询
  - 实现开仓订单（市价/限价）
  - 实现平仓订单（reduce_only）
  - 实现止损单（市价/限价）
  - 实现止盈单（市价/限价）
  - 创建测试脚本
