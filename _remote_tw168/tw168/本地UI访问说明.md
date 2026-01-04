# ✅ 本地 UI 已配置完成

## 快速开始（3 步）

### 1️⃣ 获取 admin_key

```bash
# SSH 连接到远程服务器
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# 查看 admin_key
grep TV_WEBHOOK_SECRET ~/tw168/.env

# 复制输出的值，例如: TV_WEBHOOK_SECRET=abc123xyz
```

### 2️⃣ 配置本地环境

```bash
# 方式 A: 使用环境变量（推荐）
export TV_WEBHOOK_SECRET="从步骤1获取的值"

# 方式 B: 编辑 .env 文件
nano .env
# 找到 TV_WEBHOOK_SECRET 行，替换为实际值
```

### 3️⃣ 发送测试信号

```bash
# 命令行方式
python3 send_manual_signal.py ETH-USDT-SWAP long

# 或启动 Web UI
python3 ui_server.py
# 然后访问 http://localhost:9000
```

---

## 测试验证

运行自动测试脚本：

```bash
./test_local_to_remote.sh
```

**预期输出**: 全部 ✓（绿色对勾）

---

## 配置说明

### 已内置配置

以下配置已自动设置，**无需修改**:

- **远程地址**: `https://3-38-98-169.nip.io`
- **BasicAuth**: `trader:TW168Trading!2026`
- **HTTPS**: 自动使用 TLS 1.3 加密

### 需要配置的唯一参数

**admin_key（TV_WEBHOOK_SECRET）**: 从远程服务器获取

---

## 使用方式

### 方式 1: 命令行工具

```bash
# 基本用法
python3 send_manual_signal.py <交易对> <方向> -k <admin_key>

# 示例
python3 send_manual_signal.py BTC-USDT-SWAP long -k abc123
python3 send_manual_signal.py ETH-USDT-SWAP short -t 15m -k abc123

# 使用环境变量（无需每次输入 -k）
export TV_WEBHOOK_SECRET="abc123"
python3 send_manual_signal.py BTC-USDT-SWAP long
```

### 方式 2: Web UI

```bash
# 1. 启动 UI 服务器
python3 ui_server.py

# 2. 打开浏览器
http://localhost:9000

# 3. 填写表单发送信号
```

### 方式 3: Python 代码集成

```python
from send_manual_signal import send_manual_signal

result = send_manual_signal(
    inst_id="ETH-USDT-SWAP",
    tf="1h",
    side="long",
    admin_key="your-admin-key"
)

if "error" not in result:
    print(f"✅ 成功: {result.get('instId')} @ {result.get('entry')}")
```

---

## 限流说明

- **平均速率**: 5 次/分钟（每 12 秒 1 次）
- **突发容量**: 10 次（短时间内可连续发 10 单）
- **超限行为**: 返回 HTTP 429，等待 12 秒后重试

**示例场景**:
- 连续发 5 单 → ✅ 立即成功
- 连续发 10 单 → ✅ 立即成功
- 连续发 15 单 → ⚠️ 前 10 单成功，后 5 单被限流（需等待）

---

## 安全性

### 三层防护

1. **传输层**: HTTPS TLS 1.3 加密
2. **网关层**: BasicAuth 认证
3. **应用层**: admin_key 验证

### 端口安全

- ✅ 8000/8001 端口仅监听 `127.0.0.1`（公网不可访问）
- ✅ 仅 443 端口对外开放
- ✅ 所有流量通过 Nginx 反向代理

---

## 故障排查

### 连接失败

```bash
# 测试 HTTPS 连接
curl https://3-38-98-169.nip.io/health

# 如果失败，检查远程服务
ssh ubuntu@3.38.98.169 "sudo systemctl status nginx && docker ps"
```

### 401 Unauthorized

**原因**: BasicAuth 凭据错误（不太可能，已内置）

**解决**: 检查代码中的密码是否为 `TW168Trading!2026`

### 403 Forbidden（应用返回）

**原因**: admin_key 错误

**解决**:
```bash
# 1. 重新获取正确的 admin_key
ssh ubuntu@3.38.98.169 "grep TV_WEBHOOK_SECRET ~/tw168/.env"

# 2. 更新本地环境变量
export TV_WEBHOOK_SECRET="正确的值"
```

### 429 Too Many Requests

**原因**: 超出限流（每分钟 >5 次，或短时间 >10 次）

**解决**: 等待 12 秒后重试，或减少请求频率

---

## 相关文档

- **部署详情**: [DEPLOYMENT_SUCCESS_NGINX.md](DEPLOYMENT_SUCCESS_NGINX.md)
- **UI 使用指南**: [LOCAL_UI_QUICKSTART.md](LOCAL_UI_QUICKSTART.md)
- **测试脚本**: `./test_local_to_remote.sh`

---

## 技术架构

```
本地电脑
  ↓ python3 send_manual_signal.py
  ↓ HTTPS (TLS 1.3)
  ↓ BasicAuth: trader:TW168Trading!2026
Internet
  ↓
3-38-98-169.nip.io:443
  ↓ Nginx 反向代理
  ↓ 限流检查
  ↓ BasicAuth 验证
127.0.0.1:8001 (Docker 容器 tv-router)
  ↓ admin_key 验证
  ↓ 路由到后端
127.0.0.1:8000 (Docker 容器 tv-okx)
  ↓ 执行交易逻辑
返回结果
```

---

## 常用命令速查

```bash
# 测试连接
./test_local_to_remote.sh

# 查看健康状态
curl https://3-38-98-169.nip.io/health

# 发送信号（命令行）
python3 send_manual_signal.py ETH-USDT-SWAP long -k <admin_key>

# 启动 Web UI
python3 ui_server.py

# 查看远程日志
ssh ubuntu@3.38.98.169 "docker logs -f tw168-tv-router-1"

# 获取 admin_key
ssh ubuntu@3.38.98.169 "grep TV_WEBHOOK_SECRET ~/tw168/.env"
```

---

## 总结

### ✅ 已完成
- HTTPS 端点配置
- BasicAuth 自动认证
- 命令行工具更新
- Web UI 支持
- 限流优化（5/min，突发 10）
- 测试脚本

### 🔑 唯一需要配置
- `TV_WEBHOOK_SECRET`（admin_key）

### 🚀 立即可用
```bash
export TV_WEBHOOK_SECRET="从远程获取"
python3 send_manual_signal.py ETH-USDT-SWAP long
```

**完成！现在可以安全、稳定地从本地访问远程交易服务 🎉**
