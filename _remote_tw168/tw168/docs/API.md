# TW168 API 文档

本文档描述 TW168 系统的所有 HTTP API 端点。

## 📋 目录

- [基础信息](#基础信息)
- [认证](#认证)
- [端点列表](#端点列表)
- [Webhook 端点](#webhook-端点)
- [查询端点](#查询端点)
- [错误处理](#错误处理)
- [示例代码](#示例代码)

## 基础信息

### Base URL
```
http://your-server:8000
```

### 请求格式
- Content-Type: `application/json`
- Charset: UTF-8

### 响应格式
所有响应均为 JSON 格式。

## 认证

### Webhook 认证
Webhook 端点使用 `secret` 字段进行认证：

```json
{
  "secret": "your_webhook_secret"
}
```

配置在 `.env` 文件中：
```bash
TV_WEBHOOK_SECRET=your_webhook_secret
```

## 端点列表

### 系统端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/` | 欢迎信息 |
| GET | `/status` | 系统状态 (需要认证) |

### Webhook 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/webhook/tradingview` | TradingView 信号接收 |

### 查询端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/candles/{symbol}` | 查询缓存的 K 线数据 |
| GET | `/trades` | 查询活跃的交易计划 |

---

## Webhook 端点

### POST /webhook/tradingview

接收来自 TradingView 的交易信号。

#### 请求格式

**ZONE 信号** (设置市场状态)

```json
{
  "secret": "your_webhook_secret",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m",
  "t": "2025-01-01 12:00:00",
  "close": "3500.50"
}
```

**参数说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| secret | string | ✅ | Webhook 密钥 |
| type | string | ✅ | 信号类型，固定为 "ZONE" |
| zone | string | ✅ | 市场状态: "OVERSOLD", "OVERBOUGHT", "NEUTRAL" |
| instId | string | ✅ | 交易对，如 "ETH-USDT-SWAP" |
| tf | string | ✅ | 时间周期，如 "1m", "15m", "1h" |
| t | string | ❌ | 时间戳 (可选) |
| close | string | ❌ | 收盘价 (可选) |

**DIV 信号** (触发交易)

```json
{
  "secret": "your_webhook_secret",
  "type": "DIV",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m",
  "t": "2025-01-01 12:01:00",
  "close": "3501.20"
}
```

**参数说明:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| secret | string | ✅ | Webhook 密钥 |
| type | string | ✅ | 信号类型，固定为 "DIV" |
| instId | string | ✅ | 交易对 |
| tf | string | ✅ | 时间周期 |
| side | string | ❌ | 强制方向: "buy" 或 "sell" (跳过 ZONE 检查) |
| t | string | ❌ | 时间戳 |
| close | string | ❌ | 收盘价 |

#### 成功响应

**200 OK** - ZONE 信号

```json
{
  "ok": true,
  "message": "zone_updated",
  "zone": "OVERSOLD",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m"
}
```

**200 OK** - DIV 信号 (Paper Trade)

```json
{
  "ok": true,
  "paper": true,
  "instId": "ETH-USDT-SWAP",
  "side": "buy",
  "posSide": "long",
  "entry": 3501.20,
  "sl": 3425.15,
  "tp1": 3615.35,
  "tp2": 3653.30,
  "tp3": 3691.25,
  "tp4": 3767.15,
  "r_value": 76.05,
  "size": "0.5"
}
```

**200 OK** - DIV 信号 (实盘交易)

```json
{
  "ok": true,
  "instId": "ETH-USDT-SWAP",
  "side": "buy",
  "posSide": "long",
  "orderId": "123456789",
  "clOrdId": "tv1735732860123b",
  "entry": 3501.20,
  "sl": 3425.15,
  "tp1": 3615.35,
  "tp2": 3653.30,
  "tp3": 3691.25,
  "tp4": 3767.15,
  "r_value": 76.05,
  "size": "0.5",
  "trade_plan_registered": true
}
```

#### 跳过响应

**200 OK** - 信号被跳过

```json
{
  "ok": true,
  "skipped": "cooldown",
  "reason": "cooldown_active_for_95_seconds"
}
```

**跳过原因:**

| skipped 值 | 说明 |
|-----------|------|
| `cooldown` | 冷却时间未到 |
| `duplicate` | 重复信号 (已去重) |
| `zone_expired_or_neutral` | ZONE 过期或为 NEUTRAL |
| `pattern_filter` | 形态过滤不通过 |
| `rsi_filter` | RSI 过滤不通过 |
| `direction_disabled` | 方向被禁用 |
| `invalid_stop_loss` | 止损价格无效 |

#### 错误响应

**400 Bad Request** - 参数错误

```json
{
  "detail": "Missing required field: instId"
}
```

**403 Forbidden** - 认证失败

```json
{
  "detail": "Invalid webhook secret"
}
```

**403 Forbidden** - 交易对不在白名单

```json
{
  "detail": "Symbol not in allowlist"
}
```

**500 Internal Server Error** - 服务器错误

```json
{
  "detail": "Order placement failed: API error"
}
```

---

## 查询端点

### GET /health

健康检查端点，用于监控服务状态。

#### 请求示例

```bash
curl http://localhost:8000/health
```

#### 成功响应

**200 OK**

```json
{
  "status": "healthy",
  "timestamp": "2025-01-01T12:00:00Z"
}
```

---

### GET /

欢迎信息，返回服务基本信息。

#### 请求示例

```bash
curl http://localhost:8000/
```

#### 成功响应

**200 OK**

```json
{
  "name": "TW168 Trading Service",
  "version": "2.0.0",
  "exchange": "okx",
  "trading_enabled": false
}
```

---

### GET /candles/{symbol}

查询缓存的 K 线数据 (需要启用 WebSocket 缓存)。

#### 路径参数

| 参数 | 类型 | 说明 |
|------|------|------|
| symbol | string | 交易对，如 "ETH-USDT-SWAP" |

#### 查询参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| tf | string | ❌ | "1h" | 时间周期 |
| limit | integer | ❌ | 100 | 返回 K 线数量 |

#### 请求示例

```bash
curl "http://localhost:8000/candles/ETH-USDT-SWAP?tf=15m&limit=50"
```

#### 成功响应

**200 OK**

```json
{
  "symbol": "ETH-USDT-SWAP",
  "tf": "15m",
  "count": 50,
  "candles": [
    {
      "ts": 1735732800000,
      "open": 3500.00,
      "high": 3510.00,
      "low": 3495.00,
      "close": 3505.00,
      "volume": 1234.56
    }
  ]
}
```

#### 错误响应

**404 Not Found** - 无缓存数据

```json
{
  "detail": "No cached candles for ETH-USDT-SWAP@15m"
}
```

---

### GET /trades

查询当前活跃的交易计划。

#### 请求示例

```bash
curl http://localhost:8000/trades
```

#### 成功响应

**200 OK**

```json
{
  "count": 2,
  "trades": [
    {
      "inst_id": "ETH-USDT-SWAP",
      "side": "buy",
      "pos_side": "long",
      "entry_price": 3500.00,
      "stop_loss": 3425.00,
      "total_sz": "1.0",
      "r_value": 75.00,
      "tp1_done": false,
      "tp2_done": false,
      "tp3_done": false,
      "tp4_done": false,
      "trail_active": false
    }
  ]
}
```

---

## 错误处理

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 403 | 认证失败或权限不足 |
| 404 | 资源未找到 |
| 500 | 服务器内部错误 |

### 错误响应格式

所有错误响应遵循统一格式：

```json
{
  "detail": "Error message"
}
```

### 常见错误

#### 1. 无效的 Webhook 密钥

```json
{
  "detail": "Invalid webhook secret"
}
```

**解决方案:** 检查 `.env` 中的 `TV_WEBHOOK_SECRET` 配置。

#### 2. 交易对不在白名单

```json
{
  "detail": "Symbol ETH-USDT-SWAP not in allowlist"
}
```

**解决方案:** 在 `.env` 中的 `SYMBOL_ALLOWLIST` 添加交易对。

#### 3. 冷却时间未到

```json
{
  "ok": true,
  "skipped": "cooldown",
  "reason": "cooldown_active_for_95_seconds"
}
```

**解决方案:** 等待冷却时间结束或调整 `COOLDOWN_SECONDS` 配置。

#### 4. ZONE 状态过期

```json
{
  "ok": true,
  "skipped": "zone_expired_or_neutral"
}
```

**解决方案:** 先发送 ZONE 信号，再发送 DIV 信号。

---

## 示例代码

### Python

```python
import requests

# Webhook URL
url = "http://localhost:8000/webhook/tradingview"

# ZONE 信号
zone_payload = {
    "secret": "your_webhook_secret",
    "type": "ZONE",
    "zone": "OVERSOLD",
    "instId": "ETH-USDT-SWAP",
    "tf": "15m",
    "close": "3500.00"
}

response = requests.post(url, json=zone_payload)
print(response.json())

# DIV 信号
div_payload = {
    "secret": "your_webhook_secret",
    "type": "DIV",
    "instId": "ETH-USDT-SWAP",
    "tf": "15m",
    "close": "3501.20"
}

response = requests.post(url, json=div_payload)
print(response.json())
```

### cURL

```bash
# ZONE 信号
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_webhook_secret",
    "type": "ZONE",
    "zone": "OVERSOLD",
    "instId": "ETH-USDT-SWAP",
    "tf": "15m",
    "close": "3500.00"
  }'

# DIV 信号
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_webhook_secret",
    "type": "DIV",
    "instId": "ETH-USDT-SWAP",
    "tf": "15m",
    "close": "3501.20"
  }'
```

### JavaScript

```javascript
// ZONE 信号
const zonePayload = {
  secret: "your_webhook_secret",
  type: "ZONE",
  zone: "OVERSOLD",
  instId: "ETH-USDT-SWAP",
  tf: "15m",
  close: "3500.00"
};

fetch("http://localhost:8000/webhook/tradingview", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(zonePayload)
})
  .then(res => res.json())
  .then(data => console.log(data));

// DIV 信号
const divPayload = {
  secret: "your_webhook_secret",
  type: "DIV",
  instId: "ETH-USDT-SWAP",
  tf: "15m",
  close: "3501.20"
};

fetch("http://localhost:8000/webhook/tradingview", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(divPayload)
})
  .then(res => res.json())
  .then(data => console.log(data));
```

---

## TradingView Alert 配置

### 步骤 1: 创建 Alert

在 TradingView 图表上：
1. 右键点击 → "Add Alert"
2. 选择条件（你的指标/策略）
3. 设置触发频率："Once Per Bar Close"

### 步骤 2: 配置 Webhook

在 Alert 设置中：

**Webhook URL:**
```
http://your-server:8000/webhook/tradingview
```

**Message:** (ZONE 信号)
```json
{"secret":"your_webhook_secret","type":"ZONE","zone":"OVERSOLD","instId":"{{ticker}}","tf":"{{interval}}","t":"{{time}}","close":"{{close}}"}
```

**Message:** (DIV 信号)
```json
{"secret":"your_webhook_secret","type":"DIV","instId":"{{ticker}}","tf":"{{interval}}","t":"{{time}}","close":"{{close}}"}
```

### 可用的 TradingView 变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `{{ticker}}` | 交易对 | "BINANCE:ETHUSDT" |
| `{{interval}}` | 时间周期 | "15" |
| `{{time}}` | 时间戳 | "2025-01-01T12:00:00Z" |
| `{{close}}` | 收盘价 | "3500.50" |
| `{{open}}` | 开盘价 | "3495.00" |
| `{{high}}` | 最高价 | "3510.00" |
| `{{low}}` | 最低价 | "3490.00" |
| `{{volume}}` | 成交量 | "1234.56" |

**注意:**
- `{{ticker}}` 需要转换为 OKX 格式，如 `ETH-USDT-SWAP`
- `{{interval}}` 需要添加单位，如 "15m", "1h"

---

## 速率限制

目前 TW168 没有实现严格的速率限制，但建议：

- **ZONE 信号:** 每个交易对每分钟不超过 10 次
- **DIV 信号:** 每个交易对每分钟不超过 5 次
- **查询端点:** 每秒不超过 100 次

过于频繁的请求可能导致：
- 被冷却机制阻止
- 被去重机制过滤
- 消耗过多 API 配额

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 2.0 | 2025-01-01 | 添加 K 线缓存查询，添加交易计划查询 |
| 1.1 | 2024-12-20 | 优化 ZONE 过期逻辑 |
| 1.0 | 2024-12-20 | 初始版本 |

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
