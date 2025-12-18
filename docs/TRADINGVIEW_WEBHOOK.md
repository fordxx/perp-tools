# TradingView Webhook 集成（tv168）

本项目内置 TradingView Alerts Webhook 接口（兼容 `tw168` 的 `ZONE` + `DIV` 语义）。

## ✨ 新功能（v2.3）

- ✅ **OKX 双向持仓（Hedge Mode）支持**：可同时持有多空仓位
- ✅ **自动止损单下单**：成交后立即挂止损单（OKX 条件单）
- ✅ **执行状态机追踪**：place → ack → filled → SL placed
- ✅ **错误分类与日志**：区分凭据/余额/限流/网络等错误类型
- ✅ **UI 可选交易对**：从交易所实时拉取合约列表

## 1) 启动服务

### 方式 A：挂在主系统 Web Console（推荐）

```bash
python3 -m perpbot.cli serve --config config.example.yaml --port 8000
```

### 方式 B：tv168 独立启动

```bash
PYTHONPATH=src .venv/bin/python -m perpbot.integrations.tradingview.standalone --port 8000
```

## 2) 配置环境变量

在 `.env` 里设置（示例见 `.env.example`）：

### 基础配置
- `PERPBOT_TV_WEBHOOK_SECRET=CHANGE_ME`：Webhook 密钥
- `PERPBOT_TV_SYMBOL_ALLOWLIST=ETH-USDT-SWAP`：允许交易的交易对白名单
- `PERPBOT_TV_TRADING_ENABLED=false`：**默认 paper 模式，不下单**
- `PERPBOT_TV_DEFAULT_EXCHANGE=okx`：默认交易所
- `PERPBOT_TV_EXCHANGE_ALLOWLIST=okx,binance,...`（可选）

### 新增：执行模式配置
- `PERPBOT_TV_HEDGE_MODE=true`：**双向持仓模式**（OKX 需开启账户 hedge mode）
- `PERPBOT_TV_PLACE_STOP_LOSS=true`：**自动下止损单**（成交后立即挂条件单）
- `PERPBOT_TV_ORDER_SIZE=1`：默认下单数量（可在 YAML 里按交易所覆盖）

### 可选
- `PERPBOT_TV_CONFIG_PATH=config/tradingview/example.yaml`：YAML profile
- `PERPBOT_TV_ALLOW_ALL_SYMBOLS=true`：允许任意交易对（建议先 paper）

### ⚠️ OKX 双向持仓要求
如果启用 `PERPBOT_TV_HEDGE_MODE=true`，需要在 **OKX 账户设置** 里打开「双向持仓」：
- 登录 OKX → 交易设置 → 仓位模式 → 选择「双向持仓」
- Demo Trading 账户也需要单独设置

## 3) TradingView Alert 消息格式

Webhook URL：`http://YOUR_HOST:8000/webhook/tradingview`

你可以在 payload 里指定交易所（多交易所同服务更方便）：

```json
{"exchange":"binance"}
```

如果你的 TradingView `{{ticker}}` 形如 `SOLUSDT.P`，推荐用 YAML profile 做别名映射（`symbol_aliases`）统一成 `SOL/USDT`。

## Canonical Symbol（推荐）

tv168 内部统一使用 `BASE/QUOTE`（例如 `SOL/USDT`）作为 canonical symbol。

- 不同交易所如果需要特殊 symbol，可以在 YAML 里配置 `symbol_overrides_by_exchange` 覆盖（可选）。

## 自动拉取交易对（Web UI）

Web Console 的 tv168 卡片会在你选择交易所后调用：

- `GET /api/tv168/markets?exchange=...`

对支持的交易所使用公共 REST 拉取合约列表并做缓存（`PERPBOT_TV_MARKETS_CACHE_SEC`）。

ZONE:

```json
{"secret":"CHANGE_ME","type":"ZONE","zone":"OVERSOLD","exchange":"okx","instId":"ETH-USDT-SWAP","tf":"1m","t":"{{time}}","close":"{{close}}"}
```

DIV:

```json
{"secret":"CHANGE_ME","type":"DIV","exchange":"okx","instId":"ETH-USDT-SWAP","tf":"1m","t":"{{time}}","close":"{{close}}"}
```

## 4) 本地快速测试

```bash
bash scripts/test_tradingview_webhook.sh http://127.0.0.1:8000 ETH-USDT-SWAP 1m
```

## 5) 测试流程（渐进式验证）

### Step 1: Paper 模式验证（无需凭据）

```bash
# 启动服务
bash scripts/run_tv168.sh

# 另一个终端运行测试
bash scripts/test_tv168_okx.sh paper
```

预期结果：
- `"paper": true`
- `"order": null`（没有下单）
- `"sl"` 和 `"tp"` 有计算值

### Step 2: OKX Testnet/Demo 验证（需要 API 凭据）

1. **获取 OKX Demo Trading 凭据**：
   - 登录 [OKX](https://www.okx.com) → API 管理 → 创建 API Key
   - ⚠️ **启用 Demo Trading 模式**（项目强制 testnet）

2. **配置 `.env`**：
   ```bash
   OKX_API_KEY=your_demo_key
   OKX_API_SECRET=your_demo_secret
   OKX_PASSPHRASE=your_demo_passphrase
   OKX_ENV=testnet

   PERPBOT_TV_TRADING_ENABLED=true
   PERPBOT_TV_HEDGE_MODE=true
   PERPBOT_TV_PLACE_STOP_LOSS=true
   ```

3. **OKX 账户设置双向持仓**：
   - 登录 OKX Demo Trading → 交易设置 → 仓位模式 → 双向持仓

4. **运行测试**：
   ```bash
   bash scripts/test_tv168_okx.sh testnet
   ```

5. **验证结果**：
   - API 响应：`"paper": false`，`"order"` 有订单 ID
   - OKX Web：持仓页面有 ETH/USDT 多仓
   - OKX Web：委托页面有止损单（条件单）

### Step 3: 小仓位主网试跑（可选，谨慎）

⚠️ **风险警告**：主网涉及真实资金，建议先充分测试 Demo Trading。

```bash
# .env 改为 mainnet（需要主网 API Key）
OKX_ENV=mainnet
PERPBOT_TV_ORDER_SIZE=0.01  # 最小仓位
```

## 6) 响应格式说明

成功执行后的 JSON 响应：

```json
{
  "ok": true,
  "type": "DIV",
  "instId": "ETH-USDT-SWAP",
  "symbol": "ETH/USDT",
  "zone": "OVERSOLD",
  "side": "buy",
  "entry": 3201.0,
  "sl": 3150.0,
  "tp": 3354.0,
  "exchange": "okx",
  "paper": false,
  "order": {
    "id": "123456789",
    "exchange": "okx",
    "symbol": "ETH/USDT",
    "side": "buy",
    "size": 1.0,
    "price": 3201.5
  },
  "stop_loss_order": {
    "id": "987654321",
    "exchange": "okx",
    "symbol": "ETH/USDT",
    "side": "sell",
    "size": 1.0,
    "price": 3150.0
  },
  "execution": {
    "ok": true,
    "status": "filled",
    "entry_price": 3201.5,
    "stop_loss_price": 3150.0,
    "elapsed_ms": 245
  }
}
```

## 7) TradingView 端口限制（80/443）

如果 TradingView 只允许 `http` 80 或 `https` 443：

- 用 Nginx/Caddy 在 80/443 接入
- 反向代理到本服务的 `:8000`

## 8) 故障排查

### 问题：订单被拒绝（`"order": {"id": "rejected-..."}`）

- **原因 1**：缺少 API 凭据 → 检查 `.env` 是否正确配置
- **原因 2**：`PERPBOT_TV_TRADING_ENABLED=false` → 改为 `true`
- **原因 3**：OKX 账户未开启双向持仓 → 去 OKX 设置

### 问题：止损单下单失败

- **原因 1**：`PERPBOT_TV_PLACE_STOP_LOSS=false` → 改为 `true`
- **原因 2**：CCXT 版本不支持 `stop_market` → 升级 `pip install --upgrade ccxt`
- **原因 3**：止损价格不合法（触发价在市价另一侧） → 检查 `sl` 计算逻辑

### 问题：Hedge mode 参数报错

- **OKX 报错 `Invalid posSide`**：账户未开启双向持仓
- **解决方案**：登录 OKX → 交易设置 → 仓位模式 → 选择「双向持仓」
