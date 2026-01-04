# TW168 故障排查指南

本文档提供 TW168 系统常见问题的诊断和解决方案。

## 📋 目录

- [快速诊断](#快速诊断)
- [服务问题](#服务问题)
- [Webhook 问题](#webhook-问题)
- [交易问题](#交易问题)
- [API 问题](#api-问题)
- [配置问题](#配置问题)
- [性能问题](#性能问题)
- [日志分析](#日志分析)

## 快速诊断

### 1. 检查服务状态

```bash
# Docker
docker compose ps

# 系统服务
sudo systemctl status tw168

# 健康检查
curl http://localhost:8000/health
```

### 2. 查看最近日志

```bash
# Docker
docker compose logs --tail=50

# 系统服务
sudo journalctl -u tw168 -n 50

# 应用日志
tail -50 tw168.log
```

### 3. 快速重启

```bash
# Docker
docker compose restart

# 系统服务
sudo systemctl restart tw168
```

## 服务问题

### 问题: 服务无法启动

#### 症状
```bash
$ docker compose up
ERROR: Cannot start service app
```

#### 可能原因与解决方案

**1. 端口被占用**

```bash
# 检查端口占用
sudo lsof -i :8000

# 杀死占用进程
sudo kill -9 <PID>

# 或修改端口
# 在 docker-compose.yml 中修改端口映射
ports:
  - "8001:8000"
```

**2. 配置文件错误**

```bash
# 检查 .env 文件
cat .env | grep -v "^#" | grep -v "^$"

# 验证必须的配置项
python3 -c "from app.config import SETTINGS; print(SETTINGS)"
```

**3. Docker 资源不足**

```bash
# 检查 Docker 资源
docker system df

# 清理无用资源
docker system prune -a
```

### 问题: 服务频繁重启

#### 症状
```bash
$ docker compose ps
NAME     STATUS
app      Restarting (1) 5 seconds ago
```

#### 诊断步骤

```bash
# 1. 查看完整日志
docker compose logs --tail=200

# 2. 检查常见错误
grep -E "ERROR|Exception|Traceback" tw168.log | tail -20

# 3. 检查内存使用
docker stats --no-stream
```

#### 常见原因

**1. Python 导入错误**
```
ModuleNotFoundError: No module named 'xxx'
```

**解决:**
```bash
# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

**2. 配置错误**
```
KeyError: 'OKX_API_KEY'
```

**解决:**
```bash
# 检查 .env 文件
grep OKX_API_KEY .env

# 确保所有必须的环境变量都存在
diff .env.example .env
```

**3. 数据库连接失败**
```
ConnectionError: Unable to connect to database
```

**解决:**
```bash
# 检查数据库服务
docker compose ps db

# 重启数据库
docker compose restart db
```

### 问题: 服务运行缓慢

#### 症状
- HTTP 请求超时
- Webhook 响应延迟
- CPU 使用率过高

#### 诊断

```bash
# 检查资源使用
docker stats

# 检查进程
top -p $(pgrep -f uvicorn)

# 检查日志中的慢查询
grep "slow" tw168.log
```

#### 解决方案

**1. 增加 Worker 数量**

```bash
# 修改 docker-compose.yml
command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**2. 启用 K 线缓存**

```bash
# .env
CANDLE_WS_ENABLED=true
CANDLE_WS_OKX_ENABLED=true
```

**3. 优化日志级别**

```bash
# .env
LOG_LEVEL=WARNING  # 减少日志输出
```

## Webhook 问题

### 问题: TradingView Webhook 无响应

#### 症状
- TradingView 显示 Webhook 超时
- 没有收到交易信号

#### 诊断步骤

**1. 检查服务可访问性**

```bash
# 从外部测试
curl http://your-domain.com/health

# 从 TradingView 测试
# 在 TradingView Alert 中点击 "Test"
```

**2. 检查防火墙**

```bash
# 检查 UFW
sudo ufw status

# 确保端口开放
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

**3. 检查 Nginx 配置**

```bash
# 测试配置
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/error.log
```

#### 解决方案

**1. 验证 Webhook URL**

正确格式:
```
http://your-domain.com/webhook/tradingview
https://your-domain.com/webhook/tradingview
```

错误格式:
```
http://your-domain.com/webhook/tradingview/  # 末尾不要斜杠
http://your-domain.com:8000/webhook/tradingview  # 生产环境不要端口号
```

**2. 手动测试 Webhook**

```bash
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "your_secret",
    "type": "ZONE",
    "zone": "OVERSOLD",
    "instId": "ETH-USDT-SWAP",
    "tf": "15m"
  }'
```

预期响应:
```json
{"ok": true, "message": "zone_updated", ...}
```

### 问题: Webhook 认证失败

#### 症状
```json
{"detail": "Invalid webhook secret"}
```

#### 解决方案

```bash
# 1. 检查环境变量
grep TV_WEBHOOK_SECRET .env

# 2. 检查 TradingView Alert 配置
# 确保 JSON 中的 secret 与 .env 一致

# 3. 重启服务使配置生效
docker compose restart
```

### 问题: 信号被跳过

#### 症状
```json
{"ok": true, "skipped": "cooldown"}
```

#### 常见跳过原因

| skipped 值 | 原因 | 解决方案 |
|-----------|------|----------|
| `cooldown` | 冷却时间未到 | 等待或减少 `COOLDOWN_SECONDS` |
| `duplicate` | 重复信号 | 检查 TradingView Alert 触发频率 |
| `zone_expired_or_neutral` | ZONE 过期或为 NEUTRAL | 先发送 ZONE 信号 |
| `pattern_filter` | 形态过滤不通过 | 禁用形态过滤或调整参数 |
| `rsi_filter` | RSI 过滤不通过 | 禁用 RSI 过滤或调整阈值 |
| `direction_disabled` | 方向被禁用 | 启用 `ENABLE_LONG` 或 `ENABLE_SHORT` |

#### 查看详细原因

```bash
# 查看最近的跳过记录
grep "skipped" tw168.log | tail -20

# 查看信号审计日志
cat logs/signals/signals-$(date +%Y%m%d).jsonl | tail -10 | jq
```

## 交易问题

### 问题: 订单未执行

#### 症状
- Webhook 返回成功，但 OKX 无订单
- Paper mode 响应但没有实盘订单

#### 诊断

**1. 检查交易开关**

```bash
grep TRADING_ENABLED .env
```

如果是 `TRADING_ENABLED=false`，则为模拟交易。

**2. 检查交易对白名单**

```bash
grep SYMBOL_ALLOWLIST .env
```

确保交易对在白名单中。

**3. 查看订单日志**

```bash
# 搜索订单相关日志
grep "order_placed\|order_failed" tw168.log | tail -20

# 搜索 OKX 错误
grep "OKX.*error" tw168.log | tail -20
```

### 问题: 订单被拒绝

#### 症状
```
OKX API Error 51000: Order placement failed
```

#### 常见 OKX 错误码

| 错误码 | 原因 | 解决方案 |
|--------|------|----------|
| 51000 | 参数错误 | 检查订单参数 |
| 51001 | API 密钥错误 | 检查 API 配置 |
| 51002 | 签名错误 | 重新生成 API 密钥 |
| 51008 | 余额不足 | 充值账户 |
| 51010 | 交易对不存在 | 检查 instId 格式 |
| 51014 | 订单数量太小 | 增加 ORDER_SZ |
| 51020 | 超过持仓限制 | 减少仓位或提高账户等级 |

#### 解决步骤

```bash
# 1. 验证 API 密钥
curl -X GET "https://www.okx.com/api/v5/account/balance" \
  -H "OK-ACCESS-KEY: $OKX_API_KEY" \
  -H "OK-ACCESS-SIGN: ..." \
  -H "OK-ACCESS-TIMESTAMP: ..." \
  -H "OK-ACCESS-PASSPHRASE: $OKX_API_PASSPHRASE"

# 2. 检查账户余额
python3 -c "from app.okx import OKXClient; print(OKXClient().get_balance())"

# 3. 检查最小下单量
python3 -c "from app.okx import OKXClient; print(OKXClient().get_market_config('ETH-USDT-SWAP'))"
```

### 问题: 止盈止损未触发

#### 症状
- 价格已达到止盈位，但未平仓
- TradeManager 没有执行

#### 诊断

```bash
# 1. 检查 TradeManager 是否运行
grep "TradeManager" tw168.log | tail -20

# 2. 检查活跃的交易计划
curl http://localhost:8000/trades

# 3. 检查持仓
python3 -c "from app.okx import OKXClient; print(OKXClient().get_positions())"
```

#### 解决方案

**1. 检查配置**

```bash
# 止盈是否启用
grep TP_ENABLED .env

# TradeManager 轮询周期
grep MANAGER_POLL_SECONDS .env
```

**2. 手动触发平仓**

```python
# 紧急平仓脚本
from app.okx import OKXClient

okx = OKXClient()
okx.close_position("ETH-USDT-SWAP", "long")
```

## API 问题

### 问题: OKX API 超时

#### 症状
```
TimeoutError: Request to OKX API timed out
```

#### 解决方案

```bash
# 1. 检查网络连接
ping www.okx.com

# 2. 检查 OKX 服务状态
curl https://www.okx.com/api/v5/system/status

# 3. 增加超时时间
# 在 app/okx.py 中修改超时设置
timeout = 30  # 增加到 30 秒
```

### 问题: Lighter API 错误

#### 症状
```
ExtendedError: Failed to fetch market data
```

#### 解决方案

```bash
# 1. 检查 Lighter API 状态
curl https://api.lighter.xyz/markets

# 2. 检查 Paradex 配置
grep PARADEX .env

# 3. 重新连接 WebSocket
docker compose restart
```

## 配置问题

### 问题: 环境变量未生效

#### 症状
- 修改 .env 后配置未更新
- 服务使用旧配置

#### 解决方案

```bash
# Docker 需要重启容器
docker compose down
docker compose up -d

# 系统服务需要重启
sudo systemctl restart tw168

# 验证配置
python3 -c "from app.config import SETTINGS; print(SETTINGS.dict())"
```

### 问题: 配置项冲突

#### 症状
```
ValueError: RISK_PER_TRADE_USDT and ORDER_SZ both set
```

#### 解决方案

```bash
# 选择一种仓位计算方式
# 推荐使用 RISK_PER_TRADE_USDT
RISK_PER_TRADE_USDT=100
ORDER_SZ=0  # 设置为 0 禁用固定数量

# 或使用固定数量 (不推荐)
RISK_PER_TRADE_USDT=0
ORDER_SZ=1
```

## 性能问题

### 问题: 内存使用过高

#### 症状
```bash
$ docker stats
CONTAINER   MEM USAGE / LIMIT
app         1.8GB / 2GB
```

#### 解决方案

**1. 限制 K 线缓存**

```bash
# .env
CANDLE_CACHE_MAX_BARS=1000  # 减少缓存数量
CANDLE_WS_OKX_MAX_SUBS=50   # 减少订阅数量
```

**2. 限制 Docker 内存**

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 1G
```

**3. 清理旧日志**

```bash
# 清理 30 天前的日志
find logs/ -name "*.log" -mtime +30 -delete
find logs/signals/ -name "*.jsonl" -mtime +30 -delete
```

### 问题: CPU 使用率过高

#### 症状
- CPU 持续 100%
- 响应缓慢

#### 诊断

```bash
# 查看进程
top -p $(pgrep -f uvicorn)

# 查看线程
ps -eLf | grep uvicorn

# Python 性能分析
pip install py-spy
sudo py-spy top --pid $(pgrep -f uvicorn)
```

#### 解决方案

**1. 优化 WebSocket 订阅**

```bash
# 减少订阅
CANDLE_WS_TFS=1h  # 仅订阅必要的时间周期
CANDLE_WS_SYMBOL_TFS=ETH-USDT-SWAP:1h,BTC-USDT-SWAP:1h
```

**2. 禁用不必要的功能**

```bash
# 禁用 RSI 过滤
RSI_FILTER_ENABLED=false

# 禁用形态过滤
PATTERN_LONG=none
PATTERN_SHORT=none
```

## 日志分析

### 查找特定错误

```bash
# 查找所有错误
grep -E "ERROR|Exception" tw168.log

# 查找特定交易对的错误
grep "ETH-USDT-SWAP.*ERROR" tw168.log

# 查找 API 错误
grep "OKX.*error\|Extended.*error" tw168.log

# 查找最近 1 小时的错误
find logs/ -name "*.log" -mmin -60 -exec grep "ERROR" {} \;
```

### 分析信号审计日志

```bash
# 查看今天的信号
cat logs/signals/signals-$(date +%Y%m%d).jsonl | jq

# 统计信号类型
cat logs/signals/signals-$(date +%Y%m%d).jsonl | jq -r '.type' | sort | uniq -c

# 查找被跳过的信号
cat logs/signals/signals-$(date +%Y%m%d).jsonl | jq 'select(.decision == "skipped")'

# 查找成功的交易
cat logs/signals/signals-$(date +%Y%m%d).jsonl | jq 'select(.decision == "order_placed")'
```

### 性能分析

```bash
# 统计请求处理时间
grep "request_duration" tw168.log | awk '{sum+=$NF; count++} END {print "Average:", sum/count, "ms"}'

# 统计 API 调用次数
grep "OKX.*API.*call" tw168.log | wc -l

# 统计订单数量
grep "order_placed" tw168.log | wc -l
```

## 常用诊断命令

```bash
# 综合检查脚本
#!/bin/bash

echo "=== Service Status ==="
docker compose ps

echo "\n=== Health Check ==="
curl -s http://localhost:8000/health | jq

echo "\n=== Recent Errors ==="
docker compose logs --tail=20 | grep ERROR

echo "\n=== Memory Usage ==="
docker stats --no-stream

echo "\n=== Active Trades ==="
curl -s http://localhost:8000/trades | jq

echo "\n=== Configuration ==="
grep -E "TRADING_ENABLED|EXCHANGE|SYMBOL_ALLOWLIST" .env
```

## 获取帮助

如果以上方法都无法解决问题:

1. **收集诊断信息**
   ```bash
   # 生成诊断报告
   ./scripts/generate_diagnostic_report.sh > diagnostic.txt
   ```

2. **提交 Issue**
   - 前往 GitHub Issues
   - 附上诊断报告
   - 描述问题和复现步骤

3. **社区支持**
   - GitHub Discussions
   - Telegram 群组

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
