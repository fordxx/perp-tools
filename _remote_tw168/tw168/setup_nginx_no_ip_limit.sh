#!/bin/bash
# Nginx 反向代理配置脚本（动态 IP 版）
# 安全策略: BasicAuth + admin_key + 限流，不依赖 IP 白名单

set -euo pipefail

# ========== 配置区 ==========
DOMAIN="3-38-98-169.nip.io"     # 使用 nip.io 或你的域名
EMAIL="your-email@example.com"  # Let's Encrypt 证书邮箱
BASIC_AUTH_USER="trader"        # BasicAuth 用户名
BASIC_AUTH_PASS=""              # BasicAuth 密码（留空则脚本会提示输入）

# ========== 检查权限 ==========
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# ========== 安装依赖 ==========
echo "[1/7] 检查并安装依赖..."
apt-get update
apt-get install -y nginx certbot python3-certbot-nginx apache2-utils

# ========== 创建 BasicAuth 密码 ==========
echo "[2/7] 配置 BasicAuth..."
if [ -z "$BASIC_AUTH_PASS" ]; then
    echo "请为 BasicAuth 设置密码（此密码将用于访问 /manual/signal 端点）:"
    htpasswd -c /etc/nginx/.htpasswd "$BASIC_AUTH_USER"
else
    echo "$BASIC_AUTH_PASS" | htpasswd -ci /etc/nginx/.htpasswd "$BASIC_AUTH_USER"
fi

echo "✓ BasicAuth 用户名: $BASIC_AUTH_USER"

# ========== 创建 Nginx 配置 ==========
echo "[3/7] 创建 Nginx 配置文件..."
cat > /etc/nginx/sites-available/trading-api << 'NGINX_EOF'
# 限速配置（防止暴力破解和滥用）
limit_req_zone $binary_remote_addr zone=trading_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=signal_limit:10m rate=2r/m;  # 每分钟最多 2 次信号

# Upstream 定义
upstream trading_backend {
    server 127.0.0.1:8000 fail_timeout=10s max_fails=3;
    keepalive 32;
}

# HTTP → HTTPS 重定向
server {
    listen 80;
    listen [::]:80;
    server_name DOMAIN_PLACEHOLDER;

    # Let's Encrypt 验证路径
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # 其他请求重定向到 HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS 主配置
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name DOMAIN_PLACEHOLDER;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 日志
    access_log /var/log/nginx/trading-api-access.log;
    error_log /var/log/nginx/trading-api-error.log warn;

    # 健康检查端点（公开，不需要认证，轻量级限速）
    location = /health {
        limit_req zone=trading_limit burst=20 nodelay;
        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
        access_log off;  # 不记录健康检查日志
    }

    # Metrics 端点（需要 BasicAuth）
    location = /metrics {
        auth_basic "Metrics Access";
        auth_basic_user_file /etc/nginx/.htpasswd;

        limit_req zone=trading_limit burst=10 nodelay;
        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # 手动信号端点（双重保护：BasicAuth + 严格限流）
    location /manual/signal {
        # 第一层：BasicAuth（防止未授权访问）
        auth_basic "Trading Signal API";
        auth_basic_user_file /etc/nginx/.htpasswd;

        # 第二层：严格限流（每分钟最多 2 次，突发最多 5 次）
        limit_req zone=signal_limit burst=5 nodelay;
        limit_req_status 429;

        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # 超时配置
        proxy_connect_timeout 10s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;

        # 请求体大小限制
        client_max_body_size 1m;
    }

    # WebSocket 支持（如果需要，也需要 BasicAuth）
    location /ws {
        auth_basic "WebSocket Access";
        auth_basic_user_file /etc/nginx/.htpasswd;

        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # 拒绝其他所有路径
    location / {
        return 404 "Endpoint not found";
    }
}
NGINX_EOF

# 替换配置中的占位符
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" /etc/nginx/sites-available/trading-api

# ========== 启用站点 ==========
echo "[4/7] 启用站点配置..."
ln -sf /etc/nginx/sites-available/trading-api /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # 移除默认站点

# ========== 测试配置 ==========
echo "[5/7] 测试 Nginx 配置..."
nginx -t

# ========== 重启 Nginx ==========
echo "[6/7] 重启 Nginx..."
systemctl restart nginx
systemctl enable nginx

# ========== 获取 Let's Encrypt 证书 ==========
echo "[7/7] 获取 SSL 证书..."

# 先测试域名解析
CURRENT_IP=$(curl -s ifconfig.me)
echo "当前服务器公网 IP: $CURRENT_IP"
echo "配置的域名: $DOMAIN"

if host "${DOMAIN}" > /dev/null 2>&1; then
    RESOLVED_IP=$(host "${DOMAIN}" | grep "has address" | awk '{print $4}' | head -1)
    if [ "$RESOLVED_IP" = "$CURRENT_IP" ]; then
        echo "✓ 域名解析正确: ${DOMAIN} → ${CURRENT_IP}"
    else
        echo "⚠ 警告: 域名解析不匹配"
        echo "  解析到: $RESOLVED_IP"
        echo "  期望: $CURRENT_IP"
    fi
else
    echo "⚠ 警告: 无法解析域名 ${DOMAIN}"
fi

# 获取证书
if certbot --nginx -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --non-interactive; then
    echo "✅ SSL 证书获取成功！"
else
    echo "❌ SSL 证书获取失败"
    echo "可能原因:"
    echo "  1. 域名未正确指向 $CURRENT_IP"
    echo "  2. 防火墙未开放 80 端口"
    echo ""
    echo "手动获取证书命令:"
    echo "  sudo certbot --nginx -d ${DOMAIN} --email ${EMAIL}"
    exit 1
fi

# ========== 配置自动续期 ==========
echo "配置证书自动续期..."
systemctl enable certbot.timer
systemctl start certbot.timer

# ========== 完成 ==========
echo ""
echo "=========================================="
echo "✅ Nginx 配置完成！"
echo "=========================================="
echo ""
echo "访问地址: https://${DOMAIN}"
echo "BasicAuth 用户名: ${BASIC_AUTH_USER}"
echo "BasicAuth 密码: (你设置的密码)"
echo ""
echo "验证命令:"
echo "  # 健康检查（无需认证）"
echo "  curl https://${DOMAIN}/health"
echo ""
echo "  # 手动信号（需要 BasicAuth + admin_key）"
echo "  curl -u ${BASIC_AUTH_USER}:YOUR_PASSWORD \\"
echo "    -X POST https://${DOMAIN}/manual/signal \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{"
echo "      \"instId\": \"BTC-USDT-SWAP\","
echo "      \"tf\": \"15m\","
echo "      \"side\": \"buy\","
echo "      \"admin_key\": \"YOUR_ADMIN_KEY\""
echo "    }'"
echo ""
echo "查看日志:"
echo "  sudo tail -f /var/log/nginx/trading-api-error.log"
echo ""
echo "修改 BasicAuth 密码:"
echo "  sudo htpasswd /etc/nginx/.htpasswd ${BASIC_AUTH_USER}"
echo "  sudo systemctl reload nginx"
echo ""
