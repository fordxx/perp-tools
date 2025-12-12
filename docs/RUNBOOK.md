# PerpBot V2 运维手册 (Runbook)

**版本**: 1.0
**最后更新**: 2025-12-12
**目标读者**: 运维工程师、开发人员

---

## 📖 目录

- [日常运维](#日常运维)
- [监控与告警](#监控与告警)
- [故障排查](#故障排查)
- [紧急操作](#紧急操作)
- [维护操作](#维护操作)
- [性能优化](#性能优化)

---

## 日常运维

### 每日检查清单

**早上 9:00 AM**
- [ ] 检查系统健康状态
- [ ] 查看过去 24 小时的交易记录
- [ ] 检查是否有告警
- [ ] 查看资金使用情况
- [ ] 检查 WebSocket 连接状态

**下午 3:00 PM**
- [ ] 检查系统性能指标
- [ ] 查看日志中的异常
- [ ] 检查磁盘空间使用

**晚上 9:00 PM**
- [ ] 查看当天 PnL
- [ ] 检查是否有未平仓位
- [ ] 准备次日交易参数调整

### 健康检查命令

```bash
# 快速健康检查
./deploy/scripts/health-check.sh

# 查看系统状态
docker compose ps

# 查看资源使用
docker stats --no-stream

# 检查 WebSocket 连接
curl http://localhost:8000/api/websocket/status
```

### 日志查看

```bash
# 查看实时日志
./deploy/scripts/logs.sh perpbot

# 查看最近 100 行
docker compose logs --tail=100 perpbot

# 查看错误日志
docker compose logs perpbot | grep ERROR

# 查看特定时间段日志
docker compose logs --since="2024-01-01T00:00:00" --until="2024-01-01T23:59:59" perpbot
```

---

## 监控与告警

### Grafana Dashboard

**访问**: http://localhost:3000

**关键指标**:

1. **System Health** (目标: > 90%)
   - 位置: 主 Dashboard 左上角
   - 正常范围: 90-100%
   - 告警阈值: < 70%

2. **Active Positions** (目标: < 10)
   - 位置: 主 Dashboard 右上角
   - 正常范围: 0-5
   - 告警阈值: > 10

3. **Capital Utilization** (目标: < 80%)
   - 位置: 主 Dashboard 右侧
   - 正常范围: 0-70%
   - 告警阈值: > 80%

4. **WebSocket Latency** (目标: < 100ms)
   - 位置: 主 Dashboard 中部
   - 正常范围: 30-80ms
   - 告警阈值: > 200ms

5. **Order Success Rate** (目标: > 95%)
   - 位置: 主 Dashboard 下部
   - 正常范围: 95-100%
   - 告警阈值: < 90%

### Prometheus 查询

**访问**: http://localhost:9090

**常用查询**:

```promql
# 系统健康度
perpbot_system_health

# WebSocket 连接状态
perpbot_websocket_connected{exchange="okx"}

# 订单成功率
rate(perpbot_orders_success_total[5m]) / rate(perpbot_orders_total[5m])

# P99 执行延迟
histogram_quantile(0.99, rate(perpbot_order_execution_duration_seconds_bucket[5m]))

# 资金使用率
perpbot_capital_utilization_percent

# 套利机会发现率
rate(perpbot_arbitrage_opportunities_total[5m])
```

### 告警处理

**Critical 告警**:
1. 立即查看 Alertmanager: http://localhost:9093
2. 确认告警详情
3. 按照对应的处理流程操作
4. 记录处理过程
5. 告警解除后进行复盘

**Warning 告警**:
1. 记录告警信息
2. 分析根本原因
3. 制定优化计划
4. 非紧急情况下周内处理

---

## 故障排查

### 故障分类与响应时间

| 严重程度 | 示例 | 响应时间 | 解决时间目标 |
|---------|------|----------|-------------|
| **P0 - 严重** | 系统宕机、资金丢失 | 立即 | 1 小时 |
| **P1 - 高** | 交易异常、数据不准 | 15 分钟 | 4 小时 |
| **P2 - 中** | 性能下降、连接不稳 | 1 小时 | 1 天 |
| **P3 - 低** | 日志过多、界面问题 | 4 小时 | 1 周 |

### 常见故障及解决方案

#### 1. PerpBot 服务无法启动

**症状**:
- Docker 容器启动后立即退出
- 日志显示初始化错误

**排查步骤**:
```bash
# 1. 查看容器状态
docker compose ps

# 2. 查看最近日志
docker compose logs --tail=50 perpbot

# 3. 检查配置文件
cat .env | grep -v "^#" | grep -v "^$"
cat config.yaml
```

**常见原因**:
1. **API 凭证错误**
   - 检查 `.env` 中的 API Key
   - 验证凭证是否过期
   - 确认环境配置 (testnet/mainnet)

2. **端口被占用**
   ```bash
   # 检查端口占用
   netstat -tlnp | grep :8000

   # 解决: 停止占用进程或修改端口
   ```

3. **依赖服务未启动**
   ```bash
   # 检查 Redis
   docker compose ps redis

   # 重启依赖服务
   docker compose restart redis
   ```

**解决方案**:
```bash
# 重新配置
nano .env

# 重启服务
docker compose down
docker compose up -d

# 验证
./deploy/scripts/health-check.sh
```

#### 2. WebSocket 连接失败

**症状**:
- Dashboard 显示交易所断开
- 日志显示 "WebSocket connection failed"
- 没有接收到行情数据

**排查步骤**:
```bash
# 1. 检查 WebSocket 状态
curl http://localhost:8000/api/websocket/status

# 2. 查看日志
docker compose logs perpbot | grep -i websocket

# 3. 测试网络连接
ping api.okx.com
curl -I https://api.hyperliquid.xyz
```

**常见原因**:
1. **网络问题**
   - 检查防火墙设置
   - 验证 DNS 解析
   - 测试到交易所的连接

2. **API 限流**
   - 检查是否超过 API 频率限制
   - 等待冷却期后重试
   - 调整请求频率

3. **交易所维护**
   - 查看交易所公告
   - 切换到备用端点
   - 等待恢复

**解决方案**:
```bash
# 重启 WebSocket 连接
docker compose restart perpbot

# 如果持续失败，切换到备用端点
# 编辑 .env 修改 WebSocket URL
```

#### 3. 交易执行失败

**症状**:
- 订单提交失败
- 日志显示 "Order rejected"
- 订单成功率下降

**排查步骤**:
```bash
# 1. 查看订单日志
docker compose logs perpbot | grep -i "order\|trade"

# 2. 检查资金余额
curl http://localhost:8000/api/balances

# 3. 检查持仓
curl http://localhost:8000/api/positions
```

**常见原因**:
1. **余额不足**
   - 检查可用余额
   - 平掉部分持仓释放资金
   - 充值

2. **风控拒绝**
   - 检查风控规则
   - 查看日志中的拒绝原因
   - 调整风控参数

3. **交易所错误**
   - 查看交易所返回的错误码
   - 参考交易所 API 文档
   - 联系交易所支持

**解决方案**:
```bash
# 调整风控参数
nano config.yaml
# 修改 max_position_size_usdt, max_leverage 等

# 重启应用新配置
docker compose restart perpbot
```

#### 4. 内存使用过高

**症状**:
- 容器内存使用 > 80%
- 系统响应变慢
- OOM (Out of Memory) 错误

**排查步骤**:
```bash
# 1. 查看内存使用
docker stats --no-stream

# 2. 查看进程内存
docker compose exec perpbot top -o %MEM

# 3. 检查是否有内存泄漏
docker compose logs perpbot | grep -i "memory\|oom"
```

**解决方案**:
```bash
# 1. 重启服务释放内存
docker compose restart perpbot

# 2. 增加内存限制（临时）
docker compose down
# 编辑 docker-compose.yml 增加 mem_limit
docker compose up -d

# 3. 优化配置
# 减少订阅的交易对数量
# 调整日志级别到 WARNING
# 增加日志轮转频率

# 4. 升级服务器（长期）
```

#### 5. 数据不一致

**症状**:
- Dashboard 显示的数据与实际不符
- 持仓数量错误
- PnL 计算不准确

**排查步骤**:
```bash
# 1. 对比多个数据源
curl http://localhost:8000/api/positions  # PerpBot
# 登录交易所查看实际持仓

# 2. 检查同步状态
docker compose logs perpbot | grep -i "sync\|position"

# 3. 检查数据库状态（如果使用）
# 查询持仓表，对比时间戳
```

**解决方案**:
```bash
# 1. 强制重新同步
curl -X POST http://localhost:8000/api/sync/positions

# 2. 重启服务
docker compose restart perpbot

# 3. 如果问题持续，清理缓存
docker compose down
docker volume rm perpbot_redis-data
docker compose up -d
```

---

## 紧急操作

### 紧急停止所有交易

**场景**: 发现严重问题，需要立即停止所有交易活动

**步骤**:
```bash
# 方法 1: 停止 PerpBot 服务
docker compose stop perpbot

# 方法 2: 通过 API 暂停交易
curl -X POST http://localhost:8000/api/trading/pause

# 方法 3: 紧急停机
docker compose down
```

**验证**:
```bash
# 确认没有新订单
curl http://localhost:8000/api/orders/active

# 确认服务已停止
docker compose ps
```

### 紧急平仓

**场景**: 需要立即平掉所有持仓

**步骤**:
```bash
# 1. 查看所有持仓
curl http://localhost:8000/api/positions

# 2. 一键平仓（如果实现了）
curl -X POST http://localhost:8000/api/positions/close-all

# 3. 手动平仓（如果 API 不可用）
# 登录各交易所手动平仓
```

### 数据备份

**场景**: 紧急备份数据以防丢失

**步骤**:
```bash
# 1. 备份日志
tar -czf logs-backup-$(date +%Y%m%d-%H%M%S).tar.gz logs/

# 2. 备份配置
tar -czf config-backup-$(date +%Y%m%d-%H%M%S).tar.gz .env config.yaml

# 3. 备份数据卷
docker run --rm -v perpbot_redis-data:/data -v $(pwd):/backup alpine tar czf /backup/redis-backup-$(date +%Y%m%d-%H%M%S).tar.gz /data

# 4. 导出 Prometheus 数据（可选）
docker compose exec prometheus promtool tsdb dump /prometheus > prometheus-backup-$(date +%Y%m%d-%H%M%S).txt
```

### 回滚部署

**场景**: 新版本有问题，需要回滚到旧版本

**步骤**:
```bash
# 1. 停止服务
docker compose down

# 2. 切换到旧版本
git log --oneline  # 查看历史版本
git checkout <old-commit-hash>

# 3. 重新构建
docker compose build

# 4. 启动服务
docker compose up -d

# 5. 验证
./deploy/scripts/health-check.sh
```

---

## 维护操作

### 定期维护任务

**每周**:
- [ ] 清理旧日志文件
- [ ] 检查磁盘空间使用
- [ ] 更新 Docker 镜像
- [ ] 备份配置和数据
- [ ] 检查安全更新

**每月**:
- [ ] 全面系统审计
- [ ] 性能优化评估
- [ ] 更新依赖包
- [ ] 灾难恢复演练
- [ ] 文档更新

### 日志清理

```bash
# 清理 30 天前的日志
find logs/ -name "*.log" -mtime +30 -delete

# 清理 Docker 日志
docker system prune -af --volumes

# 清理旧的容器和镜像
docker compose down --rmi all --volumes --remove-orphans
```

### 升级流程

```bash
# 1. 备份当前版本
./deploy/scripts/backup.sh

# 2. 拉取最新代码
git pull origin main

# 3. 检查更新日志
cat CHANGELOG.md

# 4. 更新依赖
docker compose pull

# 5. 重新构建
docker compose build

# 6. 停止服务
docker compose down

# 7. 启动新版本
docker compose up -d

# 8. 验证升级
./deploy/scripts/health-check.sh
python validate_perpbot_v2.py

# 9. 监控 30 分钟
watch -n 60 './deploy/scripts/health-check.sh'
```

### 配置变更

```bash
# 1. 备份现有配置
cp .env .env.backup
cp config.yaml config.yaml.backup

# 2. 修改配置
nano .env
nano config.yaml

# 3. 验证配置（可选）
# python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# 4. 重启服务应用配置
docker compose restart perpbot

# 5. 验证配置生效
curl http://localhost:8000/api/config
```

---

## 性能优化

### 识别性能瓶颈

```bash
# 1. CPU 使用率
docker stats --no-stream | sort -k3 -h

# 2. 内存使用
docker stats --no-stream | sort -k4 -h

# 3. 网络 I/O
docker stats --no-stream --format "table {{.Name}}\t{{.NetIO}}"

# 4. 磁盘 I/O
iostat -x 5

# 5. 应用层性能
curl http://localhost:8000/metrics | grep duration
```

### 优化建议

**CPU 优化**:
- 减少订阅的交易对数量
- 降低扫描频率
- 使用编译型语言重写热点代码

**内存优化**:
- 调整日志级别
- 限制历史数据保留时间
- 增加服务器内存

**网络优化**:
- 使用地理位置更近的服务器
- 启用 Redis 缓存
- 优化 WebSocket 心跳频率

**磁盘优化**:
- 使用 SSD
- 调整日志轮转策略
- 定期清理旧数据

---

## 📞 联系与支持

### 紧急联系方式

- **主要负责人**: [姓名] - [手机]
- **备用联系人**: [姓名] - [手机]
- **技术支持**: support@example.com

### 上报流程

**P0/P1 故障**:
1. 立即通知主要负责人
2. 在问题跟踪系统创建紧急工单
3. 启动应急响应流程
4. 每小时更新状态

**P2/P3 故障**:
1. 创建工单
2. 在工作时间内通知相关人员
3. 按计划处理

---

## 📝 变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2025-12-12 | 1.0 | 初始版本创建 | Claude |

---

**最后更新**: 2025-12-12
**下次审查**: 2025-01-12
