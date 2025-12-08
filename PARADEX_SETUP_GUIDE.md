# Paradex DEX 交易功能 - 完整使用指南

## 📋 目录
1. [简介](#简介)
2. [功能列表](#功能列表)
3. [环境准备](#环境准备)
4. [API 凭证配置](#api-凭证配置)
5. [安装依赖](#安装依赖)
6. [快速开始](#快速开始)
7. [功能详解](#功能详解)
8. [测试指南](#测试指南)
9. [常见问题](#常见问题)
10. [风险提示](#风险提示)

---

## 简介

Paradex 是基于 Starknet 的去中心化衍生品交易所。本客户端提供完整的交易功能，支持主网和测试网。

**特点：**
- ✅ 支持 LIMIT 和 MARKET 订单
- ✅ 完整的订单管理（下单、撤单、查询）
- ✅ 实时持仓查询
- ✅ 余额查询
- ✅ 主网和测试网支持
- ✅ JWT 认证集成

---

## 功能列表

| 功能 | 状态 | 说明 |
|------|------|------|
| 连接认证 | ✅ | JWT token 认证 |
| 查询价格 | ✅ | 获取实时 bid/ask |
| 查询订单簿 | ✅ | 深度行情 |
| 下限价单 | ✅ | LIMIT order |
| 下市价单 | ✅ | MARKET order |
| 撤单 | ✅ | 取消订单 |
| 查询活跃订单 | ✅ | 所有未成交订单 |
| 查询持仓 | ✅ | 当前持仓 |
| 查询余额 | ✅ | USDC 余额 |
| WebSocket | ⏸️ | 待实现 |

---

## 环境准备

### 系统要求
- Python 3.10+
- 网络连接（访问 Paradex API）

### 支持的操作系统
- ✅ Linux
- ✅ macOS
- ✅ Windows

---

## API 凭证配置

### 1. 获取 Paradex API 凭证

#### 方法 A: 通过 Paradex 官网
1. 访问 [Paradex 官网](https://app.paradex.trade/)
2. 连接你的 Starknet 钱包（如 Argent X, Braavos）
3. 进入 **Account Settings** > **API Keys**
4. 点击 **Create New API Key**
5. 保存以下信息：
   - API Key
   - API Secret
   - Account Address（你的 Starknet 钱包地址）

#### 方法 B: 使用测试网
测试网配置与主网相同，只需访问测试网网站：
- Testnet: https://testnet.paradex.trade/

### 2. 创建 `.env` 文件

在项目根目录创建 `.env` 文件：

```bash
# Paradex 主网配置
PARADEX_API_KEY=your_api_key_here
PARADEX_API_SECRET=your_api_secret_here
PARADEX_ACCOUNT_ADDRESS=0xYourStarknetAddress
PARADEX_ENV=mainnet

# 可选: STARK 私钥（用于订单签名）
PARADEX_STARK_PRIVATE_KEY=your_stark_private_key

# 如果使用测试网，改为:
# PARADEX_ENV=testnet
```

**⚠️ 安全提示：**
- ❌ 不要提交 `.env` 文件到 Git
- ❌ 不要分享你的 API Secret
- ✅ 确保 `.env` 已加入 `.gitignore`

---

## 安装依赖

### 方法 1: 使用 requirements.txt（推荐）

```bash
pip install -r requirements.txt
```

### 方法 2: 手动安装

```bash
# 必需的库
pip install httpx python-dotenv

# 可选：STARK 签名支持（未来）
# pip install starknet-py
```

### 验证安装

```bash
python -c "import httpx; print('✅ httpx 已安装')"
python -c "from dotenv import load_dotenv; print('✅ python-dotenv 已安装')"
```

---

## 快速开始

### 1. 运行测试脚本

```bash
python test_paradex.py
```

### 2. 选择环境

```
选择环境 (1=Mainnet, 2=Testnet): 2
```

**建议：** 先在测试网测试（选择 2）

### 3. 测试流程

脚本会自动执行以下测试：
1. ✅ 连接 Paradex
2. ✅ 查询 BTC/USDT 价格
3. ✅ 查询订单簿
4. ✅ 查询余额
5. ✅ 查询持仓
6. ✅ 查询活跃订单
7. ⚠️  下限价单（需用户确认）
8. ⚠️  下市价单（需用户确认）
9. ⚠️  撤单（需用户确认）

### 4. 输出示例

```
✅ Paradex 连接成功！
   - 交易模式: Testnet
   - 交易启用: True

✅ 价格查询成功！
   - 买价 (Bid): $94,550.00
   - 卖价 (Ask): $94,560.00
   - 中间价: $94,555.00
   - 价差: $10.00 (0.01%)

✅ 订单簿查询成功！

📈 卖单（Ask）：
   $94,580.00  |  0.5000
   $94,570.00  |  1.2000
   ...

💰 USDC:
   - 可用: 1000.0000
   - 冻结: 50.0000
   - 总计: 1050.0000
```

---

## 功能详解

### 1. 连接和认证

```python
from perpbot.exchanges.paradex import ParadexClient

# 创建客户端
client = ParadexClient(use_testnet=True)  # True=测试网, False=主网

# 连接
client.connect()
```

**认证流程：**
1. 读取 `.env` 配置
2. 使用 HMAC-SHA256 签名
3. 获取 JWT token
4. 自动在后续请求中使用 JWT

### 2. 查询价格

```python
from perpbot.exchanges.paradex import ParadexClient

client = ParadexClient(use_testnet=True)
client.connect()

# 查询 BTC/USDT 价格
price = client.get_current_price("BTC/USDT")

print(f"买价: ${price.bid:,.2f}")
print(f"卖价: ${price.ask:,.2f}")
print(f"中间价: ${price.mid:,.2f}")
print(f"价差: {price.spread_pct:.2f}%")
```

**支持的交易对：**
- BTC/USDT → 自动转换为 BTC-USD-PERP
- ETH/USDT → 自动转换为 ETH-USD-PERP
- 其他 Paradex 支持的交易对

### 3. 查询订单簿

```python
# 查询订单簿（深度 20）
book = client.get_orderbook("BTC/USDT", depth=20)

# 打印买单
for price, size in book.bids[:5]:
    print(f"买: ${price:,.2f} | {size:.4f}")

# 打印卖单
for price, size in book.asks[:5]:
    print(f"卖: ${price:,.2f} | {size:.4f}")
```

### 4. 下限价单（LIMIT Order）

```python
from perpbot.models import OrderRequest

# 创建限价单请求
request = OrderRequest(
    symbol="BTC/USDT",
    side="buy",  # "buy" 或 "sell"
    size=0.001,  # 数量
    limit_price=90000.0,  # 限价
)

# 下单
order = client.place_open_order(request)

print(f"订单ID: {order.id}")
print(f"成交价: ${order.price:,.2f}")
```

**限价单特点：**
- ✅ 可以设置精确价格
- ✅ 不会立即成交（除非价格达到）
- ✅ 可以随时撤单

### 5. 下市价单（MARKET Order）

```python
from perpbot.models import OrderRequest

# 创建市价单请求
request = OrderRequest(
    symbol="BTC/USDT",
    side="buy",
    size=0.001,
    limit_price=None,  # 市价单不需要价格
)

# 下单
order = client.place_open_order(request)

print(f"订单ID: {order.id}")
print(f"成交价: ${order.price:,.2f}")
```

**⚠️ 市价单注意事项：**
- ⚠️  会立即成交
- ⚠️  成交价格不确定（取决于订单簿）
- ⚠️  可能产生滑点
- ✅ 适合需要快速成交的场景

### 6. 撤单

```python
# 撤销订单
client.cancel_order(order_id="1234567890")

print("✅ 撤单成功")
```

### 7. 查询活跃订单

```python
# 查询所有活跃订单
orders = client.get_active_orders()

for order in orders:
    print(f"订单ID: {order.id}")
    print(f"交易对: {order.symbol}")
    print(f"方向: {order.side}")
    print(f"数量: {order.size:.4f}")
    print(f"价格: ${order.price:,.2f}")

# 查询特定交易对的订单
btc_orders = client.get_active_orders(symbol="BTC/USDT")
```

### 8. 查询持仓

```python
# 查询所有持仓
positions = client.get_account_positions()

for pos in positions:
    print(f"交易对: {pos.order.symbol}")
    print(f"方向: {pos.order.side}")
    print(f"数量: {pos.order.size:.4f}")
    print(f"开仓价: ${pos.order.price:,.2f}")
```

### 9. 查询余额

```python
# 查询账户余额
balances = client.get_account_balances()

for balance in balances:
    print(f"{balance.asset}:")
    print(f"  可用: {balance.free:,.4f}")
    print(f"  冻结: {balance.locked:,.4f}")
    print(f"  总计: {balance.total:,.4f}")
```

### 10. 平仓

```python
# 平仓（假设你有一个持仓）
positions = client.get_account_positions()

if positions:
    pos = positions[0]
    current_price = client.get_current_price(pos.order.symbol).mid

    # 平仓（市价单）
    close_order = client.place_close_order(pos, current_price)
    print(f"✅ 平仓订单ID: {close_order.id}")
```

---

## 测试指南

### 测试环境选择

#### Testnet（推荐新手）
- ✅ 无真实资金风险
- ✅ 可以大胆测试
- ✅ API 行为与主网一致
- ❌ 需要测试网 USDC

#### Mainnet（生产环境）
- ⚠️  使用真实资金
- ⚠️  交易会产生费用
- ✅ 真实市场行情
- ✅ 真实流动性

### 测试步骤

#### 1. 只读测试（无风险）

```bash
# 修改 .env
PARADEX_ENV=testnet

# 运行测试（只执行查询功能）
python test_paradex.py
```

当询问是否继续下单测试时，选择 **no**。

#### 2. 小额下单测试

```bash
# 确保 .env 配置正确
# 运行完整测试
python test_paradex.py
```

当询问是否继续下单测试时，选择 **yes**。

**建议测试参数：**
- 交易对: BTC/USDT
- 数量: 0.001 BTC（约 $100）
- 订单类型: 先测 LIMIT，再测 MARKET

#### 3. 生产环境测试

```bash
# 修改 .env
PARADEX_ENV=mainnet

# ⚠️  小心！这会使用真实资金
python test_paradex.py
```

**主网测试建议：**
- 从非常小的金额开始（10-20 USDC）
- 先用限价单（不会立即成交）
- 确认一切正常后再用市价单
- 随时准备撤单

---

## 常见问题

### Q1: 认证失败怎么办？

**错误：** `❌ Paradex authentication failed`

**解决方法：**
1. 检查 `.env` 文件中的 API Key 和 Secret 是否正确
2. 确认 API Key 没有过期
3. 检查网络连接
4. 尝试重新生成 API Key

### Q2: 下单失败怎么办？

**错误：** `❌ Order REJECTED`

**可能原因：**
1. **余额不足** - 检查账户余额
2. **数量太小** - Paradex 有最小下单量限制
3. **价格异常** - 限价单价格偏离市场太远
4. **交易对不存在** - 检查交易对名称

**解决方法：**
```python
# 查询余额
balances = client.get_account_balances()

# 查询当前价格
price = client.get_current_price("BTC/USDT")

# 使用合理的价格和数量
request = OrderRequest(
    symbol="BTC/USDT",
    side="buy",
    size=0.01,  # 增加数量
    limit_price=price.bid * 0.99,  # 使用市场价附近的价格
)
```

### Q3: 查询持仓为空？

**问题：** `ℹ️  当前没有持仓`

**可能原因：**
1. 确实没有持仓
2. API Key 权限不足
3. 连接到了错误的环境（testnet vs mainnet）

**解决方法：**
- 检查 `.env` 中的 `PARADEX_ENV` 设置
- 确认在正确的环境下查询
- 先下单建仓，再查询持仓

### Q4: 价格查询失败？

**错误：** `❌ Paradex price fetch failed`

**可能原因：**
1. 交易对名称错误
2. 网络连接问题
3. API 限流

**解决方法：**
```python
# 使用正确的交易对名称
# ✅ 正确
price = client.get_current_price("BTC/USDT")

# ❌ 错误
# price = client.get_current_price("BTCUSDT")  # 格式错误
# price = client.get_current_price("BTC-USD-PERP")  # 不需要手动转换
```

### Q5: STARK 签名问题？

**警告：** `⚠️ STARK signing not implemented`

**说明：**
- 当前版本不需要 STARK 签名
- Paradex API 使用 JWT 认证
- 未来版本可能添加 STARK 签名支持

**如需 STARK 签名：**
```bash
# 安装 starknet.py
pip install starknet-py

# 在 .env 中配置
PARADEX_STARK_PRIVATE_KEY=your_stark_private_key
```

### Q6: 如何获取测试网 USDC？

**步骤：**
1. 在测试网部署 Starknet 钱包（Argent X 或 Braavos）
2. 访问 Starknet 测试网水龙头获取 ETH
3. 在 Paradex 测试网申请测试 USDC
4. 或使用 Starknet 测试网的 USDC 水龙头

---

## 风险提示

### ⚠️ 重要风险提示

1. **资金风险**
   - 加密货币交易存在高风险
   - 可能损失全部投入资金
   - 仅使用你能承受损失的资金

2. **技术风险**
   - 代码可能存在 bug
   - API 可能不稳定
   - 网络可能中断

3. **市场风险**
   - 价格波动剧烈
   - 滑点可能很大
   - 流动性可能不足

4. **操作风险**
   - 市价单会立即成交
   - 撤单可能不及时
   - 订单可能部分成交

### ✅ 安全建议

1. **从小额开始**
   - 先在测试网测试
   - 主网从 10-20 USDC 开始
   - 逐步增加金额

2. **设置止损**
   - 设定最大亏损额度
   - 及时止损离场
   - 不要追涨杀跌

3. **保护 API 凭证**
   - 不要分享 API Secret
   - 定期更换 API Key
   - 限制 API Key 权限

4. **监控交易**
   - 定期检查持仓
   - 关注账户余额
   - 及时处理异常订单

---

## 高级用法

### 自动化交易

```python
import time
from perpbot.exchanges.paradex import ParadexClient
from perpbot.models import OrderRequest

def auto_trade():
    """简单的自动化交易示例"""
    client = ParadexClient(use_testnet=True)
    client.connect()

    while True:
        try:
            # 查询价格
            price = client.get_current_price("BTC/USDT")

            # 简单策略：价格低于 95000 买入
            if price.bid < 95000:
                request = OrderRequest(
                    symbol="BTC/USDT",
                    side="buy",
                    size=0.001,
                    limit_price=price.bid,
                )
                order = client.place_open_order(request)
                print(f"✅ 买入订单: {order.id}")

            # 等待 10 秒
            time.sleep(10)

        except KeyboardInterrupt:
            print("停止交易")
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(10)

# 运行（仅供演示，请根据实际需求修改策略）
auto_trade()
```

### 批量操作

```python
# 批量下单
symbols = ["BTC/USDT", "ETH/USDT"]
orders = []

for symbol in symbols:
    price = client.get_current_price(symbol)
    request = OrderRequest(
        symbol=symbol,
        side="buy",
        size=0.001,
        limit_price=price.bid * 0.99,
    )
    order = client.place_open_order(request)
    orders.append(order)

# 批量撤单
for order in orders:
    if not order.id.startswith("rejected"):
        client.cancel_order(order.id)
```

---

## 总结

### ✅ 你现在可以：
1. 连接 Paradex DEX
2. 查询实时价格和订单簿
3. 下限价单和市价单
4. 管理活跃订单（撤单、查询）
5. 查询持仓和余额
6. 在测试网安全测试
7. 在主网真实交易

### 📚 推荐学习资源：
- [Paradex 官方文档](https://docs.paradex.trade/)
- [Starknet 开发文档](https://docs.starknet.io/)
- [加密货币交易基础](https://www.binance.com/zh-CN/academy)

### 🆘 需要帮助？
- GitHub Issues: https://github.com/your-repo/issues
- Paradex Discord: https://discord.gg/paradex
- Starknet Discord: https://discord.gg/starknet

---

**祝你交易顺利！💰**
