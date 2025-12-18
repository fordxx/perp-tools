# SOL/USDT OKX Demo Trading 快速开始

## 🎯 目标

在 OKX Demo Trading 环境下测试 SOL/USDT 双向持仓 + 止损单自动下单。

---

## ⚡ 快速配置（5 分钟）

### Step 1: 获取 OKX Demo Trading API 凭据

1. 访问 [OKX官网](https://www.okx.com)
2. 登录 → 右上角头像 → **API**
3. 点击「**创建 API**」
4. 选择「**Demo Trading**」模式 ⚠️
5. 设置权限：
   - ✅ 读取
   - ✅ 交易
   - ✅ 合约交易
6. 记录下：
   - API Key
   - API Secret
   - Passphrase

### Step 2: 配置 .env 文件

```bash
# 方式 A：从模板创建
cp .env.sol_demo_template .env

# 方式 B：直接编辑（如果已有 .env）
vim .env
```

**必填配置**：

```bash
# OKX Demo Trading 凭据
OKX_API_KEY=<你的 API Key>
OKX_API_SECRET=<你的 API Secret>
OKX_PASSPHRASE=<你的 Passphrase>
OKX_ENV=testnet

# 启用实盘下单
PERPBOT_TV_TRADING_ENABLED=true

# 允许所有交易对
PERPBOT_TV_ALLOW_ALL_SYMBOLS=true

# SOL 数量（0.1 SOL ≈ 20 USDT）
PERPBOT_TV_ORDER_SIZE=0.1

# 双向持仓 + 止损单
PERPBOT_TV_HEDGE_MODE=true
PERPBOT_TV_PLACE_STOP_LOSS=true
```

### Step 3: OKX 账户设置双向持仓

⚠️ **重要**：OKX Demo Trading 账户需要单独设置！

1. 登录 [OKX Demo Trading](https://www.okx.com/demo-trading)
2. 右上角 → 交易设置 → **仓位模式**
3. 选择「**双向持仓**」
4. 确认切换

### Step 4: 运行测试

```bash
# 一键测试 SOL/USDT
bash scripts/test_sol_demo.sh
```

---

## 📊 预期结果

### 成功响应示例

```json
{
  "ok": true,
  "paper": false,
  "symbol": "SOL/USDT",
  "side": "buy",
  "entry": 196.5,
  "sl": 189.2,
  "tp": 217.9,
  "order": {
    "id": "123456789",
    "exchange": "okx",
    "price": 196.52,
    "size": 0.1
  },
  "stop_loss_order": {
    "id": "987654321",
    "side": "sell",
    "price": 189.2
  },
  "execution": {
    "ok": true,
    "status": "filled",
    "elapsed_ms": 342
  }
}
```

### OKX Web 验证

登录 [OKX Demo Trading](https://www.okx.com/demo-trading) 查看：

1. **持仓页面**：
   - ✅ 应该有 SOL/USDT 多仓（0.1 SOL）
   - ✅ 持仓模式显示「双向持仓」

2. **委托页面**：
   - ✅ 应该有止损条件单（Sell Stop）
   - ✅ 触发价格 ≈ 189.2 USDT

---

## 🔧 配置调整

### 调整 SOL 下单数量

```bash
# .env 文件
PERPBOT_TV_ORDER_SIZE=0.2    # 改为 0.2 SOL
```

### 调整止损/止盈参数

```bash
# 更激进的止损（较近）
PERPBOT_TV_STOP_LOOKBACK_BARS=20

# 更保守的止损（较远）
PERPBOT_TV_STOP_LOOKBACK_BARS=100

# 调整盈亏比
PERPBOT_TV_TP_RR=2.0    # 2:1 (更保守)
PERPBOT_TV_TP_RR=5.0    # 5:1 (更激进)
```

### 只做多或只做空

```bash
# 只做多
PERPBOT_TV_ENABLE_LONG=true
PERPBOT_TV_ENABLE_SHORT=false

# 只做空
PERPBOT_TV_ENABLE_LONG=false
PERPBOT_TV_ENABLE_SHORT=true
```

---

## 🚨 故障排查

### 问题 1：订单被拒绝 `"order": {"id": "rejected"}`

**原因**：
- API 凭据错误
- `PERPBOT_TV_TRADING_ENABLED=false`（paper 模式）

**解决**：
```bash
# 检查 .env
grep OKX_API_KEY .env
grep PERPBOT_TV_TRADING_ENABLED .env

# 应该显示：
# PERPBOT_TV_TRADING_ENABLED=true
```

### 问题 2：`Invalid posSide` 错误

**原因**：OKX 账户未开启双向持仓

**解决**：
1. 登录 OKX Demo Trading
2. 交易设置 → 仓位模式 → **双向持仓**

### 问题 3：止损单未下单

**原因**：
- `PERPBOT_TV_PLACE_STOP_LOSS=false`
- CCXT 版本不支持 stop_market

**解决**：
```bash
# 检查配置
grep PERPBOT_TV_PLACE_STOP_LOSS .env

# 升级 CCXT
source .venv/bin/activate
pip install --upgrade ccxt
```

### 问题 4：Symbol not allowed

**原因**：SOL 不在白名单

**解决**：
```bash
# 方式 A：允许所有交易对
PERPBOT_TV_ALLOW_ALL_SYMBOLS=true

# 方式 B：添加到白名单
PERPBOT_TV_SYMBOL_ALLOWLIST=SOL/USDT,ETH/USDT,BTC/USDT
```

---

## 📝 手动测试流程

如果自动脚本失败，可以手动测试：

### 1. 启动服务

```bash
bash scripts/run_tv168.sh
```

### 2. 发送 ZONE 信号

```bash
curl -X POST http://127.0.0.1:8001/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "CHANGE_ME",
    "type": "ZONE",
    "zone": "OVERSOLD",
    "exchange": "okx",
    "instId": "SOL/USDT",
    "tf": "5m",
    "t": "2025-12-16T08:00:00Z",
    "close": "195.50"
  }'
```

### 3. 发送 DIV 信号（触发下单）

```bash
curl -X POST http://127.0.0.1:8001/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "CHANGE_ME",
    "type": "DIV",
    "exchange": "okx",
    "instId": "SOL/USDT",
    "tf": "5m",
    "t": "2025-12-16T08:00:05Z",
    "close": "196.00"
  }' | python3 -m json.tool
```

---

## ⚠️ 注意事项

1. **Demo Trading ≠ Testnet**
   - OKX Demo Trading 使用真实市场数据
   - 但资金是虚拟的，不会影响真实账户

2. **Mainnet 警告**
   - 如需切换到真实资金，需要：
     ```bash
     OKX_ENV=mainnet
     # 并使用 Mainnet API Key
     ```
   - ⚠️ 建议先在 Demo Trading 充分测试

3. **双向持仓限制**
   - 必须在 OKX 账户设置中启用
   - Demo Trading 和 Mainnet 需要分别设置

---

## 🎓 下一步

测试成功后，可以：

1. **接入 TradingView**：
   - 在 TradingView 创建 Alert
   - Webhook URL: `http://your-server:8001/webhook/tradingview`
   - 使用相同的 JSON 格式

2. **测试其他交易对**：
   ```bash
   # BTC/USDT
   curl -X POST ... -d '{"instId": "BTC/USDT", ...}'

   # ETH/USDT
   curl -X POST ... -d '{"instId": "ETH/USDT", ...}'
   ```

3. **调整风控参数**：
   - 止损距离
   - 盈亏比
   - 下单数量

---

需要帮助？查看 [docs/TRADINGVIEW_WEBHOOK.md](TRADINGVIEW_WEBHOOK.md) 完整文档。
