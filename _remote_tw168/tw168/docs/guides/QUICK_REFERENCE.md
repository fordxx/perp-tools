# tw168 交易系统快速参考

> 服务器: **3.38.98.169**
> 端口: **80** (Nginx) → **8000** (Docker)

---

## 🚀 一键命令

### 本地 (开发机)

```bash
# 查看服务器状态
./check_tw168.sh

# SSH 登录服务器
./ssh_tw168.sh
```

### 服务器上

```bash
# 一键查看完整状态 ⭐ 最常用
~/check_tw168_status.sh

# 查看命令帮助
cat ~/tw168_commands.txt
```

---

## 📊 监控端点

所有端点都可以通过 **80 端口** 或 **8000 端口** 访问：

| 端点 | 用途 | 示例 |
|------|------|------|
| `/health` | 健康检查 | `curl http://3.38.98.169/health` |
| `/webhook/tradingview` | TradingView Webhook | TradingView 配置使用此 URL |
| `/rate_limits` | 速率限制监控 | `curl http://3.38.98.169/rate_limits` |
| `/websocket/stats` | WebSocket 统计 | `curl http://3.38.98.169/websocket/stats` |
| `/emergency` | 紧急仓位监控 | `curl http://3.38.98.169/emergency` |
| `/metrics` | 系统指标 | `curl http://3.38.98.169/metrics` |

---

## 📝 常用命令

### 日志查看

```bash
# 实时日志 (最常用)
docker logs -f tw168-tv-okx-1

# 查看最近 50 行
docker logs --tail 50 tw168-tv-okx-1

# 查看最近 5 分钟
docker logs --since 5m tw168-tv-okx-1

# 搜索错误
docker logs --tail 200 tw168-tv-okx-1 | grep -i error
```

### 服务管理

```bash
# 重启服务
cd ~/perp-tools/_remote_tw168/tw168
docker compose restart

# 停止服务
docker compose down

# 启动服务
docker compose up -d

# 查看容器状态
docker ps
```

### Nginx 管理

```bash
# 重启 Nginx
sudo systemctl restart nginx

# 重新加载配置 (不中断服务)
sudo systemctl reload nginx

# 检查配置
sudo nginx -t

# 查看状态
sudo systemctl status nginx
```

---

## 🔍 状态检查输出说明

运行 `~/check_tw168_status.sh` 后的输出解读：

### ✅ 正常状态示例

```
📦 Docker 容器状态:
tw168-tv-okx-1   Up 12 hours   0.0.0.0:8000->8000/tcp
```
- **Up X hours**: 容器运行时间
- **0.0.0.0:8000**: 端口正常开放

```
💚 健康检查:
  ✅ 服务正常运行
```
- 服务响应正常

```
⏱️  速率限制器状态:
  "utilization": "0.0%"  或  "< 50%"
```
- **0-50%**: 正常
- **50-80%**: 警告，需关注
- **> 80%**: 接近限制

```
🔌 WebSocket 订阅统计:
  "utilization": "3.0%"
```
- **< 60%**: 正常
- **60-85%**: 警告
- **> 85%**: 接近限制

```
🚨 紧急仓位监控:
  ✅ 无紧急仓位 (count: 0)
```
- **count: 0**: 正常
- **count > 0**: ⚠️ 立即检查！

```
💻 系统资源:
  CPU: 17.4%
  内存: 264Mi / 416Mi (63.5%)
  磁盘: 10G / 19G (55%)
```
- **CPU < 80%**: 正常
- **内存 < 80%**: 正常
- **磁盘 < 80%**: 正常

### ❌ 异常状态处理

#### 容器未运行
```bash
# 查看容器状态
docker ps -a

# 查看容器日志
docker logs tw168-tv-okx-1

# 重新启动
cd ~/perp-tools/_remote_tw168/tw168
docker compose up -d
```

#### 服务健康检查失败
```bash
# 查看最近日志
docker logs --tail 100 tw168-tv-okx-1

# 检查端口
sudo netstat -tlnp | grep 8000

# 重启服务
cd ~/perp-tools/_remote_tw168/tw168
docker compose restart
```

#### 发现紧急仓位
```bash
# 查看详细信息
curl http://localhost/emergency | python3 -m json.tool

# 检查 Telegram 通知
# 检查交易所实际仓位
# 必要时手动干预
```

---

## 🚨 告警阈值

| 指标 | 正常 | 警告 | 危险 | 操作 |
|------|------|------|------|------|
| Rate Limiter 利用率 | < 50% | 50-80% | > 80% | 减少请求频率 |
| WebSocket 利用率 | < 60% | 60-85% | > 85% | 减少订阅或扩容 |
| 紧急仓位数量 | 0 | 1-2 | ≥ 3 | 立即人工干预 |
| CPU 使用率 | < 60% | 60-80% | > 80% | 检查异常进程 |
| 内存使用率 | < 70% | 70-85% | > 85% | 考虑扩容 |
| 磁盘使用率 | < 70% | 70-85% | > 85% | 清理日志 |

---

## 🔧 故障排查流程

### 1. 服务无响应

```bash
# 步骤 1: 检查容器状态
docker ps

# 步骤 2: 查看容器日志
docker logs --tail 100 tw168-tv-okx-1

# 步骤 3: 检查端口
sudo netstat -tlnp | grep -E ':80|:8000'

# 步骤 4: 重启服务
cd ~/perp-tools/_remote_tw168/tw168
docker compose restart
```

### 2. TradingView Webhook 不工作

```bash
# 步骤 1: 检查 Nginx
sudo nginx -t
sudo systemctl status nginx

# 步骤 2: 测试 webhook 端点
curl -X POST http://localhost/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}'

# 步骤 3: 查看日志
docker logs -f tw168-tv-okx-1 | grep webhook
```

### 3. WebSocket 连接问题

```bash
# 查看 WebSocket 统计
curl http://localhost/websocket/stats | python3 -m json.tool

# 查看相关日志
docker logs --tail 200 tw168-tv-okx-1 | grep -i "ws"

# 检查连接错误
docker logs --tail 500 tw168-tv-okx-1 | grep -i "error.*ws"
```

---

## 📍 重要文件位置

### 服务器上

```
~/perp-tools/_remote_tw168/tw168/          # 项目根目录
├── app/                                    # 应用代码
│   ├── main.py                            # 主程序
│   ├── okx.py                             # OKX 客户端
│   ├── emergency_handler.py               # 紧急处理器
│   └── rate_limiter.py                    # 速率限制器
├── docker-compose.yml                      # Docker 配置
├── Dockerfile                              # Docker 镜像
├── .env                                    # 环境变量 (机密)
└── requirements.txt                        # Python 依赖

/etc/nginx/sites-available/tv-okx          # Nginx 配置
~/check_tw168_status.sh                    # 状态检查脚本
~/tw168_commands.txt                       # 命令参考
```

### 本地 (开发机)

```
/home/fordxx/perp-tools/_remote_tw168/tw168/
├── check_tw168.sh                         # 远程状态检查
├── ssh_tw168.sh                           # SSH 登录
└── QUICK_REFERENCE.md                     # 本文档
```

---

## 🔄 更新部署流程

```bash
# 1. SSH 登录服务器
./ssh_tw168.sh

# 2. 进入项目目录
cd ~/perp-tools/_remote_tw168/tw168

# 3. 备份当前配置
git stash save "backup-$(date +%Y%m%d-%H%M%S)"

# 4. 拉取最新代码
git pull origin claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF

# 5. 停止服务
docker compose down

# 6. 重新构建镜像
docker compose build

# 7. 启动服务
docker compose up -d

# 8. 查看日志确认
docker logs -f tw168-tv-okx-1
```

---

## 💡 实用技巧

### 实时监控多个指标

```bash
# 在多个终端窗口同时运行
watch -n 5 'curl -s http://localhost/rate_limits | python3 -m json.tool'
watch -n 10 'curl -s http://localhost/emergency | python3 -m json.tool'
docker logs -f tw168-tv-okx-1
```

### 搜索特定交易对日志

```bash
docker logs --tail 500 tw168-tv-okx-1 | grep "BTC-USDT-SWAP"
```

### 查看性能统计

```bash
# 容器资源使用
docker stats tw168-tv-okx-1 --no-stream

# 系统整体资源
htop
```

### 备份日志

```bash
# 导出日志到文件
docker logs tw168-tv-okx-1 > tw168_logs_$(date +%Y%m%d_%H%M%S).log
```

---

## 📞 紧急联系

如果遇到无法解决的问题：

1. ✅ 先运行 `~/check_tw168_status.sh` 收集信息
2. ✅ 检查 `/emergency` 端点是否有紧急仓位
3. ✅ 导出最近 500 行日志
4. ✅ 记录问题发生时间和触发条件

---

## 🎯 快速测试

```bash
# 测试所有监控端点
for endpoint in health rate_limits websocket/stats emergency; do
  echo "=== Testing /$endpoint ==="
  curl -s http://3.38.98.169/$endpoint
  echo -e "\n"
done
```

---

*最后更新: 2025-12-27*
*文档版本: v1.0*
