# Nginx 反向代理部署指南

## 概述
使用 Nginx 作为反向代理，实现：
- ✅ HTTPS 加密（Let's Encrypt 免费证书）
- ✅ IP 白名单（只允许指定 IP 访问）
- ✅ 隐藏后端端口（8000 仅本地可访问）
- ✅ 限流保护（防止滥用）
- ✅ 自动证书续期

---

## 部署步骤

### 1. 获取本地公网 IP

```bash
# 本地执行
curl -4 ifconfig.me
# 输出示例: 203.0.113.100
```

记录此 IP，稍后配置白名单时使用。

### 2. 配置 Lightsail 防火墙

登录 [AWS Lightsail Console](https://lightsail.aws.amazon.com/) → 选择实例 → **Networking** 标签 → **Firewall**

**必须开放的端口：**
```
SSH       TCP   22      0.0.0.0/0         (已有)
HTTP      TCP   80      0.0.0.0/0         (Let's Encrypt 验证需要)
HTTPS     TCP   443     0.0.0.0/0         (公开访问)
```

**必须移除/不添加的端口：**
```
❌ Custom TCP 8000  (不要开放，仅本地访问)
```

### 3. 上传配置脚本到远程服务器

```bash
# 本地执行
cd /home/fordxx/perp-tools/_remote_tw168/tw168

# 上传脚本
scp -i ../../LightsailDefaultKey-ap-northeast-2.pem \
    setup_nginx_proxy.sh \
    ubuntu@3.38.98.169:~/
```

### 4. 编辑配置脚本

```bash
# SSH 连接到远程
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169

# 编辑配置参数
nano ~/setup_nginx_proxy.sh
```

**修改以下三行：**
```bash
YOUR_PUBLIC_IP="203.0.113.100"  # 改为步骤 1 获取的 IP
DOMAIN="3-38-98-169.nip.io"     # 保持不变（或替换为自己的域名）
EMAIL="your-email@example.com"  # 改为你的邮箱
```

保存并退出（Ctrl+X, Y, Enter）

### 5. 运行配置脚本

```bash
# 远程执行
chmod +x ~/setup_nginx_proxy.sh
sudo ~/setup_nginx_proxy.sh
```

**预期输出：**
```
[1/6] 检查并安装依赖...
[2/6] 创建 Nginx 配置文件...
[3/6] 启用站点配置...
[4/6] 测试 Nginx 配置...
nginx: configuration file /etc/nginx/nginx.conf test is successful
[5/6] 重启 Nginx...
[6/6] 获取 SSL 证书...
✅ SSL 证书获取成功！
```

### 6. 重启 Docker 容器（应用新的端口绑定）

```bash
# 远程执行
cd ~/tw168  # 或你的项目路径
docker-compose down
docker-compose up -d

# 验证容器运行
docker ps | grep tv-okx
# 应显示: 127.0.0.1:8000->8000/tcp (不是 0.0.0.0:8000)
```

### 7. 验证配置

```bash
# ========== 远程服务器测试 ==========
# 1. 检查 Nginx 运行
sudo systemctl status nginx

# 2. 检查端口监听
ss -lntp | grep -E ':(80|443|8000)'
# 预期:
#   *:80    LISTEN  (nginx)
#   *:443   LISTEN  (nginx)
#   127.0.0.1:8000  LISTEN  (docker-proxy)

# 3. 本地健康检查
curl http://127.0.0.1:8000/health
# 应返回: {"status": "ok", ...}

# 4. 通过 Nginx 访问
curl https://3-38-98-169.nip.io/health
# 应返回: {"status": "ok", ...}

# ========== 本地机器测试 ==========
# 5. HTTPS 健康检查
curl https://3-38-98-169.nip.io/health

# 6. 测试手动信号
curl -X POST https://3-38-98-169.nip.io/manual/signal \
  -H "Content-Type: application/json" \
  -d '{
    "instId": "BTC-USDT-SWAP",
    "tf": "15m",
    "side": "buy",
    "admin_key": "your-admin-key-from-env"
  }'
```

---

## 运维指南

### 查看日志

```bash
# Nginx 访问日志
sudo tail -f /var/log/nginx/trading-api-access.log

# Nginx 错误日志
sudo tail -f /var/log/nginx/trading-api-error.log

# Docker 容器日志
docker logs -f tw168-tv-okx-1

# 过滤特定 IP 的访问
sudo grep "203.0.113.100" /var/log/nginx/trading-api-access.log
```

### 更新白名单 IP

```bash
# 远程执行
sudo nano /etc/nginx/sites-available/trading-api

# 找到以下行并修改 IP
#   allow 203.0.113.100;

# 添加多个 IP（每行一个）
#   allow 203.0.113.100;
#   allow 198.51.100.50;
#   deny all;

# 测试配置
sudo nginx -t

# 重载配置（无需重启，不影响现有连接）
sudo systemctl reload nginx
```

### 证书续期

证书自动续期已配置（通过 systemd timer），手动检查：

```bash
# 检查自动续期任务
sudo systemctl status certbot.timer

# 手动测试续期（dry-run）
sudo certbot renew --dry-run

# 强制续期
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

### 健康检查脚本

```bash
# 创建监控脚本
cat > ~/check_nginx_health.sh << 'EOF'
#!/bin/bash
set -euo pipefail

echo "=== Nginx 状态 ==="
sudo systemctl is-active nginx || echo "❌ Nginx 未运行"

echo -e "\n=== 证书有效期 ==="
sudo certbot certificates 2>/dev/null | grep "Expiry Date" || echo "未找到证书"

echo -e "\n=== 端口监听 ==="
ss -lntp | grep -E ':(80|443|8000)' || echo "无端口监听"

echo -e "\n=== Docker 容器 ==="
docker ps --filter "name=tv-okx" --format "{{.Names}}: {{.Status}}"

echo -e "\n=== 内部健康检查 ==="
if curl -sf http://127.0.0.1:8000/health > /dev/null; then
    echo "✅ 后端健康"
else
    echo "❌ 后端异常"
fi

echo -e "\n=== HTTPS 访问测试 ==="
if curl -sf https://3-38-98-169.nip.io/health > /dev/null; then
    echo "✅ HTTPS 正常"
else
    echo "❌ HTTPS 异常"
fi

echo -e "\n=== 最近 10 条错误日志 ==="
sudo tail -10 /var/log/nginx/trading-api-error.log 2>/dev/null || echo "无错误日志"
EOF

chmod +x ~/check_nginx_health.sh
```

运行检查：
```bash
~/check_nginx_health.sh
```

---

## 故障排查

### 问题 1: SSL 证书获取失败

**症状：** certbot 报错 "Failed to renew certificate"

**排查：**
```bash
# 1. 检查域名解析
host 3-38-98-169.nip.io
# 应指向 3.38.98.169

# 2. 检查 80 端口可访问
curl -I http://3-38-98-169.nip.io

# 3. 检查 Nginx 配置
sudo nginx -t

# 4. 手动获取证书（查看详细错误）
sudo certbot --nginx -d 3-38-98-169.nip.io --email your@email.com
```

**常见原因：**
- Lightsail 防火墙未开放 80 端口
- 域名解析错误
- Nginx 未运行

### 问题 2: 403 Forbidden

**症状：** 访问 `https://3-38-98-169.nip.io/health` 返回 403

**排查：**
```bash
# 1. 检查你的公网 IP
curl ifconfig.me

# 2. 检查 Nginx 白名单配置
sudo grep "allow" /etc/nginx/sites-available/trading-api

# 3. 查看错误日志
sudo tail -20 /var/log/nginx/trading-api-error.log
```

**解决：**
- 更新 Nginx 配置中的白名单 IP
- 如果使用 VPN，确保添加 VPN 出口 IP

### 问题 3: 502 Bad Gateway

**症状：** Nginx 正常但返回 502

**排查：**
```bash
# 1. 检查后端容器
docker ps | grep tv-okx

# 2. 检查后端健康
curl http://127.0.0.1:8000/health

# 3. 检查端口监听
ss -lntp | grep 8000
# 必须是 127.0.0.1:8000，不是 0.0.0.0:8000 也不行（如果配置错误）

# 4. 查看容器日志
docker logs tw168-tv-okx-1 --tail 50
```

**常见原因：**
- Docker 容器未运行
- 容器端口绑定错误
- 应用崩溃

### 问题 4: 从其他设备无法访问

**症状：** 手机/其他电脑访问报错

**原因：** IP 白名单只允许配置的 IP

**解决方案：**

**方案 A（推荐）：** 添加 IP 到白名单
```bash
sudo nano /etc/nginx/sites-available/trading-api
# 添加行: allow <新设备的公网IP>;
sudo nginx -t && sudo systemctl reload nginx
```

**方案 B（临时测试）：** 临时放开限制
```bash
# 备份配置
sudo cp /etc/nginx/sites-available/trading-api{,.bak}

# 注释掉 IP 限制（仅测试用！）
sudo sed -i 's/allow /# allow /' /etc/nginx/sites-available/trading-api
sudo sed -i 's/deny all/# deny all/' /etc/nginx/sites-available/trading-api

# 重载
sudo nginx -t && sudo systemctl reload nginx

# 测试完成后恢复
sudo mv /etc/nginx/sites-available/trading-api{.bak,}
sudo systemctl reload nginx
```

---

## 性能优化

### 1. 启用 Gzip 压缩

```bash
sudo nano /etc/nginx/nginx.conf

# 在 http 块中添加
gzip on;
gzip_types application/json text/plain;
gzip_min_length 1000;

sudo nginx -t && sudo systemctl reload nginx
```

### 2. 调整 Nginx 连接数

```bash
sudo nano /etc/nginx/nginx.conf

# 修改
worker_processes auto;
worker_connections 2048;

sudo systemctl reload nginx
```

---

## 安全加固（可选）

### 1. 添加 BasicAuth（双重验证）

```bash
# 安装工具
sudo apt install -y apache2-utils

# 创建密码文件
sudo htpasswd -c /etc/nginx/.htpasswd trader
# 输入密码（例如: MySecurePass123!）

# 修改 Nginx 配置
sudo nano /etc/nginx/sites-available/trading-api

# 在 location /manual/signal 块中添加
#     auth_basic "Trading API";
#     auth_basic_user_file /etc/nginx/.htpasswd;

sudo nginx -t && sudo systemctl reload nginx
```

使用时需要添加认证：
```bash
curl -u trader:MySecurePass123! \
  -X POST https://3-38-98-169.nip.io/manual/signal -d '{...}'
```

### 2. 启用 Fail2Ban（防暴力破解）

```bash
sudo apt install -y fail2ban

# 创建规则
sudo nano /etc/fail2ban/jail.local

# 添加
[nginx-trading]
enabled = true
port = 443
filter = nginx-trading
logpath = /var/log/nginx/trading-api-access.log
maxretry = 5
bantime = 3600

# 创建过滤器
sudo nano /etc/fail2ban/filter.d/nginx-trading.conf

# 添加
[Definition]
failregex = ^<HOST> .* "(POST|GET) /manual/signal .*" 403
ignoreregex =

sudo systemctl restart fail2ban
```

---

## 完整验证 Checklist

| 步骤 | 命令 | 预期结果 | 失败排查 |
|-----|------|---------|---------|
| 1️⃣ Nginx 运行 | `sudo systemctl status nginx` | active (running) | `sudo systemctl start nginx` |
| 2️⃣ 证书存在 | `sudo ls /etc/letsencrypt/live/3-38-98-169.nip.io/` | 看到 fullchain.pem | 重新运行 setup 脚本 |
| 3️⃣ 端口监听 | `ss -lntp \| grep ':443'` | nginx LISTEN | 检查配置 |
| 4️⃣ Docker 运行 | `docker ps \| grep tv-okx` | UP, 127.0.0.1:8000 | `docker-compose up -d` |
| 5️⃣ 后端健康 | `curl http://127.0.0.1:8000/health` | {"status": "ok"} | 检查容器日志 |
| 6️⃣ Nginx 代理 | `curl https://3-38-98-169.nip.io/health` | {"status": "ok"} | 检查 Nginx 日志 |
| 7️⃣ IP 限制 | 从其他 IP 访问 | 403 Forbidden | 正常（白名单生效） |
| 8️⃣ 真实信号 | `curl -X POST https://.../manual/signal -d '{...}'` | 200 OK | 检查 admin_key |

---

## 与现有 UI 集成

更新你的本地 UI 代码，使用 HTTPS 端点：

```python
# send_manual_signal.py
import requests

API_URL = "https://3-38-98-169.nip.io/manual/signal"
ADMIN_KEY = "your-secret-from-env"

response = requests.post(
    API_URL,
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

## 总结

**安全性：**
- ✅ TLS 1.2/1.3 加密
- ✅ IP 白名单（应用层）
- ✅ admin_key 验证（应用层）
- ✅ 限流保护（10 req/s）
- ✅ 8000 端口仅本地可访问

**稳定性：**
- ✅ Nginx upstream 健康检查
- ✅ Docker restart: unless-stopped
- ✅ 证书自动续期
- ✅ Systemd 服务自启动

**维护成本：**
- ✅ 零成本证书（Let's Encrypt）
- ✅ 自动续期（无需人工干预）
- ✅ 日志轮转（自动清理）

下一步建议：配置监控告警（可选，见健康检查脚本章节）。
