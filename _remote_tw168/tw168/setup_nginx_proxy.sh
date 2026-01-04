#!/bin/bash
# Nginx 反向代理配置脚本
# 用途: 配置 HTTPS + IP 白名单 + 反向代理到 Docker 容器

set -euo pipefail

# ========== 配置区 ==========
YOUR_PUBLIC_IP="203.0.113.100"  # 替换为你的公网 IP (运行 curl ifconfig.me 获取)
DOMAIN="3-38-98-169.nip.io"     # 使用 nip.io 免费通配符 DNS，或替换为你的域名
EMAIL="your-email@example.com"  # Let's Encrypt 证书邮箱

# ========== 检查权限 ==========
if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本"
    exit 1
fi

# ========== 安装依赖 ==========
echo "[1/6] 检查并安装依赖..."
apt-get update
apt-get install -y nginx certbot python3-certbot-nginx

# ========== 创建 Nginx 配置 ==========
echo "[2/6] 创建 Nginx 配置文件..."
cat > /etc/nginx/sites-available/trading-api << 'NGINX_EOF'
# 限速配置（防止滥用）
limit_req_zone $binary_remote_addr zone=trading_limit:10m rate=10r/s;

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

    # SSL 配置（certbot 会自动填充证书路径）
    ssl_certificate /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/DOMAIN_PLACEHOLDER/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;

    # 日志
    access_log /var/log/nginx/trading-api-access.log;
    error_log /var/log/nginx/trading-api-error.log warn;

    # IP 白名单（只允许你的 IP）
    allow IP_PLACEHOLDER;
    deny all;

    # 健康检查端点（不限速）
    location = /health {
        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
        access_log off;  # 不记录健康检查日志
    }

    # Metrics 端点
    location = /metrics {
        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_read_timeout 10s;
    }

    # 手动信号端点（限速保护）
    location /manual/signal {
        limit_req zone=trading_limit burst=5 nodelay;

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

    # WebSocket 支持（如果未来需要）
    location /ws {
        proxy_pass http://trading_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }

    # 拒绝其他所有路径
    location / {
        return 404;
    }
}
NGINX_EOF

# 替换配置中的占位符
sed -i "s/DOMAIN_PLACEHOLDER/${DOMAIN}/g" /etc/nginx/sites-available/trading-api
sed -i "s/IP_PLACEHOLDER/${YOUR_PUBLIC_IP}/g" /etc/nginx/sites-available/trading-api

# ========== 启用站点 ==========
echo "[3/6] 启用站点配置..."
ln -sf /etc/nginx/sites-available/trading-api /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # 移除默认站点

# ========== 测试配置 ==========
echo "[4/6] 测试 Nginx 配置..."
nginx -t

# ========== 临时启动 Nginx（用于获取证书）==========
echo "[5/6] 重启 Nginx..."
systemctl restart nginx
systemctl enable nginx

# ========== 获取 Let's Encrypt 证书 ==========
echo "[6/6] 获取 SSL 证书..."
echo "注意: Let's Encrypt 需要域名能通过公网访问到 80 端口"
echo "如果使用 nip.io，确保 Lightsail 防火墙已开放 80/443"
echo ""

# 先测试域名解析
if host "${DOMAIN}" > /dev/null 2>&1; then
    echo "✓ 域名解析正常: ${DOMAIN}"
else
    echo "⚠ 警告: 域名 ${DOMAIN} 解析失败"
    echo "请确保:"
    echo "  1. Lightsail 防火墙开放了 80/443 端口"
    echo "  2. 域名正确指向 $(curl -s ifconfig.me)"
    read -p "继续获取证书? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "已取消。手动获取证书命令:"
        echo "  sudo certbot --nginx -d ${DOMAIN} --email ${EMAIL} --agree-tos --non-interactive"
        exit 0
    fi
fi

# 获取证书
if certbot --nginx -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --non-interactive; then
    echo "✅ SSL 证书获取成功！"
else
    echo "❌ SSL 证书获取失败"
    echo "可能原因:"
    echo "  1. 域名未指向正确 IP"
    echo "  2. 防火墙未开放 80 端口"
    echo "  3. Nginx 未正常运行"
    echo ""
    echo "手动排查命令:"
    echo "  sudo nginx -t"
    echo "  sudo systemctl status nginx"
    echo "  curl http://${DOMAIN}/.well-known/acme-challenge/test"
    exit 1
fi

# ========== 配置自动续期 ==========
echo "配置证书自动续期..."
systemctl enable certbot.timer
systemctl start certbot.timer

# ========== 验证 ==========
echo ""
echo "=========================================="
echo "✅ Nginx 配置完成！"
echo "=========================================="
echo ""
echo "访问地址: https://${DOMAIN}"
echo ""
echo "验证命令:"
echo "  curl https://${DOMAIN}/health"
echo ""
echo "后续步骤:"
echo "  1. 确保 Docker 容器运行: docker ps | grep tv-okx"
echo "  2. 本地测试: curl https://${DOMAIN}/health"
echo "  3. 查看日志: tail -f /var/log/nginx/trading-api-error.log"
echo ""
echo "修改白名单 IP:"
echo "  sudo nano /etc/nginx/sites-available/trading-api"
echo "  # 修改 'allow IP_PLACEHOLDER;' 行"
echo "  sudo nginx -t && sudo systemctl reload nginx"
echo ""
