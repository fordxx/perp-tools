# PerpBot V2 生产环境部署指南

**目标**: 将 PerpBot V2 部署到生产环境，实现 24/7 稳定运行

---

## 📋 概览

本指南涵盖：
- Docker 容器化部署
- 监控系统配置 (Prometheus + Grafana)
- 告警系统配置 (Alertmanager)
- 日志管理
- 高可用性配置
- 安全最佳实践

---

## 🎯 部署架构

```
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer                         │
│                  (Nginx / HAProxy)                       │
└──────────────┬────────────────────────────┬─────────────┘
               │                            │
       ┌───────▼────────┐          ┌───────▼────────┐
       │  PerpBot Node 1 │          │  PerpBot Node 2 │
       │  (Active)       │          │  (Standby)      │
       └───────┬────────┘          └───────┬────────┘
               │                            │
               └─────────────┬──────────────┘
                             │
                    ┌────────▼────────┐
                    │    Redis        │
                    │  (Shared State) │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
    ┌─────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
    │ Prometheus │    │   Grafana   │   │ Alertmanager│
    └───────────┘    └─────────────┘   └─────────────┘
```

---

## 🚀 快速开始

### 单机部署 (推荐用于测试)

```bash
# 1. 克隆仓库
git clone https://github.com/fordxx/perp-tools.git
cd perp-tools

# 2. 配置环境变量
cp env.example .env
nano .env  # 填写 API 凭证

# 3. 启动所有服务
./deploy/scripts/start.sh

# 4. 验证部署
./deploy/scripts/health-check.sh
```

### 生产环境部署

参见下方详细步骤。

---

## 📦 部署步骤详解

### Step 1: 环境准备

#### 1.1 服务器要求

**最小配置** (测试环境):
- CPU: 2 核心
- 内存: 4GB
- 磁盘: 20GB SSD
- 网络: 稳定互联网连接

**推荐配置** (生产环境):
- CPU: 4+ 核心
- 内存: 8GB+
- 磁盘: 50GB+ SSD (RAID 1)
- 网络: 千兆网卡，< 50ms 延迟到主要交易所

**高可用配置**:
- 2+ 台服务器
- 负载均衡器
- 共享存储或分布式缓存

#### 1.2 软件依赖

```bash
# Ubuntu 20.04+
sudo apt-get update
sudo apt-get install -y docker.io docker-compose git

# CentOS 8+
sudo yum install -y docker docker-compose git

# 启动 Docker
sudo systemctl enable docker
sudo systemctl start docker

# 验证安装
docker --version  # 应显示 20.10+
docker compose version  # 应显示 2.0+
```

#### 1.3 网络配置

```bash
# 开放必要端口
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw allow 8000/tcp  # Web Dashboard
sudo ufw allow 3000/tcp  # Grafana
sudo ufw allow 9090/tcp  # Prometheus
sudo ufw enable

# 或使用 iptables
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables-save
```

### Step 2: 配置文件

#### 2.1 环境变量 (.env)

```bash
cp env.example .env
nano .env
```

**必填项**:
```bash
# OKX
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet  # ⚠️ 首次部署使用 testnet

# Hyperliquid
HYPERLIQUID_ACCOUNT_ADDRESS=your_address
HYPERLIQUID_PRIVATE_KEY=your_private_key
HYPERLIQUID_ENV=testnet

# Paradex (可选)
PARADEX_L2_PRIVATE_KEY=your_key
PARADEX_ACCOUNT_ADDRESS=your_address
PARADEX_ENV=testnet
```

**安全设置**:
```bash
# 设置文件权限
chmod 600 .env

# 验证不会被 Git 跟踪
git status .env  # 应显示 .env 被忽略
```

#### 2.2 交易配置 (config.yaml)

```yaml
# 资金管理
capital:
  initial_capital_usdt: 1000  # 初始资金
  max_position_size_usdt: 100  # 单笔最大仓位
  max_leverage: 3  # 最大杠杆

# 风控
risk:
  max_daily_loss_usdt: 50  # 每日最大亏损
  max_drawdown_percent: 5  # 最大回撤
  stop_loss_percent: 2  # 止损百分比

# 套利
arbitrage:
  min_profit_bps: 10  # 最小利润（基点）
  max_spread_bps: 100  # 最大价差
  execution_timeout_seconds: 10  # 执行超时

# 交易所
exchanges:
  - okx
  - hyperliquid
  # - paradex  # 可选

# 监控
monitoring:
  enabled: true
  prometheus_port: 9090
  metrics_interval_seconds: 15
```

### Step 3: 构建与启动

#### 3.1 构建 Docker 镜像

```bash
# 构建 PerpBot 镜像
docker compose build perpbot

# 验证镜像
docker images | grep perpbot
```

#### 3.2 启动服务

```bash
# 方式 1: 使用脚本（推荐）
./deploy/scripts/start.sh

# 方式 2: 手动启动
docker compose up -d

# 查看启动日志
docker compose logs -f perpbot
```

#### 3.3 验证部署

```bash
# 运行健康检查
./deploy/scripts/health-check.sh

# 预期输出:
# ✅ PerpBot:      HEALTHY
# ✅ Prometheus:   HEALTHY
# ✅ Grafana:      HEALTHY
# ✅ Redis:        HEALTHY
```

### Step 4: 监控配置

#### 4.1 访问 Grafana

```
URL: http://your-server-ip:3000
默认用户名: admin
默认密码: admin
```

**首次登录**:
1. 修改默认密码
2. 验证 Prometheus 数据源已连接
3. 打开 PerpBot Dashboard
4. 确认实时数据显示

#### 4.2 配置告警

编辑 `deploy/alertmanager/alertmanager.yml`:

```yaml
receivers:
  - name: 'telegram'
    telegram_configs:
      - bot_token: 'YOUR_BOT_TOKEN'
        chat_id: YOUR_CHAT_ID
        message: |
          🚨 {{ .GroupLabels.alertname }}
          {{ range .Alerts }}
          {{ .Annotations.description }}
          {{ end }}
```

重启 Alertmanager:
```bash
docker compose restart alertmanager
```

### Step 5: 日志配置

#### 5.1 配置日志轮转

```bash
# 复制 logrotate 配置
sudo cp deploy/logrotate/perpbot /etc/logrotate.d/perpbot

# 测试配置
sudo logrotate -d /etc/logrotate.d/perpbot

# 手动执行轮转
sudo logrotate -f /etc/logrotate.d/perpbot
```

#### 5.2 集中日志（可选）

使用 ELK Stack 或 Loki:

```yaml
# docker-compose.yml 添加
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"

  promtail:
    image: grafana/promtail:latest
    volumes:
      - ./logs:/var/log
      - ./deploy/promtail/config.yaml:/etc/promtail/config.yaml
```

---

## 🔒 安全加固

### 1. HTTPS 配置

使用 Let's Encrypt + Nginx:

```nginx
# /etc/nginx/sites-available/perpbot
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. 防火墙配置

```bash
# 只允许必要端口
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 3. 访问控制

```yaml
# docker-compose.yml
services:
  perpbot:
    environment:
      - ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
      - REQUIRE_AUTH=true
      - JWT_SECRET=your-secret-key
```

### 4. 密钥管理

使用环境变量或密钥管理系统:

```bash
# 使用 Docker Secrets
echo "your_api_key" | docker secret create okx_api_key -

# 在 docker-compose.yml 中引用
secrets:
  okx_api_key:
    external: true
```

---

## 📊 监控最佳实践

### 1. 关键指标

**必须监控**:
- 系统健康度 (target: > 90%)
- WebSocket 连接状态
- 订单成功率 (target: > 95%)
- 执行延迟 (target: < 200ms)
- 资金使用率 (alert: > 80%)

**推荐监控**:
- CPU/内存使用率
- 磁盘使用率
- 网络延迟
- 套利机会发现率
- PnL 趋势

### 2. 告警规则

**Critical 告警** (立即处理):
- 系统宕机
- WebSocket 全部断开
- 资金使用超过 90%
- 订单失败率 > 10%

**Warning 告警** (24 小时内处理):
- WebSocket 延迟 > 200ms
- 资金使用 > 80%
- 订单失败率 > 5%
- 套利机会过少

### 3. 告警渠道

优先级顺序:
1. Telegram (即时通知)
2. Email (详细报告)
3. PagerDuty (值班轮换)
4. Slack/Lark (团队协作)

---

## 🔄 高可用性配置

### 1. 主备模式

```yaml
# docker-compose.ha.yml
services:
  perpbot-primary:
    <<: *perpbot
    environment:
      - ROLE=primary
      - FAILOVER_ENABLED=true

  perpbot-standby:
    <<: *perpbot
    environment:
      - ROLE=standby
      - WATCH_PRIMARY=perpbot-primary:8000
```

### 2. 共享状态

```yaml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --repl-diskless-sync yes
    volumes:
      - redis-data:/data
```

### 3. 健康检查

```yaml
services:
  perpbot:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

---

## 🧪 测试与验证

### 1. 冒烟测试

```bash
# 运行基础功能测试
python test_websocket_feeds.py

# 运行套利扫描测试
python demos/websocket_arbitrage_demo.py

# 运行完整系统验证
python validate_perpbot_v2.py
```

### 2. 压力测试

```bash
# 并发连接测试
ab -n 1000 -c 10 http://localhost:8000/api/health

# WebSocket 连接测试
# (编写专门的压测脚本)
```

### 3. 故障注入测试

```bash
# 模拟网络延迟
sudo tc qdisc add dev eth0 root netem delay 100ms

# 模拟丢包
sudo tc qdisc add dev eth0 root netem loss 5%

# 清理规则
sudo tc qdisc del dev eth0 root
```

---

## 📈 性能优化

### 1. 容器资源限制

```yaml
services:
  perpbot:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

### 2. Redis 优化

```yaml
services:
  redis:
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save ""
      --appendonly yes
```

### 3. 应用层优化

```yaml
# config.yaml
performance:
  worker_threads: 4
  connection_pool_size: 20
  websocket_ping_interval: 30
  cache_ttl_seconds: 60
```

---

## 🔧 故障恢复

### 1. 自动恢复

```yaml
services:
  perpbot:
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### 2. 数据备份

```bash
# 每日自动备份
0 2 * * * /app/deploy/scripts/backup.sh

# 备份脚本
#!/bin/bash
DATE=$(date +%Y%m%d)
tar -czf backup-$DATE.tar.gz logs/ data/ .env config.yaml
scp backup-$DATE.tar.gz backup-server:/backups/
```

### 3. 灾难恢复

```bash
# 恢复流程
# 1. 停止服务
docker compose down

# 2. 恢复数据
tar -xzf backup-20250112.tar.gz

# 3. 重启服务
docker compose up -d

# 4. 验证
./deploy/scripts/health-check.sh
```

---

## 📞 支持与维护

### 日常维护

- **每日**: 检查健康状态、查看告警、审查日志
- **每周**: 清理日志、检查磁盘空间、更新依赖
- **每月**: 全面审计、性能优化、灾难恢复演练

### 获取帮助

1. **文档**: [docs/](.)
2. **Runbook**: [RUNBOOK.md](RUNBOOK.md)
3. **Issue**: [GitHub Issues](https://github.com/fordxx/perp-tools/issues)

---

## ✅ 部署检查清单

部署完成后，确认以下所有项：

- [ ] 所有服务容器运行正常
- [ ] WebSocket 连接稳定
- [ ] Grafana Dashboard 显示正常
- [ ] 告警规则配置完成
- [ ] 日志轮转配置完成
- [ ] 数据备份计划就绪
- [ ] 访问控制配置正确
- [ ] HTTPS 证书有效
- [ ] 防火墙规则配置
- [ ] 运维文档已阅读

完整检查清单: [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)

---

**最后更新**: 2025-12-12
