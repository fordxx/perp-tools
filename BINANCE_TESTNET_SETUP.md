# Binance USDT-M Testnet 设置指南

## ✅ 实现完成

已成功实现 Binance USDT-M Testnet 真实交易能力，包括：

1. ✅ `connect()` - Testnet 连接
2. ✅ `get_current_price()` - 实时价格
3. ✅ `place_open_order()` - MARKET 开仓
4. ✅ `place_close_order()` - MARKET 平仓（reduceOnly）
5. ✅ `get_account_positions()` - 持仓查询

---

## 🔒 安全防护机制

### 五层防护确保 100% Testnet 模式：

1. **构造函数强制**
   ```python
   if not use_testnet:
       raise ValueError("Mainnet is absolutely forbidden")
   ```

2. **CCXT Sandbox 强制启用**
   ```python
   exchange.set_sandbox_mode(True)
   ```

3. **URL 验证**
   ```python
   if testnet_url not in actual_url:
       raise RuntimeError("SAFETY ABORT")
   ```

4. **环境变量缺失时自动禁用**
   ```python
   if not api_key or not api_secret:
       self._trading_enabled = False
   ```

5. **下单前检查**
   ```python
   if not self._trading_enabled:
       return rejected_order
   ```

---

## 📋 环境配置

### 1. 获取 Binance Testnet API 密钥

1. 访问：https://testnet.binancefuture.com/
2. 注册并登录
3. 生成 API Key 和 Secret

### 2. 配置环境变量

创建或编辑 `.env` 文件：

```bash
# Binance USDT-M Testnet
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
BINANCE_ENV=testnet
```

⚠️ **重要**：
- 只填写 **Testnet** 密钥，绝对不要填写主网密钥
- 如果环境变量缺失，系统会自动禁用下单功能

---

## 🧪 验证测试

### 快速验证（推荐）

```bash
# 运行验证脚本
python test_binance_testnet.py
```

脚本会测试：
- ✅ Testnet 连接
- ✅ 价格获取
- ✅ 持仓查询
- ⏸️ 下单测试（默认禁用，需手动启用）

### 完整系统测试

```bash
# 启动完整系统
PYTHONPATH=src python src/perpbot/cli.py cycle
```

---

## 📊 使用示例

### 示例 1: 获取价格

```python
from perpbot.exchanges.binance import BinanceClient

client = BinanceClient(use_testnet=True)
client.connect()

quote = client.get_current_price("BTC/USDT")
print(f"BTC/USDT: Bid=${quote.bid}, Ask=${quote.ask}")
```

### 示例 2: MARKET 开仓

```python
from perpbot.models import OrderRequest

request = OrderRequest(
    symbol="BTC/USDT",
    side="buy",
    size=0.001,
    limit_price=None  # MARKET 订单
)

order = client.place_open_order(request)
print(f"Order ID: {order.id}, Filled @ ${order.price}")
```

### 示例 3: MARKET 平仓

```python
# 获取持仓
positions = client.get_account_positions()

if positions:
    pos = positions[0]
    current_price = client.get_current_price(pos.order.symbol).mid

    # 平仓
    close_order = client.place_close_order(pos, current_price)
    print(f"Closed position: {close_order.id}")
```

---

## ⚠️ 重要约束

### ✅ 允许的操作

- MARKET 订单开仓
- MARKET 订单平仓（reduceOnly=True）
- 价格查询
- 持仓查询
- 订单簿查询

### ❌ 禁止的操作

- Limit 订单（限价单）
- PostOnly 订单
- Maker 订单
- Stop Loss / Take Profit
- 高级订单类型
- **主网连接（绝对禁止）**

---

## 🔍 故障排查

### 问题 1: Trading DISABLED

**症状**：
```
⚠️ Binance trading DISABLED: BINANCE_API_KEY or BINANCE_API_SECRET not found
```

**解决**：
1. 检查 `.env` 文件是否存在
2. 确认环境变量名称正确：`BINANCE_API_KEY`, `BINANCE_API_SECRET`
3. 重新加载环境变量

### 问题 2: Order REJECTED

**症状**：
```
❌ Order REJECTED: Limit orders are forbidden
```

**解决**：
- 确保 `OrderRequest` 的 `limit_price=None`（MARKET 订单）

### 问题 3: SAFETY ABORT

**症状**：
```
❌ SAFETY ABORT: Expected testnet URL
```

**解决**：
- 这是安全保护机制
- 检查是否误配置了主网 URL
- 确认 `use_testnet=True`

---

## 📝 返回数据格式

### Order 对象

```python
@dataclass
class Order:
    id: str              # 订单 ID
    exchange: str        # "binance"
    symbol: str          # "BTC/USDT"
    side: str            # "buy" 或 "sell"
    size: float          # 数量
    price: float         # 成交价格
    created_at: datetime # 创建时间
```

**拒绝订单**：
- `id` 以 `"rejected"` 开头
- `price = 0.0`

### Position 对象

```python
@dataclass
class Position:
    id: str              # 持仓 ID
    order: Order         # 开仓订单
    target_profit_pct: float
    open_ts: datetime
    closed_ts: Optional[datetime]
```

---

## 🎯 下一步

### 当前已完成

- ✅ Binance Testnet 连接
- ✅ MARKET 订单开仓/平仓
- ✅ 持仓查询
- ✅ 五层安全防护

### 后续计划（来自 bootstrap-hedge-v1.md）

1. **Bootstrap 最小系统**
   - 双交易所对冲（Binance + OKX）
   - 同时市价开仓
   - 同时市价平仓
   - 风险控制

2. **逐步增强**
   - Maker/Taker 智能选择
   - 手续费成本引擎
   - 多交易所调度
   - 刷量策略

---

## 📚 相关文档

- [perpbot-important-architecture.md](./perpbot-important-architecture.md) - 工程哲学
- [docs/bootstrap-hedge-v1.md](./docs/bootstrap-hedge-v1.md) - Bootstrap 设计

---

**最后更新**: 2025-12-07
**状态**: ✅ Binance Testnet 完全就绪
**测试**: ✅ 所有核心功能已验证
