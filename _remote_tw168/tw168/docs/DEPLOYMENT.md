# TW168 部署指南

本文档提供 TW168 系统的完整部署指南，包括本地开发、测试环境和生产环境部署。

## 📋 目录

- [环境要求](#环境要求)
- [本地开发部署](#本地开发部署)
- [Docker 部署](#docker-部署)
- [生产环境部署](#生产环境部署)
- [配置说明](#配置说明)
- [升级指南](#升级指南)
- [备份与恢复](#备份与恢复)

## 环境要求

### 硬件要求

**最低配置:**
- CPU: 1 核
- 内存: 512 MB
- 磁盘: 1 GB

**推荐配置:**
- CPU: 2 核+
- 内存: 2 GB+
- 磁盘: 10 GB+

### 软件要求

- **操作系统:** Linux (Ubuntu 20.04+推荐), macOS, Windows WSL
- **Python:** 3.11 或更高版本
- **Docker:** 20.10+ (可选)
- **Docker Compose:** 2.0+ (可选)
- **Git:** 2.0+

### 网络要求

- 公网 IP 或域名 (用于接收 TradingView Webhook)
- 开放端口 8000 (或自定义端口)
- 能够访问 OKX API: `https://www.okx.com`
- 能够访问 Lighter API: `https://api.lighter.xyz`

## 本地开发部署

### 1. 克隆项目

```bash
git clone <repository-url>
cd tw168
```

### 2. 创建虚拟环境

```bash
# 使用 venv
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 或使用 conda
conda create -n tw168 python=3.11
conda activate tw168
```

### 3. 安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置文件
nano .env  # 或使用其他编辑器
```

**必须配置的项:**
```bash
TV_WEBHOOK_SECRET=生成一个强随机字符串
EXCHANGE=okx
TRADING_ENABLED=false  # 测试时使用 false
SYMBOL_ALLOWLIST=ETH-USDT-SWAP,BTC-USDT-SWAP
```

**OKX API 配置:**
```bash
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_API_PASSPHRASE=your_passphrase
```

### 5. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**参数说明:**
- `--host 0.0.0.0` - 监听所有网络接口
- `--port 8000` - 端口号
- `--reload` - 代码修改自动重载 (仅开发环境)

### 6. 验证服务

```bash
# 健康检查
curl http://localhost:8000/health

# 查看欢迎信息
curl http://localhost:8000/
```

## Docker 部署

### 1. 准备配置文件

```bash
# 复制示例配置
cp .env.example .env

# 编辑配置
nano .env
```

### 2. 构建镜像

```bash
docker compose build
```

### 3. 启动服务

```bash
# 后台运行
docker compose up -d

# 前台运行 (查看日志)
docker compose up
```

### 4. 查看日志

```bash
# 实时日志
docker compose logs -f

# 最近 100 行
docker compose logs --tail=100

# 特定服务
docker compose logs -f app
```

### 5. 停止服务

```bash
# 停止容器
docker compose stop

# 停止并删除容器
docker compose down

# 停止并删除容器和卷
docker compose down -v
```

### 6. 重启服务

```bash
docker compose restart
```

## 生产环境部署

### 方案一: Docker 部署 (推荐)

#### 1. 服务器准备

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 安装 Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker --version
docker-compose --version
```

#### 2. 创建工作目录

```bash
# 创建应用目录
sudo mkdir -p /opt/tw168
cd /opt/tw168

# 克隆项目
git clone <repository-url> .

# 设置权限
sudo chown -R $USER:$USER /opt/tw168
```

#### 3. 配置环境

```bash
# 复制配置
cp .env.example .env

# 编辑配置 (重要!)
nano .env
```

**生产环境必须修改:**
```bash
TRADING_ENABLED=true  # 启用实盘交易
TV_WEBHOOK_SECRET=<生成强随机密钥>
OKX_API_KEY=<你的API密钥>
OKX_API_SECRET=<你的API密钥>
OKX_API_PASSPHRASE=<你的API密码>
```

#### 4. 启动服务

```bash
# 构建并启动
docker compose up -d --build

# 查看状态
docker compose ps

# 查看日志
docker compose logs -f
```

#### 5. 配置开机自启

```bash
# 创建 systemd 服务文件
sudo nano /etc/systemd/system/tw168.service
```

```ini
[Unit]
Description=TW168 Trading Service
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/tw168
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
# 启用服务
sudo systemctl enable tw168
sudo systemctl start tw168
sudo systemctl status tw168
```

### 方案二: 系统服务部署

#### 1. 安装 Python 和依赖

```bash
sudo apt install python3.11 python3.11-venv -y
```

#### 2. 创建服务用户

```bash
sudo useradd -r -s /bin/false tw168
```

#### 3. 设置项目

```bash
sudo mkdir -p /opt/tw168
cd /opt/tw168
sudo git clone <repository-url> .

# 创建虚拟环境
sudo python3.11 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt

# 配置环境
sudo cp .env.example .env
sudo nano .env

# 设置权限
sudo chown -R tw168:tw168 /opt/tw168
```

#### 4. 创建 Systemd 服务

```bash
sudo nano /etc/systemd/system/tw168.service
```

```ini
[Unit]
Description=TW168 Trading Service
After=network.target

[Service]
Type=simple
User=tw168
Group=tw168
WorkingDirectory=/opt/tw168
Environment="PATH=/opt/tw168/.venv/bin"
ExecStart=/opt/tw168/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable tw168
sudo systemctl start tw168
sudo systemctl status tw168
```

### 配置反向代理 (Nginx)

#### 1. 安装 Nginx

```bash
sudo apt install nginx -y
```

#### 2. 配置站点

```bash
sudo nano /etc/nginx/sites-available/tw168
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# 启用站点
sudo ln -s /etc/nginx/sites-available/tw168 /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 3. 配置 HTTPS (Let's Encrypt)

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx -y

# 获取证书
sudo certbot --nginx -d your-domain.com

# 自动续期
sudo systemctl enable certbot.timer
```

### 配置防火墙

```bash
# UFW 防火墙
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp  # SSH
sudo ufw enable
```

## 配置说明

### 关键配置项

#### 交易开关

```bash
# 模拟交易 (安全)
TRADING_ENABLED=false

# 实盘交易 (风险)
TRADING_ENABLED=true
```

#### 交易对白名单

```bash
# 单个交易对
SYMBOL_ALLOWLIST=ETH-USDT-SWAP

# 多个交易对
SYMBOL_ALLOWLIST=ETH-USDT-SWAP,BTC-USDT-SWAP,SOL-USDT-SWAP
```

#### 风险控制

```bash
# 每笔交易风险金额 (推荐)
RISK_PER_TRADE_USDT=100

# 冷却时间 (秒)
COOLDOWN_SECONDS=120

# 方向控制
ENABLE_LONG=true
ENABLE_SHORT=true
```

### 配置验证

```bash
# 使用配置工具验证
python3 scripts/envctl.py --check

# 或手动测试
curl http://localhost:8000/health
```

## 升级指南

### Docker 升级

```bash
# 1. 备份配置
cp .env .env.backup

# 2. 拉取最新代码
git pull origin main

# 3. 停止服务
docker compose down

# 4. 重新构建
docker compose build --no-cache

# 5. 启动服务
docker compose up -d

# 6. 查看日志
docker compose logs -f
```

### 系统服务升级

```bash
# 1. 停止服务
sudo systemctl stop tw168

# 2. 备份
sudo cp /opt/tw168/.env /opt/tw168/.env.backup
sudo tar czf /tmp/tw168-backup-$(date +%Y%m%d).tar.gz /opt/tw168

# 3. 更新代码
cd /opt/tw168
sudo -u tw168 git pull origin main

# 4. 更新依赖
sudo -u tw168 .venv/bin/pip install -r requirements.txt --upgrade

# 5. 检查配置
diff .env.example .env

# 6. 重启服务
sudo systemctl start tw168
sudo systemctl status tw168
```

### 版本回滚

```bash
# Docker 回滚
git checkout <previous-commit>
docker compose down
docker compose up -d --build

# 系统服务回滚
sudo systemctl stop tw168
cd /opt/tw168
git checkout <previous-commit>
sudo -u tw168 .venv/bin/pip install -r requirements.txt
sudo systemctl start tw168
```

## 备份与恢复

### 备份

#### 配置文件备份

```bash
# 备份 .env
cp .env .env.backup-$(date +%Y%m%d)

# 或使用脚本
tar czf tw168-config-$(date +%Y%m%d).tar.gz .env
```

#### 日志备份

```bash
# 备份日志目录
tar czf tw168-logs-$(date +%Y%m%d).tar.gz logs/

# 轮转日志 (自动清理旧日志)
sudo logrotate -f /etc/logrotate.d/tw168
```

#### 完整备份

```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/tw168"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p $BACKUP_DIR

# 备份配置
cp .env $BACKUP_DIR/env-$DATE

# 备份日志
tar czf $BACKUP_DIR/logs-$DATE.tar.gz logs/

# 备份信号审计
if [ -d "logs/signals" ]; then
    tar czf $BACKUP_DIR/signals-$DATE.tar.gz logs/signals/
fi

echo "Backup completed: $BACKUP_DIR"
```

### 恢复

```bash
# 1. 停止服务
docker compose down
# 或 sudo systemctl stop tw168

# 2. 恢复配置
cp .env.backup .env

# 3. 恢复日志
tar xzf tw168-logs-YYYYMMDD.tar.gz

# 4. 启动服务
docker compose up -d
# 或 sudo systemctl start tw168
```

## 监控与日志

### 日志查看

```bash
# Docker 日志
docker compose logs -f --tail=100

# 系统服务日志
sudo journalctl -u tw168 -f

# 应用日志
tail -f /opt/tw168/tw168.log
```

### 健康检查

```bash
# 定期健康检查脚本
#!/bin/bash
# health_check.sh

if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "Service is healthy"
else
    echo "Service is down! Restarting..."
    docker compose restart
fi
```

```bash
# 添加到 crontab
crontab -e
```

```cron
# 每 5 分钟检查一次
*/5 * * * * /opt/tw168/health_check.sh
```

## 故障排查

### 服务无法启动

```bash
# 检查日志
docker compose logs
sudo journalctl -u tw168 -n 50

# 检查端口占用
sudo lsof -i :8000

# 检查配置
python3 -c "from app.config import SETTINGS; print(SETTINGS)"
```

### 无法接收 Webhook

```bash
# 检查防火墙
sudo ufw status

# 检查 Nginx
sudo nginx -t
sudo systemctl status nginx

# 测试 Webhook
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"secret":"your_secret","type":"ZONE","zone":"OVERSOLD","instId":"ETH-USDT-SWAP","tf":"15m"}'
```

更多故障排查，参考 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
