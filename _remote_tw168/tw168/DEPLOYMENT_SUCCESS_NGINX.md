# ✅ Nginx HTTPS 反向代理部署成功

## 部署总结

**完成时间**: 2026-01-03
**服务地址**: `https://3-38-98-169.nip.io`
**安全认证**: BasicAuth + ADMIN_KEY 双重验证

---

## 安全架构

```
Internet (任何设备/IP)
    ↓ HTTPS:443 (TLS 1.2/1.3 加密)
Lightsail Firewall (只开放 80/443)
    ↓
Nginx (反向代理)
    ├── BasicAuth 验证 (/manual/signal, /metrics 等敏感端点)
    ├── 限流保护 (2 req/min for signals, 10 req/s for others)
    └── 反向代理到内部端口
         ↓ HTTP (仅本地可访问)
Docker Containers
    ├── tv-okx: 127.0.0.1:8000 (主服务)
    └── tv-router: 127.0.0.1:8001 (路由服务)
```

---

## 安全措施

### ✅ 已实现的安全层级

1. **网络层**
   - ✅ Docker 端口仅绑定 127.0.0.1（不暴露到公网）
   - ✅ Lightsail 防火墙只开放 80/443 端口
   - ✅ 8000/8001 端口公网不可访问

2. **传输层**
   - ✅ 强制 HTTPS（Let's Encrypt 证书）
   - ✅ TLS 1.2/1.3 加密
   - ✅ HTTP 自动重定向到 HTTPS

3. **应用层**
   - ✅ BasicAuth 保护敏感端点（用户名: trader）
   - ✅ admin_key 验证（应用内验证）
   - ✅ 限流保护（防止暴力破解和滥用）

---

## 访问凭据

### BasicAuth（Nginx 层）
```
用户名: trader
密码: TW168Trading!2026
```

### Admin Key（应用层）
```
配置在远程服务器: ~/tw168/.env
变量名: ADMIN_KEY
```

---

## 端点访问指南

### 1. 健康检查（无需认证）

```bash
# HTTP（会自动重定向到 HTTPS）
curl http://3-38-98-169.nip.io/health

# HTTPS
curl https://3-38-98-169.nip.io/health
```

**响应**: `{"status":"ok"}`

---

### 2. Metrics 监控（需要 BasicAuth）

```bash
curl -u trader:TW168Trading!2026 https://3-38-98-169.nip.io/metrics
```

---

### 3. 手动信号（需要 BasicAuth + admin_key）

```bash
curl -u trader:TW168Trading!2026 \
  -X POST https://3-38-98-169.nip.io/manual/signal \
  -H "Content-Type: application/json" \
  -d '{
    "instId": "BTC-USDT-SWAP",
    "tf": "15m",
    "side": "buy",
    "admin_key": "YOUR_ADMIN_KEY_FROM_ENV"
  }'
```

**Python 示例**:

```python
import requests

API_URL = "https://3-38-98-169.nip.io/manual/signal"
BASIC_AUTH = ("trader", "TW168Trading!2026")
ADMIN_KEY = "your-admin-key-from-env"

response = requests.post(
    API_URL,
    auth=BASIC_AUTH,
    json={
        "instId": "BTC-USDT-SWAP",
        "tf": "15m",
        "side": "buy",
        "admin_key": ADMIN_KEY,
    },
    timeout=10,
)

print(response.json())
```

---

### 4. TradingView Webhook（公开，无需 BasicAuth）

TradingView 无法提供 BasicAuth，因此此端点保持公开（仅 HTTPS）：

```
URL: https://3-38-98-169.nip.io/webhook/tradingview
Method: POST
```

**注意**: 此端点依赖应用内的 admin_key 验证来确保安全性。

---

## 限流策略

| 端点 | 限制 | 突发容量 | 说明 |
|-----|-----|---------|-----|
| /health | 10 req/s | 20 | 健康检查 |
| /webhook/tradingview | 10 req/s | 10 | TradingView 信号 |
| /metrics, /emergency 等 | 10 req/s | 5-10 | 监控端点 |
| /manual/signal | **5 req/min** | **10** | 手动信号，可短时间连续发 10 单 |

**超出限制**: 返回 HTTP 429 Too Many Requests

**限流说明**:
- 平均速率: 5 req/min = 每 12 秒 1 单
- 突发容量: 10 单（短时间内可连续发送 10 单）
- 超过 10 单后，按 5/min 速率限制
- 适用场景: 支持偶尔的批量开仓需求

---

## 运维指南

### 查看日志

```bash
# SSH 连接
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# Nginx 访问日志
sudo tail -f /var/log/nginx/tv-okx-access.log

# Nginx 错误日志
sudo tail -f /var/log/nginx/tv-okx-error.log

# Docker 容器日志
docker logs -f tw168-tv-okx-1
docker logs -f tw168-tv-router-1

# 过滤特定端点的访问
sudo grep "/manual/signal" /var/log/nginx/tv-okx-access.log
```

---

### 健康检查脚本

```bash
# 远程服务器执行
cat > ~/check_service.sh << 'EOF'
#!/bin/bash
echo "=== Nginx 状态 ==="
sudo systemctl is-active nginx

echo -e "\n=== Docker 容器 ==="
docker ps --filter "name=tw168" --format "{{.Names}}: {{.Status}}"

echo -e "\n=== 端口监听 ==="
sudo ss -tlnp | grep -E ':(443|127.0.0.1:800)'

echo -e "\n=== HTTPS 健康检查 ==="
curl -sf https://3-38-98-169.nip.io/health || echo "❌ 健康检查失败"

echo -e "\n=== 证书有效期 ==="
sudo certbot certificates | grep "Expiry Date"
EOF

chmod +x ~/check_service.sh
~/check_service.sh
```

---

### 修改 BasicAuth 密码

```bash
# SSH 连接到远程服务器
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# 重置密码
sudo htpasswd /etc/nginx/.htpasswd trader
# 输入新密码

# 重载 Nginx
sudo systemctl reload nginx
```

---

### SSL 证书续期

证书已配置自动续期（通过 certbot.timer），无需手动干预。

**检查自动续期状态**:
```bash
# 远程执行
sudo systemctl status certbot.timer

# 手动测试续期
sudo certbot renew --dry-run
```

**证书过期时间**: 2026-04-02（自动续期会在过期前 30 天触发）

---

### 更新 Docker 配置

如果需要修改 docker-compose.yml：

```bash
# SSH 连接
cd ~/tw168

# 编辑配置
nano docker-compose.yml

# 重启容器
docker compose down
docker compose up -d

# 验证
docker ps
```

**重要**: 确保端口绑定始终使用 `127.0.0.1:8000:8000`，不要改为 `0.0.0.0`。

---

## 故障排查

### 问题 1: 无法访问 HTTPS

**检查项**:
```bash
# 1. Nginx 是否运行
sudo systemctl status nginx

# 2. 证书是否存在
sudo ls -la /etc/letsencrypt/live/3-38-98-169.nip.io/

# 3. 443 端口是否监听
sudo ss -tlnp | grep :443

# 4. Lightsail 防火墙是否开放 443
# 登录 AWS Console 检查
```

---

### 问题 2: 401 Unauthorized

**原因**: BasicAuth 凭据错误

**解决**:
```bash
# 验证凭据
curl -v -u trader:TW168Trading!2026 https://3-38-98-169.nip.io/metrics

# 重置密码
ssh ubuntu@3.38.98.169 "sudo htpasswd /etc/nginx/.htpasswd trader"
```

---

### 问题 3: 502 Bad Gateway

**原因**: 后端容器未运行或崩溃

**解决**:
```bash
# 检查容器状态
docker ps

# 重启容器
docker compose down && docker compose up -d

# 查看容器日志
docker logs tw168-tv-okx-1 --tail 50
```

---

### 问题 4: 429 Too Many Requests

**原因**: 超出限流限制

**临时解决**（仅调试用）:
```bash
# 编辑 Nginx 配置
sudo nano /etc/nginx/sites-available/tv-okx

# 修改限流参数（例如将 2r/m 改为 10r/m）
# limit_req_zone $binary_remote_addr zone=signal_limit:10m rate=10r/m;

# 重载配置
sudo nginx -t && sudo systemctl reload nginx
```

---

## 与本地 UI 集成

更新本地脚本使用 HTTPS 端点：

```python
# send_manual_signal.py
import requests
from requests.auth import HTTPBasicAuth

API_URL = "https://3-38-98-169.nip.io/manual/signal"
BASIC_AUTH_USER = "trader"
BASIC_AUTH_PASS = "TW168Trading!2026"
ADMIN_KEY = "your-secret-from-remote-env"

response = requests.post(
    API_URL,
    auth=HTTPBasicAuth(BASIC_AUTH_USER, BASIC_AUTH_PASS),
    json={
        "instId": "BTC-USDT-SWAP",
        "tf": "15m",
        "side": "buy",
        "admin_key": ADMIN_KEY,
    },
    timeout=10,
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
```

---

## 配置文件位置

| 文件 | 路径 |
|-----|------|
| Nginx 配置 | `/etc/nginx/sites-available/tv-okx` |
| BasicAuth 密码 | `/etc/nginx/.htpasswd` |
| SSL 证书 | `/etc/letsencrypt/live/3-38-98-169.nip.io/` |
| Docker Compose | `~/tw168/docker-compose.yml` |
| 应用配置 | `~/tw168/.env` |
| Nginx 日志 | `/var/log/nginx/tv-okx-*.log` |

---

## 备份文件

配置已自动备份到：
- `/etc/nginx/sites-available/tv-okx.bak.YYYYMMDD_HHMMSS`

查看所有备份：
```bash
ssh ubuntu@3.38.98.169 "ls -lt /etc/nginx/sites-available/*.bak*"
```

---

## 安全建议

### ✅ 已实施
- 强制 HTTPS
- BasicAuth 双重验证
- 端口仅内网访问
- 限流保护
- 安全头（HSTS, X-Frame-Options）

### 🔐 可选加固（未来）
- [ ] 启用 Fail2Ban（防暴力破解）
- [ ] 配置 WAF（Web Application Firewall）
- [ ] 添加 IP 地理位置限制（仅允许特定国家）
- [ ] 设置告警通知（证书过期、服务down）

---

## 性能监控

### 当前配置
- Keepalive: 16 connections
- Worker connections: 默认（768）
- Gzip: 未启用（JSON 响应较小）

### 如需优化
```bash
# 编辑 Nginx 主配置
sudo nano /etc/nginx/nginx.conf

# 添加
worker_processes auto;
worker_connections 2048;

gzip on;
gzip_types application/json;

sudo systemctl reload nginx
```

---

## 总结

### ✅ 实现的目标
1. ✅ 本地可通过 HTTPS 直接调用远程交易服务
2. ✅ 不使用 SSH 隧道
3. ✅ 长期稳定（证书自动续期、容器自动重启）
4. ✅ 安全可控（三层安全防护 + 限流）
5. ✅ 动态 IP 友好（BasicAuth 而非 IP 白名单）

### 🎯 安全等级
- 传输加密: ✅ TLS 1.2/1.3
- 身份验证: ✅ BasicAuth + admin_key
- 网络隔离: ✅ 端口仅本地可访问
- 防滥用: ✅ 限流保护
- 审计日志: ✅ Nginx 访问日志

### 📊 稳定性
- 服务自启: ✅ systemd (Nginx) + Docker restart policy
- 证书续期: ✅ 自动（certbot.timer）
- 健康检查: ✅ Nginx upstream health check

---

**下一步建议**: 将 BasicAuth 凭据和 ADMIN_KEY 安全保存到密码管理器（如 1Password, Bitwarden）。
