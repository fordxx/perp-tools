# 手动交易信号发送功能

## 概述

新增的手动信号发送功能允许用户通过API直接发送交易信号到远程服务器，无需依赖TradingView webhook。系统会复用所有现有的交易逻辑，包括止损止盈计算、风控规则等。

## 功能特性

✅ **复用现有逻辑** - 使用与TradingView webhook相同的处理流程
✅ **完整风控** - 支持所有现有的风险管理规则（cooldown、paper trade等）
✅ **多渠道发送** - 支持cURL、Python脚本、网页表单
✅ **密钥验证** - 防止未授权访问
✅ **实时反馈** - 返回详细的执行结果

## API 端点

### POST `/manual/signal`

手动发送交易信号的API端点。

#### 请求参数

```json
{
  "instId": "ETH-USDT-SWAP",
  "tf": "1h",
  "side": "long",
  "type": "DIV",
  "admin_key": "your_admin_key"
}
```

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `instId` | string | 是 | 交易对，如 `ETH-USDT-SWAP` |
| `tf` | string | 否 | 时间周期，默认 `1h` |
| `side` | string | 是 | 方向：`long` 或 `short` |
| `type` | string | 否 | 信号类型，默认 `DIV` |
| `admin_key` | string | 是 | 管理员密钥（与TradingView webhook密钥相同） |

#### 响应示例

```json
{
  "ok": true,
  "type": "DIV",
  "zone": "OVERSOLD",
  "side": "long",
  "posSide": "long",
  "entry": 2456.78,
  "sl": 2432.12,
  "tp": 2481.44,
  "order_sz": "0.1",
  "r_value": 24.66,
  "order": {
    "code": "0",
    "msg": "",
    "data": [...]
  }
}
```

## 使用方法

### 1. 命令行工具

使用 `send_manual_signal.py` 脚本：

```bash
# 基本用法
python send_manual_signal.py ETH-USDT-SWAP long

# 指定时间周期
python send_manual_signal.py BTC-USDT-SWAP short -t 4h

# 指定服务器URL和密钥
python send_manual_signal.py SOL-USDT-SWAP long -u https://trader:TW168Trading!2026@3-38-98-169.nip.io -k your_key
```

### 2. cURL 命令

```bash
curl -X POST https://3-38-98-169.nip.io/manual/signal \
  -u "trader:TW168Trading!2026" \
  -H "Content-Type: application/json" \
  -d '{
    "instId": "ETH-USDT-SWAP",
    "tf": "1h",
    "side": "long",
    "type": "DIV",
    "admin_key": "your_admin_key"
  }'
```

### 3. Python 脚本

```python
import requests

def send_signal(symbol, side, tf="1h"):
    response = requests.post(
        "https://3-38-98-169.nip.io/manual/signal",
        json={
            "instId": symbol,
            "tf": tf,
            "side": side,
            "admin_key": "your_admin_key"
        }
    )
    return response.json()

# 示例
result = send_signal("BTC-USDT-SWAP", "long")
print(result)
```

### 4. 网页表单

打开 `manual_signal.html` 文件在浏览器中，选择参数并点击发送。

## 部署流程

1. **修改代码**
   - 已添加 `ManualSignalRequest` 模型
   - 已添加 `/manual/signal` 端点

2. **部署到远程服务器**
   ```bash
   ./deploy_remote_rsync.sh
   ```

3. **测试功能**
   ```bash
   # 本地测试
   python test_manual_signal.py

   # 远程测试
   python send_manual_signal.py ETH-USDT-SWAP long -u https://trader:TW168Trading!2026@3-38-98-169.nip.io
   ```

## 安全注意事项

⚠️ **重要提醒**

- 管理员密钥与TradingView webhook密钥相同，请妥善保管
- 此功能会立即在交易所开仓，请谨慎使用
- 建议在测试环境先验证功能
- 生产环境使用时确保网络安全

## 支持的交易对

系统支持所有配置的交易对，包括：
- BTC-USDT-SWAP
- ETH-USDT-SWAP
- SOL-USDT-SWAP
- LINK-USDT-SWAP
- DOGE-USDT-SWAP
- 等等...

## 时间周期

支持的时间周期：
- 1m, 5m, 15m, 30m
- 1h, 4h

## 故障排除

### 常见错误

1. **403 Forbidden**: 管理员密钥无效
2. **400 Bad Request**: 参数格式错误
3. **500 Internal Server Error**: 服务器内部错误

### 调试方法

1. 检查服务器日志：`docker logs tw168`
2. 验证密钥是否正确
3. 确认交易对和时间周期格式
4. 检查网络连接

## 文件清单

- `app/main.py` - 主应用文件（已修改）
- `test_manual_signal.py` - 测试脚本
- `send_manual_signal.py` - 命令行工具
- `manual_signal.html` - 网页表单
