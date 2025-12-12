# Paradex WebSocket 使用指南 (V2 Event-Driven)

**版本**: V2 (ExchangeConnectionManager 集成)  
**最后更新**: 2025-12-12

> 注: 本指南针对 V2 Event-Driven 架构进行了更新。Paradex WebSocket 连接现在通过 `ExchangeConnectionManager` 进行统一管理。

## 快速开始

### 1. 环境变量配置

在 `.env` 文件中配置：

```bash
# Paradex L2 凭证
PARADEX_L2_PRIVATE_KEY=0x...  # 你的 L2 私钥
PARADEX_ACCOUNT_ADDRESS=0x...  # 你的 Starknet 账户地址
PARADEX_ENV=testnet  # 或 mainnet
```

### 2. 账户 Onboarding

**重要**: 首次使用需要在 Paradex 完成 onboarding。

#### 方法 A: 通过 Web 界面
1. 访问 https://testnet.paradex.trade/
2. 连接你的钱包
3. 完成 onboarding 流程

#### 方法 B: 通过 API
```python
from paradex_py import ParadexSubkey
from paradex_py.environment import TESTNET

client = ParadexSubkey(
    env=TESTNET,
    l2_private_key="0x...",
    l2_address="0x..."
)

# 调用 onboarding（仅需一次）
client.api_client.onboard()
```

### 3. 运行测试

```bash
source venv/bin/activate
python test_paradex_websocket.py
```

## 使用示例

### 基本用法

```python
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from perpbot.exchanges.paradex import ParadexClient

# 创建客户端
client = ParadexClient(use_testnet=True)
client.connect()

# 设置回调
def on_order(msg):
    print(f"订单: {msg}")

def on_position(msg):
    print(f"持仓: {msg}")

client.setup_order_update_handler(on_order)
client.setup_position_update_handler(on_position)

# ... 运行你的业务逻辑 ...

# 清理
client.disconnect()
```

### 在应用中集成

```python
from perpbot.exchanges.paradex import ParadexClient

class MyTradingBot:
    def __init__(self):
        self.client = ParadexClient(use_testnet=True)
        
    def start(self):
        self.client.connect()
        self.client.setup_order_update_handler(self.handle_order)
        self.client.setup_position_update_handler(self.handle_position)
        
    def handle_order(self, message):
        # 处理订单更新
        order_data = message.get('params', {}).get('data', {})
        print(f"订单状态: {order_data.get('status')}")
        
    def handle_position(self, message):
        # 处理持仓更新
        position_data = message.get('params', {}).get('data', {})
        print(f"持仓: {position_data}")
        
    def stop(self):
        self.client.disconnect()
```

## WebSocket 频道

当前实现订阅以下频道：

- **ORDERS**: 所有市场的订单更新 (`market: "ALL"`)
- **POSITIONS**: 全账户持仓更新

### 可扩展频道

SDK 支持更多频道（可按需添加）:

```python
from paradex_py.api.ws_client import ParadexWebsocketChannel

# 所有可用频道
ParadexWebsocketChannel.ACCOUNT
ParadexWebsocketChannel.BALANCE_EVENTS
ParadexWebsocketChannel.BBO
ParadexWebsocketChannel.FILLS
ParadexWebsocketChannel.FUNDING_DATA
ParadexWebsocketChannel.FUNDING_PAYMENTS
ParadexWebsocketChannel.MARKETS_SUMMARY
ParadexWebsocketChannel.ORDER_BOOK
ParadexWebsocketChannel.TRADES
ParadexWebsocketChannel.TRADEBUSTS
ParadexWebsocketChannel.TRANSACTIONS
ParadexWebsocketChannel.TRANSFERS
```

## 消息格式

### ORDERS 消息示例

```json
{
  "jsonrpc": "2.0",
  "method": "subscription",
  "params": {
    "channel": "ORDERS",
    "data": {
      "id": "order_123",
      "market": "ETH-USD-PERP",
      "side": "BUY",
      "status": "OPEN",
      "size": "0.1",
      "price": "3000.00"
    }
  }
}
```

### POSITIONS 消息示例

```json
{
  "jsonrpc": "2.0",
  "method": "subscription",
  "params": {
    "channel": "POSITIONS",
    "data": {
      "market": "ETH-USD-PERP",
      "size": "0.5",
      "avgEntryPrice": "3000.00",
      "unrealizedPnl": "50.00"
    }
  }
}
```

## 故障排查

### 问题 1: ModuleNotFoundError: No module named 'perpbot'

**解决方案**: 在脚本中添加：
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
```

### 问题 2: NOT_ONBOARDED 错误

**原因**: 账户未完成 Paradex onboarding

**解决方案**:
1. 访问 https://testnet.paradex.trade/
2. 连接钱包并完成 onboarding
3. 或调用 `client.api_client.onboard()`

### 问题 3: WebSocket 连接失败

**检查项**:
- 网络连接是否正常
- 环境变量是否配置正确
- L2 私钥和地址是否匹配

### 问题 4: 没有收到消息

**可能原因**:
- 账户没有活跃订单或持仓
- Handler 未正确设置
- 订阅频道失败

**调试方法**:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## API 参考

### ParadexClient 主要方法

| 方法 | 说明 |
|------|------|
| `connect()` | 连接到 Paradex（自动启动 WebSocket） |
| `disconnect()` | 断开 WebSocket 连接 |
| `setup_order_update_handler(handler)` | 设置订单更新回调 |
| `setup_position_update_handler(handler)` | 设置持仓更新回调 |
| `get_current_price(symbol)` | 获取当前价格 |
| `place_open_order(request)` | 下单 |
| `cancel_order(order_id)` | 取消订单 |
| `get_account_positions()` | 获取持仓 |
| `get_account_balances()` | 获取余额 |

## 技术细节

### 架构

```
主线程 (同步)
    ↓
ParadexClient.connect()
    ↓
后台线程 (daemon)
    ↓
asyncio 事件循环
    ↓
ParadexSubkey.ws_client
    ↓
WebSocket 连接
    ↓
消息推送 → Handler 回调
```

### 线程安全

- WebSocket 运行在独立的 daemon 线程
- Handler 在 asyncio 事件循环线程中执行
- 如果 Handler 需要访问共享状态，请使用线程锁

### 性能建议

1. **Handler 轻量化**: 避免在回调中执行耗时操作
2. **使用队列**: 如果需要复杂处理，将消息放入队列异步处理
3. **错误处理**: Handler 中的异常会被捕获并记录，不影响其他消息

## 更多资源

- **官方文档**: https://tradeparadex.github.io/paradex-py/
- **SDK GitHub**: https://github.com/tradeparadex/paradex-py
- **API 文档**: https://docs.paradex.trade/
- **测试网**: https://testnet.paradex.trade/
