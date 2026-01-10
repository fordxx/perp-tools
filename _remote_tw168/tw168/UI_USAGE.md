# TW168 交易控制面板 UI 使用指南

## 概述

TW168 现在配备了一个现代化的Web用户界面（UI），提供了一个友好的方式来管理和监控交易。UI服务器运行在 **端口 9000**，提供实时系统状态、手动信号发送和交易历史等功能。

## 启动UI服务器

### 远程下单模式（本地UI → 远程交易服务）

如果你的 UI 跑在本地（端口 9000），但希望把信号转发到远程服务器由远程程序按既定逻辑开单，推荐走 Nginx 的 **443**（更稳定，也不需要开放 8000），在本地 `.env` 增加：

```bash
TRADING_SERVICE_BASE_URL=https://<your-domain>
```

此时：
- UI 的 `/signals/send` 和 `/signals/send/form` 会转发到远程的 `/manual/signal`
- 管理员密钥仍使用 `TV_WEBHOOK_SECRET`（由远程服务校验；本地也会在配置了真实密钥时做一次校验）

### 信号来源区分（推荐）

系统会在审计日志（`SIGNAL_AUDIT_DIR` 下的 `tv_signals_YYYYMMDD.jsonl`）里记录 `signal_source` 字段：
- `signal_source=tradingview`：来自 `/webhook/tradingview`（TradingView）
- `signal_source=manual`：来自 `/manual/signal`（本地 UI/脚本转发）
- `signal_source=ui`：UI 直接在本机处理（未配置远程转发时）

### TradingView 信号过期（推荐）

如果担心“延迟很久的 TradingView 信号”误触发下单，可在远程 `.env` 配置：

```bash
TV_SIGNAL_MAX_AGE_SECONDS=300
```

当 webhook 的 payload 里 `t` 时间戳距离当前时间超过该阈值时，会跳过执行（仅记录，不下单）。

如果你仍想直连 `:8000`，需要满足：
- 远程服务监听 `0.0.0.0:8000`
- Lightsail 防火墙/安全组放行 8000

如果远程 8000 仅监听 `127.0.0.1`（推荐的安全做法），可以改用 SSH 隧道，然后本地 UI 指向隧道端口：

```bash
TRADING_SERVICE_BASE_URL=http://127.0.0.1:<local-tunnel-port>
```

### 方式1：本地启动（开发环境）

```bash
cd /path/to/tw168
/path/to/.venv/bin/python ui_server.py
```

服务器将在 `http://localhost:9000` 启动，输出如下：

```
🚀 启动TW168交易UI服务器...
📱 访问地址: http://localhost:9000
📊 功能包括:
   - 实时系统状态监控
   - 手动交易信号发送
   - 信号历史记录查看
   - 活跃仓位显示
INFO:     Uvicorn running on http://0.0.0.0:9000 (Press CTRL+C to quit)
```

### 方式2：后台启动（生产环境）

```bash
cd /path/to/tw168
nohup /path/to/.venv/bin/python ui_server.py > ui.log 2>&1 &
```

### 方式3：使用PM2 (推荐用于生产)

```bash
pm2 start "/.venv/bin/python ui_server.py" --name tw168-ui --cwd /path/to/tw168
```

## 网页界面

访问 `http://localhost:9000` 来打开UI（UI 推荐只在本机运行，不建议部署到远程服务器）

### 界面功能

#### 1. 顶部导航栏
- **系统状态指示灯**：绿色表示在线
- **交易所选择**：显示当前配置的交易所 (GRVT, OKX, Extended等)
- **交易模式**：实盘/纸上交易
- **运行时间**：显示系统运行时长

#### 2. 系统概览卡片（四个主卡片）

- **系统状态**：显示系统是否运行正常
- **最后信号**：显示上一个交易信号的时间
- **信号计数**：已发送的总信号数
- **活跃仓位**：当前打开的仓位数量

#### 3. 手动交易信号面板（左侧）

用于发送新的交易信号。字段包括：

| 字段 | 描述 | 示例 |
|------|------|------|
| **交易对** | 要交易的合约符号 | ETH-USDT-SWAP, BTC-USDT-SWAP |
| **时间周期** | K线周期 | 1m, 5m, 15m, 30m, 1h, 4h |
| **方向** | 交易方向 | 📈 做多 (buy) / 📉 做空 (sell) |
| **管理员密钥** | API密钥，用于验证 | （来自环境变量 TV_WEBHOOK_SECRET） |

**发送流程：**

1. 从下拉列表中选择交易对
2. 选择时间周期
3. 选择交易方向 (做多/做空)
4. 输入管理员密钥（来自 .env 中的 TV_WEBHOOK_SECRET）
5. 点击 **发送交易信号** 按钮

**响应示例：**

成功时：
```
✅ 信号发送成功！

交易对: ETH-USDT-SWAP
方向: long
入场价: 2500.123456
止损价: 2450.654321
数量: 1.0
```

失败时：
```
❌ 发送失败: Invalid admin key
```

#### 4. 信号历史面板（右侧）

显示最近20条信号的历史记录，包括：

- **时间戳**：信号发送时间（本地时间）
- **交易对**：ETH-USDT-SWAP 等
- **方向**：做多 (buy) / 做空 (sell) 标签
- **时间周期**：1h, 4h 等标签
- **状态**：✅ 成功 / ❌ 失败
- **成交信息**（成功时）：入场价、止损价、数量
- **错误信息**（失败时）：错误描述

## API 接口

UI也暴露了以下REST API端点，可用于集成：

### 1. 获取系统状态

**GET** `/api/system/status`

```bash
curl http://localhost:9000/api/system/status
```

**响应：**
```json
{
  "uptime": 3600,
  "exchange": "grvt",
  "trading_enabled": true,
  "total_signals": 5,
  "active_positions": 1,
  "last_signal": "2024-01-20T15:30:00.123456"
}
```

### 2. 获取信号历史

**GET** `/api/signals/history?limit=20`

```bash
curl "http://localhost:9000/api/signals/history?limit=20"
```

**响应：**
```json
{
  "history": [
    {
      "timestamp": "2024-01-20T15:30:00.123456",
      "signal": {
        "instId": "ETH-USDT-SWAP",
        "tf": "1h",
        "side": "long"
      },
      "result": {
        "ok": true,
        "entry": 2500.123456,
        "sl": 2450.654321,
        "order_sz": "1.0"
      },
      "status": "success"
    }
  ]
}
```

### 3. 发送交易信号（API）

**POST** `/signals/send`

```bash
curl -X POST http://localhost:9000/signals/send \
  -H "Content-Type: application/json" \
  -d '{
    "instId": "ETH-USDT-SWAP",
    "tf": "1h",
    "side": "long",
    "admin_key": "your-secret-key"
  }'
```

**响应：**
```json
{
  "ok": true,
  "type": "DIV",
  "zone": "OVERSOLD",
  "side": "buy",
  "entry": 2500.123456,
  "sl": 2450.654321,
  "tp3": 2550.654321,
  "order_sz": "1.0",
  "r_value": 49.468135
}
```

### 4. 发送交易信号（表单）

**POST** `/signals/send/form`

```bash
curl -X POST http://localhost:9000/signals/send/form \
  -d "instId=ETH-USDT-SWAP&tf=1h&side=long&admin_key=your-secret-key"
```

### 5. 健康检查

**GET** `/health`

```bash
curl http://localhost:9000/health
```

**响应：**
```json
{
  "status": "ok",
  "timestamp": "2024-01-20T15:30:00.123456"
}
```

## 实时功能

### 自动刷新
- 系统状态每 **5秒** 自动刷新一次
- 信号历史在发送新信号后自动更新
- 无需手动刷新页面

### 实时监控
- **运行时间**：实时显示系统运行时长
- **最后信号**：显示最新信号的时间戳
- **信号计数**：实时更新
- **交易对状态**：实时显示当前交易所和交易模式

## 安全性

### 认证
- 所有信号发送操作都需要 **管理员密钥**
- 管理员密钥来自 `.env` 文件中的 `TV_WEBHOOK_SECRET`
- 密钥通过HTTPS传输（在生产环境中使用反向代理）

### 最佳实践
1. **不要在浏览器控制台泄露密钥**
2. **使用HTTPS**（在生产环境中配置Nginx/Apache）
3. **限制访问IP**（配置防火墙规则）
4. **定期更换密钥**（通过更新 .env 文件）

## 配置

### 环境变量

在 `.env` 文件中配置：

```env
# UI服务器配置
EXCHANGE=grvt  # 交易所
TRADING_ENABLED=true  # 是否启用交易
TV_WEBHOOK_SECRET=your-secret-key  # 管理员密钥
```

### 端口配置

修改 `ui_server.py` 中的最后一行来更改端口：

```python
if __name__ == "__main__":
    # ...
    uvicorn.run(ui_app, host="0.0.0.0", port=9000, log_level="info")  # 改为其他端口
```

## 常见问题

### Q: UI无法连接到交易系统
**A:** 确保主要的trading服务（app.main）也在运行，UI服务器需要导入并使用主应用的模块。

### Q: 密钥错误显示为"无效管理员密钥"
**A:** 确认密钥与 `.env` 文件中的 `TV_WEBHOOK_SECRET` 完全匹配（区分大小写）。

### Q: 信号发送时收到"模块未找到"错误
**A:** 确保所有依赖都已安装：
```bash
./.venv/bin/pip install -r requirements.txt
./.venv/bin/pip install jinja2 python-multipart
```

### Q: 如何在远程服务器上访问UI
**A:** 
1. 在服务器上启动UI服务器
2. （不推荐）将 UI 部署到远程服务器：请自行做好访问控制与风控隔离
3. 配置防火墙允许9000端口
4. 使用反向代理（Nginx）配置HTTPS

## 使用Nginx反向代理（不推荐：仅在你确实要把 UI 部署到远程服务器时使用）

创建 `/etc/nginx/sites-available/tw168-ui` 文件：

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

启用配置：
```bash
sudo ln -s /etc/nginx/sites-available/tw168-ui /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 支持的交易所

根据 `EXCHANGE` 环境变量，UI支持：

- `okx` - OKX交易所
- `grvt` - Gravity (GRVT)
- `extended` - Extended DEX
- `paradex` - Paradex
- `lighter` - Lighter Protocol

## 监控和日志

### UI服务器日志

```bash
# 查看实时日志
tail -f ui.log

# 查看最后100行
tail -100 ui.log

# 查看特定错误
grep ERROR ui.log
```

### 主交易系统日志

```bash
# 查看主应用日志
tail -f tw168.log

# 查看最后100行
tail -100 tw168.log
```

## 故障排除

### 问题：服务器无法启动
```bash
# 1. 检查端口是否被占用
lsof -i :9000

# 2. 如果被占用，杀死进程
kill -9 <PID>

# 3. 再次启动
./.venv/bin/python ui_server.py
```

### 问题：模板加载失败
```bash
# 确保templates目录存在
ls -la templates/

# 确保有index.html
ls -la templates/index.html
```

### 问题：API响应缓慢
```bash
# 检查系统资源
top

# 检查主应用是否运行
ps aux | grep main.py
```

## 下一步

1. **部署到生产环境**：使用PM2或systemd管理进程
2. **配置HTTPS**：使用Let's Encrypt + Nginx
3. **备份配置**：定期备份 `.env` 和日志
4. **监控**：配置Telegram通知和指标导出

## 联系支持

如遇问题，请查阅主README.md或提交issue。
