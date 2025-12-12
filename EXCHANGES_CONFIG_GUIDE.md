# 📋 交易所配置指南（生产级主网小额测试）

**更新时间**: 2025-12-12  
**测试模式**: 主网 + 小额资金（无 testnet）  
**支持交易所**: 12+ 个 CEX/DEX

---

## 🎯 快速开始

### 查看所有支持的交易所
```bash
python test_exchanges.py --list
```

### 测试所有已配置交易所
```bash
python test_exchanges.py
```

### 测试特定交易所
```bash
python test_exchanges.py okx binance hyperliquid
```

### 自定义交易对
```bash
python test_exchanges.py okx --symbol BTC/USDT
```

### 输出 JSON 报告
```bash
python test_exchanges.py --json-report report.json
```

### 详细日志模式
```bash
python test_exchanges.py --verbose
```

---

## 📚 支持的交易所 (按类型分类)

### 💱 CEX (中心化交易所) - 4 个

#### 1. **OKX** (全球前 3 大 CEX)
```bash
# 配置 .env
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASSPHRASE=your_passphrase

# 获取链接: https://www.okx.com/account/my-api
# 模式: Demo Trading (OKX 强制，无真实风险)
# 支持: USDT 永续合约
python test_exchanges.py okx
```

#### 2. **币安 (Binance)** (全球最大 CEX)
```bash
# 配置 .env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# 获取链接: https://www.binance.com/en/account/api-management
# 模式: 主网 (小额测试)
# 支持: USDT 永续、现货
python test_exchanges.py binance
```

#### 3. **BITGET** (新兴 CEX，流动性好)
```bash
# 配置 .env
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_api_secret
BITGET_PASSPHRASE=your_passphrase

# 获取链接: https://www.bitget.com/en/user/account/api-management
# 模式: 主网 (小额测试)
# 支持: USDT 永续、现货
python test_exchanges.py bitget
```

#### 4. **Bybit** (流动性强)
```bash
# 配置 .env
BYBIT_API_KEY=your_api_key
BYBIT_API_SECRET=your_api_secret
BYBIT_UID=your_uid (可选)

# 获取链接: https://www.bybit.com/en/user/api-management
# 模式: 主网 (小额测试)
# 支持: USDT 永续、反向合约
python test_exchanges.py bybit
```

### 🔗 DEX (去中心化交易所) - 8+ 个

#### 5. **Hyperliquid** (Solana/Sui 上的 DEX)
```bash
# 配置 .env (可选，支持读-only)
HYPERLIQUID_ACCOUNT_ADDRESS=0xyour_address
HYPERLIQUID_PRIVATE_KEY=your_private_key

# 获取链接: https://app.hyperliquid.xyz
# 模式: 主网
# 支持: 永续合约
# 特点: 不需凭证也能查价格，有凭证可交易
python test_exchanges.py hyperliquid
```

#### 6. **Paradex** (Starknet DEX)
```bash
# 配置 .env
PARADEX_L2_PRIVATE_KEY=0xyour_private_key
PARADEX_ACCOUNT_ADDRESS=0xyour_address

# 获取链接: https://app.paradex.trade
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py paradex
```

#### 7. **Extended** (Starknet DEX)
```bash
# 配置 .env
EXTENDED_API_KEY=your_api_key
EXTENDED_STARK_PRIVATE_KEY=0xyour_stark_key
EXTENDED_VAULT_NUMBER=123456

# 获取链接: https://app.extended.exchange/api-management
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py extended
```

#### 8. **Lighter** (Ethereum L2 DEX)
```bash
# 配置 .env
LIGHTER_API_KEY=your_api_key
LIGHTER_PRIVATE_KEY=0xyour_eth_private_key

# 获取链接: https://app.lighter.xyz
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py lighter
```

#### 9. **EdgeX** (多链 DEX)
```bash
# 配置 .env
EDGEX_API_KEY=your_api_key
# EDGEX_API_SECRET=your_secret (可选)

# 获取链接: https://app.edgex.exchange
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py edgex
```

#### 10. **Backpack** (Solana DEX)
```bash
# 配置 .env
BACKPACK_API_KEY=your_api_key
BACKPACK_API_SECRET=your_api_secret

# 获取链接: https://backpack.exchange
# 模式: 主网
# 支持: 现货、期权
python test_exchanges.py backpack
```

#### 11. **GRVT** (Ethereum L2 DEX)
```bash
# 配置 .env
GRVT_API_KEY=your_api_key

# 获取链接: https://app.grvt.io
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py grvt
```

#### 12. **Aster** (Solana DEX)
```bash
# 配置 .env
ASTER_API_KEY=your_api_key

# 获取链接: https://app.aster.com
# 模式: 主网
# 支持: 永续合约
python test_exchanges.py aster
```

---

## ⚙️ .env 配置完整示例

```bash
# ===== OKX (CEX) =====
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase

# ===== 币安 (CEX) =====
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret

# ===== BITGET (CEX) =====
BITGET_API_KEY=your_bitget_api_key
BITGET_API_SECRET=your_bitget_api_secret
BITGET_PASSPHRASE=your_bitget_passphrase

# ===== Bybit (CEX) =====
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret

# ===== Hyperliquid (DEX, 可选凭证) =====
# HYPERLIQUID_ACCOUNT_ADDRESS=0xyour_address
# HYPERLIQUID_PRIVATE_KEY=your_private_key

# ===== Paradex (DEX) =====
PARADEX_L2_PRIVATE_KEY=0xyour_private_key
PARADEX_ACCOUNT_ADDRESS=0xyour_address

# ===== Extended (DEX) =====
EXTENDED_API_KEY=your_extended_api_key
EXTENDED_STARK_PRIVATE_KEY=0xyour_stark_key
EXTENDED_VAULT_NUMBER=123456

# ===== Lighter (DEX) =====
LIGHTER_API_KEY=your_lighter_api_key
LIGHTER_PRIVATE_KEY=0xyour_eth_private_key

# ===== EdgeX (DEX) =====
EDGEX_API_KEY=your_edgex_api_key

# ===== Backpack (DEX) =====
BACKPACK_API_KEY=your_backpack_api_key
BACKPACK_API_SECRET=your_backpack_api_secret

# ===== GRVT (DEX) =====
GRVT_API_KEY=your_grvt_api_key

# ===== Aster (DEX) =====
ASTER_API_KEY=your_aster_api_key
```

---

## 🧪 测试场景

### 场景 1: 快速验证（只读）
```bash
# 验证连接，不需要交易权限
python test_exchanges.py okx hyperliquid --verbose
```

### 场景 2: 完整测试（所有已配置）
```bash
# 测试所有已配置的交易所
python test_exchanges.py
```

### 场景 3: 批量测试 + 报告
```bash
# 输出详细 JSON 报告
python test_exchanges.py --json-report exchange_report.json
```

### 场景 4: 特定交易对测试
```bash
# 测试 ETH/USDT 而不是 BTC/USDT
python test_exchanges.py okx binance --symbol ETH/USDT
```

---

## 📊 测试覆盖内容

每个交易所的测试包括：

| 测试项 | 说明 | 必需凭证 |
|--------|------|---------|
| ✅ 连接 | 验证 API 连接 | 是 |
| ✅ 价格 | 获取 Bid/Ask 价格 | 否 |
| ✅ 订单簿 | 获取深度订单簿 | 否 |
| ✅ 账户余额 | 查询账户余额 | 是 |
| ✅ 持仓 | 查询开放持仓 | 是 |
| ⚠️ 交易 | 小额开单/平仓 | 是 + `--trading` |

---

## ⚠️ 安全指南

### 主网测试最佳实践

1. **使用只读 API Key**
   - 大多数交易所支持只读权限
   - 推荐测试时只开启读权限

2. **小额资金**
   - 推荐每笔不超过 5-10 USDT
   - 避免在交易量低的交易对上测试

3. **IP 白名单**
   - 为 API Key 配置 IP 白名单
   - 限制使用范围

4. **定期更换**
   - 每月更换一次 API Key
   - 定期审计使用记录

5. **禁止在代码中硬编码**
   - 始终使用 `.env` 文件
   - 确保 `.env` 在 `.gitignore` 中

---

## 🐛 故障排查

### 问题 1: "ModuleNotFoundError"
```bash
# 解决: 检查虚拈环境和依赖
source venv_okx/bin/activate
pip install okx python-dotenv httpx
deactivate
```

### 问题 2: "Connection refused"
```bash
# 解决: 检查网络和代理
# 某些地区需要代理访问交易所
```

### 问题 3: "Invalid API Key"
```bash
# 解决: 验证 .env 配置
cat .env | grep -E "OKX_|BINANCE_"
```

### 问题 4: "Rate limit exceeded"
```bash
# 解决: 等待后重试，减少测试频率
python test_exchanges.py okx --verbose
```

---

## 🎯 长期计划

### 支持的交易所数量

```
当前: 12+ 个 (4 CEX + 8+ DEX)
Q1 2026: 15+ 个 (添加 Dydx、Gate.io、Huobi)
Q2 2026: 20+ 个 (继续扩展)
```

### 扩展流程

要添加新交易所：

1. **实现客户端**
   ```python
   # src/perpbot/exchanges/new_exchange.py
   class NewExchangeClient(ExchangeClient):
       def __init__(self, use_testnet=False):
           ...
   ```

2. **添加到目录**
   ```python
   # test_exchanges.py EXCHANGE_CONFIGS
   "new_exchange": ExchangeConfig(
       name="new_exchange",
       class_name="NewExchangeClient",
       module_name="perpbot.exchanges.new_exchange",
       required_env=["NEW_EXCHANGE_API_KEY"],
   )
   ```

3. **配置 .env**
   ```bash
   NEW_EXCHANGE_API_KEY=your_key
   ```

4. **运行测试**
   ```bash
   python test_exchanges.py new_exchange
   ```

---

## 📝 日志示例

```
🚀 Starting tests for 3 exchange(s)...

============================================================
Testing OKX
============================================================
1️⃣ Testing connection...
   ✅ Connected (45ms)
2️⃣ Testing price (BTC/USDT)...
   ✅ Price: 99000.50-99001.50 (120ms)
3️⃣ Testing orderbook (BTC/USDT)...
   ✅ Orderbook: 5 bids, 5 asks (95ms)
4️⃣ Testing account balances...
   ✅ Found 3 balances (180ms)
5️⃣ Testing positions...
   ✅ Found 2 positions (150ms)
✅ OKX test completed

...

======================================================================
📊 TEST SUMMARY
======================================================================
Total: 3 exchanges
✅ Passed: 3
❌ Failed: 0
⏱️  Duration: 2.3s

Exchange        Connection  Price       Orderbook   Balance     Error
---
okx             ✅          ✅          ✅          ✅          
binance         ✅          ✅          ✅          ✅          
hyperliquid     ✅          ✅          ✅          ✅          
```

---

## 🔗 有用链接

- [test_exchanges.py](test_exchanges.py) - 统一测试框架
- [src/perpbot/exchanges/](src/perpbot/exchanges/) - 所有交易所实现
- [.env.example](.env.example) - 配置模板

---

## 💡 使用建议

1. **开发阶段**: 用少数 2-3 个主要交易所测试
2. **集成阶段**: 扩展到 5-8 个交易所
3. **生产阶段**: 支持 10+ 个交易所
4. **监控阶段**: 定期运行完整测试集

---

**建议开始**: `python test_exchanges.py --list` 查看所有支持的交易所！
