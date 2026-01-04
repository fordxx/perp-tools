# 本地 UI 快速启动指南

## 概述

本地 UI 现已配置为通过 **HTTPS** 安全访问远程交易服务。

---

## 方式 1: 命令行工具（推荐用于快速测试）

### 直接运行（无需配置）

```bash
# 基本用法（需要提供 admin_key）
python3 send_manual_signal.py ETH-USDT-SWAP long -k YOUR_ADMIN_KEY

# 完整示例
python3 send_manual_signal.py BTC-USDT-SWAP short \
  -t 15m \
  -k YOUR_ADMIN_KEY
```

**说明**:
- 已内置 HTTPS URL 和 BasicAuth 凭据
- 只需提供 `admin_key`（从远程服务器 `.env` 获取）

### 从环境变量读取 admin_key

```bash
# 1. 设置环境变量
export TV_WEBHOOK_SECRET="your-admin-key-from-remote-env"

# 2. 运行（自动使用环境变量）
python3 send_manual_signal.py ETH-USDT-SWAP long
```

---

## 方式 2: Web UI（推荐用于日常使用）

### 启动步骤

#### 1. 配置环境变量

创建或编辑本地 `.env` 文件：

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置
nano .env
```

**必须配置的变量**:

```bash
# 远程服务地址（已包含 BasicAuth）
TRADING_SERVICE_BASE_URL=https://trader:TW168Trading!2026@3-38-98-169.nip.io

# 管理员密钥（从远程服务器的 .env 复制）
TV_WEBHOOK_SECRET=your-actual-admin-key-here

# 其他可选配置
EXCHANGE=lighter  # 或 grvt
```

#### 2. 启动 UI 服务器

```bash
# 方式 A: 直接运行
python3 ui_server.py

# 方式 B: 使用启动脚本（如果存在）
./start_ui_server.sh
```

#### 3. 访问 UI

打开浏览器访问：
```
http://localhost:9000
```

**UI 功能**:
- 📊 实时系统状态
- 📈 手动信号发送
- 📝 信号历史记录
- 📱 响应式设计（支持手机访问）

---

## 安全说明

### BasicAuth 凭据

**用户名**: `trader`
**密码**: `TW168Trading!2026`

**重要**: 这些凭据已内置到 URL 中，无需手动输入。

### 传输安全

- ✅ 所有通信通过 HTTPS 加密
- ✅ BasicAuth 提供访问控制
- ✅ admin_key 提供应用层验证

---

## 完整测试示例

### 测试 1: 命令行快速测试

```bash
# 导出 admin_key（从远程 ~/tw168/.env 获取）
export TV_WEBHOOK_SECRET="your-real-admin-key"

# 发送测试信号
python3 send_manual_signal.py ETH-USDT-SWAP long -t 15m

# 预期输出
# 📤 发送手动信号到 https://trader:***@3-38-98-169.nip.io
# 🎯 交易对: ETH-USDT-SWAP
# ⏰ 时间周期: 15m
# 📈 方向: long
# --------------------------------------------------
# 📊 HTTP状态码: 200
# ✅ 信号发送成功!
```

### 测试 2: Python 脚本集成

```python
# test_signal.py
from send_manual_signal import send_manual_signal
import os

# 从环境变量或直接设置
admin_key = os.getenv("TV_WEBHOOK_SECRET") or "your-admin-key"

result = send_manual_signal(
    inst_id="BTC-USDT-SWAP",
    tf="1h",
    side="long",
    admin_key=admin_key
)

if "error" not in result:
    print(f"✅ 信号成功: {result.get('instId')} @ {result.get('entry')}")
else:
    print(f"❌ 失败: {result['error']}")
```

### 测试 3: Web UI 测试

1. **启动 UI**:
   ```bash
   python3 ui_server.py
   ```

2. **打开浏览器**: `http://localhost:9000`

3. **填写表单**:
   - 交易对: `ETH-USDT-SWAP`
   - 时间周期: `15m`
   - 方向: `Long`
   - Admin Key: `your-admin-key`

4. **点击发送**，查看实时响应

---

## 故障排查

### 问题 1: "Connection error"

**原因**: 无法连接到 HTTPS 端点

**排查**:
```bash
# 1. 测试 HTTPS 连接
curl https://3-38-98-169.nip.io/health

# 2. 测试带 BasicAuth
curl -u trader:TW168Trading!2026 https://3-38-98-169.nip.io/metrics

# 3. 检查远程服务器状态
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  "sudo systemctl status nginx && docker ps"
```

### 问题 2: "403 Forbidden" 或 "401 Unauthorized"

**原因**: BasicAuth 凭据错误

**解决**:
- 检查密码是否正确: `TW168Trading!2026`
- 查看远程 Nginx 日志:
  ```bash
  ssh ubuntu@3.38.98.169 "sudo tail -20 /var/log/nginx/tv-okx-error.log"
  ```

### 问题 3: "Invalid admin key"

**原因**: 应用层 admin_key 错误

**解决**:
```bash
# 查看远程服务器的正确 admin_key
ssh ubuntu@3.38.98.169 "grep TV_WEBHOOK_SECRET ~/tw168/.env"

# 更新本地环境变量
export TV_WEBHOOK_SECRET="correct-key-from-remote"
```

### 问题 4: SSL 证书错误

**原因**: 证书验证失败（罕见）

**临时解决**（仅调试用）:
```python
# 在 send_manual_signal.py 中添加
response = requests.post(url, json=payload, timeout=30, verify=False)
```

**永久解决**:
```bash
# 更新系统证书
sudo apt update && sudo apt install -y ca-certificates
```

---

## 获取 admin_key

```bash
# SSH 连接到远程服务器
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# 查看 admin_key
grep TV_WEBHOOK_SECRET ~/tw168/.env

# 输出示例: TV_WEBHOOK_SECRET=abc123xyz
```

将此值复制到本地 `.env` 或 `export TV_WEBHOOK_SECRET=abc123xyz`

---

## 性能优化

### 减少延迟

```python
# 在 send_manual_signal.py 中使用 Session 复用
import requests

session = requests.Session()
session.auth = ("trader", "TW168Trading!2026")

# 重复使用
for signal in signals:
    response = session.post(url, json=signal)
```

### 异步批量发送

```python
import asyncio
import httpx

async def send_signals(signals):
    async with httpx.AsyncClient() as client:
        tasks = [
            client.post(
                "https://trader:TW168Trading!2026@3-38-98-169.nip.io/manual/signal",
                json=s
            )
            for s in signals
        ]
        return await asyncio.gather(*tasks)

# 使用
results = asyncio.run(send_signals([...]))
```

---

## 监控与日志

### 查看本地日志

```bash
# UI 服务器会输出到控制台
# 或重定向到文件
python3 ui_server.py > ui.log 2>&1 &
tail -f ui.log
```

### 查看远程日志

```bash
# 访问日志（查看所有请求）
ssh ubuntu@3.38.98.169 "sudo tail -f /var/log/nginx/tv-okx-access.log"

# 错误日志（仅错误）
ssh ubuntu@3.38.98.169 "sudo tail -f /var/log/nginx/tv-okx-error.log"

# 过滤手动信号
ssh ubuntu@3.38.98.169 "sudo grep '/manual/signal' /var/log/nginx/tv-okx-access.log | tail -20"
```

---

## 凭据管理建议

### 1. 使用环境变量（推荐）

```bash
# ~/.bashrc 或 ~/.zshrc
export TV_WEBHOOK_SECRET="your-secret-here"
export TRADING_SERVICE_BASE_URL="https://trader:TW168Trading!2026@3-38-98-169.nip.io"
```

### 2. 使用 .env 文件

```bash
# .env（不要提交到 git）
TV_WEBHOOK_SECRET=your-secret-here
TRADING_SERVICE_BASE_URL=https://trader:TW168Trading!2026@3-38-98-169.nip.io
```

### 3. 使用密码管理器

将凭据保存到 1Password、Bitwarden 等密码管理器，需要时复制。

---

## 与远程服务通信流程

```
本地 UI/脚本
    ↓ HTTPS (TLS 1.2/1.3)
    ↓ BasicAuth: trader:TW168Trading!2026
3-38-98-169.nip.io:443
    ↓ Nginx 验证 BasicAuth
    ↓ Nginx 限流检查
    ↓ 反向代理到 127.0.0.1:8001
Docker 容器 (tv-router)
    ↓ 验证 admin_key
    ↓ 路由到后端服务
    ↓ 执行交易逻辑
返回响应
```

---

## 快速命令参考

```bash
# 测试连接
curl https://3-38-98-169.nip.io/health

# 发送信号（命令行）
python3 send_manual_signal.py ETH-USDT-SWAP long -k YOUR_KEY

# 启动 UI
python3 ui_server.py

# 查看远程日志
ssh ubuntu@3.38.98.169 "docker logs -f tw168-tv-router-1"

# 获取 admin_key
ssh ubuntu@3.38.98.169 "grep TV_WEBHOOK_SECRET ~/tw168/.env"
```

---

## 总结

### ✅ 已配置
- HTTPS 端点: `https://3-38-98-169.nip.io`
- BasicAuth: 内置到 URL
- 命令行工具: `send_manual_signal.py`
- Web UI: `ui_server.py`

### 🔑 需要的凭据
1. **BasicAuth**: `trader:TW168Trading!2026`（已内置）
2. **admin_key**: 从远程 `~/tw168/.env` 获取

### 🚀 开始使用
```bash
# 1. 获取 admin_key
ssh ubuntu@3.38.98.169 "grep TV_WEBHOOK_SECRET ~/tw168/.env"

# 2. 设置环境变量
export TV_WEBHOOK_SECRET="从步骤1获取的值"

# 3. 发送测试信号
python3 send_manual_signal.py ETH-USDT-SWAP long
```

**完成！现在可以安全地从本地访问远程交易服务 🎉**
