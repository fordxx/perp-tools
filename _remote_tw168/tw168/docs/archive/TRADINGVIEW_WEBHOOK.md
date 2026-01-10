# TradingView Webhook 配置指南

> ⚠️ 说明：此文档归档自早期方案，`http://3.38.98.169:8000` 属于旧的直连方式；当前推荐通过 Nginx **443** 访问（示例域名：`https://trader:***@3-38-98-169.nip.io`）。

## 🔴 当前问题

您的TradingView警报发送的webhook格式不正确，缺少必填字段 `type` 和 `instId`，导致服务器返回500错误。

## ✅ 正确的Webhook配置

### Webhook URL

```
https://trader:TW168Trading!2026@3-38-98-169.nip.io/webhook/tradingview
```

### Webhook消息格式

TradingView警报的"消息"部分必须使用以下JSON格式：

#### ZONE信号（设置交易区域）

```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "ZONE",
  "instId": "XRP-USDT-SWAP",
  "tf": "3m",
  "zone": "{{close}}",
  "side": "{{strategy.market_position}}"
}
```

**字段说明**：
- `secret`: Webhook密钥（从.env文件获取：TV_WEBHOOK_SECRET）
- `type`: 固定值 "ZONE"
- `instId`: OKX交易对名称，格式：币种-USDT-SWAP
  - BTC: `BTC-USDT-SWAP`
  - ETH: `ETH-USDT-SWAP`
  - XRP: `XRP-USDT-SWAP`
  - SOL: `SOL-USDT-SWAP`
  - 等等
- `tf`: 时间周期（如 "1m", "3m", "5m", "15m", "1h", "4h"等）
- `zone`: 区域价格，使用 `{{close}}` 获取当前K线收盘价
- `side`: 方向
  - 做多用：`"long"` 或 `{{strategy.market_position}}` (如果使用策略)
  - 做空用：`"short"`

#### DIV信号（触发交易）

```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "DIV",
  "instId": "XRP-USDT-SWAP",
  "tf": "3m",
  "close": "{{close}}",
  "t": "{{time}}",
  "rsi": "{{plot_0}}",
  "rsi_long": "50",
  "rsi_short": "50"
}
```

**字段说明**：
- `type`: 固定值 "DIV"（触发交易信号）
- `close`: 当前价格，使用 `{{close}}`
- `t`: 时间戳，使用 `{{time}}`
- `rsi`: RSI值（如果使用RSI过滤），使用 `{{plot_0}}` 或具体数值
- `rsi_long`: 做多RSI阈值（可选）
- `rsi_short`: 做空RSI阈值（可选）

## 📋 TradingView警报配置步骤

### 1. 创建警报

在TradingView图表上右键点击 → 添加警报

### 2. 配置警报条件

- **条件**: 选择您的指标或策略条件
- **选项**:
  - ☑️ Webhook URL
  - 输入：`https://trader:TW168Trading!2026@3-38-98-169.nip.io/webhook/tradingview`

### 3. 配置消息

根据警报类型，在"消息"框中输入对应的JSON：

**示例：XRP 3分钟 ZONE信号**
```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "ZONE",
  "instId": "XRP-USDT-SWAP",
  "tf": "3m",
  "zone": "{{close}}",
  "side": "long"
}
```

**示例：XRP 3分钟 DIV信号**
```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "DIV",
  "instId": "XRP-USDT-SWAP",
  "tf": "3m",
  "close": "{{close}}",
  "t": "{{time}}"
}
```

### 4. 保存警报

点击"创建"保存警报配置

## 🔧 常见币种的instId映射

| TradingView符号 | OKX instId |
|----------------|------------|
| XRPUSDT.P | XRP-USDT-SWAP |
| BTCUSDT.P | BTC-USDT-SWAP |
| ETHUSDT.P | ETH-USDT-SWAP |
| SOLUSDT.P | SOL-USDT-SWAP |
| BCHUSDT.P | BCH-USDT-SWAP |
| TRXUSDT.P | TRX-USDT-SWAP |
| AAVEUSDT.P | AAVE-USDT-SWAP |
| ONDOUSDT.P | ONDO-USDT-SWAP |

## 🧪 测试Webhook

### 方法1：使用curl测试

```bash
curl -X POST https://3-38-98-169.nip.io/webhook/tradingview \
  -u "trader:TW168Trading!2026" \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
    "type": "ZONE",
    "instId": "XRP-USDT-SWAP",
    "tf": "3m",
    "zone": "2.5",
    "side": "long"
  }'
```

应该返回：
```json
{"ok": true, "msg": "zone_recorded"}
```

### 方法2：发送DIV测试

```bash
curl -X POST https://3-38-98-169.nip.io/webhook/tradingview \
  -u "trader:TW168Trading!2026" \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfgggdhsfgfdghgdgfhgfgsgdsfeaff6",
    "type": "DIV",
    "instId": "XRP-USDT-SWAP",
    "tf": "3m",
    "close": "2.5",
    "t": "2025-12-26 10:00:00"
  }'
```

## 🔍 故障排查

### 1. 检查服务器日志

```bash
ssh -i /home/fordxx/lightsail.pem ubuntu@3.38.98.169
sudo docker logs tw168-tv-okx-1 --tail 100 -f
```

### 2. 验证webhook格式

常见错误：
- ❌ 缺少 `type` 字段
- ❌ 缺少 `instId` 字段
- ❌ `secret` 不匹配
- ❌ `instId` 格式错误（应该是 `XRP-USDT-SWAP` 而不是 `XRPUSDT.P`）
- ❌ JSON格式错误（缺少引号、逗号等）

### 3. 检查symbol是否在白名单中

服务器.env配置的白名单：
```bash
SYMBOL_ALLOWLIST=ETH-USDT-SWAP,BTC-USDT-SWAP,SOL-USDT-SWAP,BCH-USDT-SWAP,XRP-USDT-SWAP,ONDO-USDT-SWAP,AAVE-USDT-SWAP,TRX-USDT-SWAP
```

如果您的币种不在列表中，需要添加到 `.env` 文件的 `SYMBOL_ALLOWLIST`。

## 💡 工作流程

系统的完整工作流程：

1. **ZONE信号**: TradingView发送ZONE webhook
   - 系统记录交易区域和方向
   - 区域有效期：12小时（ZONE_TTL_SECONDS=43200）

2. **DIV信号**: TradingView发送DIV webhook
   - 系统检查是否有对应的ZONE记录
   - 如果有，执行开仓
   - 自动设置止损（基于lookback方法）
   - 自动设置TP阶梯（1.5R, 2.0R, 2.5R, 3.5R）

3. **风险管理**:
   - 止损失败 → 自动紧急平仓
   - TP逐步获利（70%, 15%, 10%, 5%）
   - 移动止损（2.0R开始，回撤0.75R）

## 📝 完整示例

### TradingView策略代码示例

```pine
//@version=5
strategy("TW168 Webhook", overlay=true)

// 在策略的买入/卖出条件中添加警报
if (买入条件)
    strategy.entry("Long", strategy.long)
    alert('{"secret":"rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6","type":"DIV","instId":"XRP-USDT-SWAP","tf":"3m","close":"' + str.tostring(close) + '","t":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)

if (卖出条件)
    strategy.entry("Short", strategy.short)
    alert('{"secret":"rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6","type":"DIV","instId":"XRP-USDT-SWAP","tf":"3m","close":"' + str.tostring(close) + '","t":"' + str.tostring(time) + '"}', alert.freq_once_per_bar_close)
```

---

## ⚠️ 重要提示

1. **不要泄露secret**: Webhook密钥是系统安全的关键，不要分享给他人
2. **确认instId格式**: 必须使用OKX格式（如 `XRP-USDT-SWAP`），不是TradingView格式
3. **测试再上线**: 先用curl测试webhook格式正确，再在TradingView中配置
4. **检查白名单**: 确保交易的币种在 `SYMBOL_ALLOWLIST` 中

---

配置完成后，您的TradingView警报将能正确触发tw168系统的自动交易！
