# 部署检查清单 - 关键修复

> 修复完成日期: 2025-12-26
> 部署前必读文档

---

## ✅ 修复完成确认

### 1. 异常处理细化
- [x] main.py JSON 解析异常细化
- [x] main.py Extended 订单异常分类
- [x] okx.py 添加重试机制 (指数退避)
- [x] okx.py 区分 4xx/5xx 错误

### 2. WebSocket 重连优化
- [x] candle_cache.py OKX K线 WebSocket 指数退避
- [x] ws_fills.py OKX 成交 WebSocket 指数退避
- [x] ws_fills.py Extended 成交 WebSocket 指数退避
- [x] 连续错误计数 (max 10 次)
- [x] 连接成功后重置延迟

### 3. 止损失败兜底机制
- [x] emergency_handler.py 新模块创建
- [x] main.py 集成紧急处理器
- [x] /emergency 端点添加
- [x] 多层止损防护实现
- [x] CRITICAL 告警机制

---

## 🚀 部署步骤

### 步骤 1: 备份现有代码
```bash
# 在远程服务器执行
cd /home/ubuntu/tw168
cp -r app app.backup.$(date +%Y%m%d_%H%M%S)
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
```

### 步骤 2: 同步新代码
```bash
# 在本地执行
rsync -avz --exclude='.venv' --exclude='*.pyc' \
  /home/fordxx/perp-tools/_remote_tw168/tw168/ \
  ubuntu@3.38.98.169:/home/ubuntu/tw168/
```

### 步骤 3: 检查依赖
```bash
# 在远程服务器执行
cd /home/ubuntu/tw168
source .venv/bin/activate
pip install -r requirements.txt
```

### 步骤 4: 更新配置
```bash
# 检查 .env 文件,添加新配置项 (如果需要)
cat >> .env << 'EOF'
# 备用止损 (强烈推荐开启)
BACKUP_SL_ENABLED=true
EOF
```

### 步骤 5: 验证配置
```bash
# 检查配置是否正确加载
python3 -c "from app.config import SETTINGS; print(f'Exchange: {SETTINGS.exchange}'); print(f'Backup SL: {SETTINGS.backup_sl_enabled}')"
```

### 步骤 6: 重启服务
```bash
# 使用 supervisor (推荐)
sudo supervisorctl restart tw168

# 或使用 systemd
sudo systemctl restart tw168

# 或手动重启
pkill -f "uvicorn app.main:app"
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > tw168.log 2>&1 &
```

### 步骤 7: 验证服务
```bash
# 检查服务状态
curl http://localhost:8000/health
# 预期输出: {"status":"ok"}

# 检查紧急状态端点
curl http://localhost:8000/emergency
# 预期输出: {"count":0,"positions":[]}

# 检查日志
tail -f tw168.log | grep -E "ws|emergency|retry"
```

---

## 🔍 部署后验证

### 1. WebSocket 连接验证
```bash
# 观察日志中的 WebSocket 连接信息
tail -f tw168.log | grep "ws"

# 预期看到:
# - "OKX candle ws subscribed to XX symbols"
# - "OKX fill ws connected and subscribed"
# - "Extended fill ws connected and subscribed"
```

### 2. 异常重试验证
```bash
# 等待下次 API 调用,观察是否有重试日志
tail -f tw168.log | grep "retry"

# 如果出现网络问题,应该看到:
# - "OKX API request failed (attempt 1/3), retrying in 1s"
# - "OKX API request failed (attempt 2/3), retrying in 2s"
```

### 3. 紧急处理验证
```bash
# 定期检查紧急状态
watch -n 10 'curl -s http://localhost:8000/emergency | jq'

# 如果 count > 0,立即检查 Telegram 告警
```

---

## ⚠️ 监控要点

### 关键日志关键词
```bash
# 设置告警监控这些关键词
tail -f tw168.log | grep -E --color=always \
  "CRITICAL|emergency|consecutive_errors|max_retry|sl_order_failed"
```

### 监控脚本 (crontab)
```bash
# 添加到 crontab (每 5 分钟检查)
*/5 * * * * /home/ubuntu/tw168/scripts/check_emergency.sh
```

**check_emergency.sh 内容:**
```bash
#!/bin/bash
EMERGENCY_COUNT=$(curl -s http://localhost:8000/emergency | jq -r '.count')
if [ "$EMERGENCY_COUNT" -gt 0 ]; then
    echo "⚠️ ALERT: $EMERGENCY_COUNT emergency positions detected at $(date)" | \
        tee -a /var/log/tw168_emergency.log
    # 可以在这里添加额外的告警机制 (邮件、短信等)
fi
```

---

## 🐛 故障排查

### 问题 1: WebSocket 频繁重连
**症状:** 日志中出现大量 "reconnecting in Xs"

**检查:**
```bash
# 查看连续错误计数
tail -f tw168.log | grep "consecutive"

# 如果接近 10 次,说明有持续性网络问题
```

**解决:**
- 检查网络连接: `ping ws.okx.com`
- 检查防火墙规则
- 增加 `max_consecutive_errors` (在 candle_cache.py)

### 问题 2: 止损单持续失败
**症状:** `/emergency` 端点显示多个仓位

**检查:**
```bash
# 查看止损失败原因
curl http://localhost:8000/emergency | jq '.positions[].failure_reason'

# 查看止损成功率
curl http://localhost:8000/metrics | jq '.sl_failure_rate'
```

**解决:**
- 如果是 API 限流: 降低交易频率
- 如果是权限问题: 检查 API key 权限
- 如果是网络问题: 启用 BACKUP_SL_ENABLED

### 问题 3: OKX API 重试失败
**症状:** 大量 "OKX API failed after 3 attempts"

**检查:**
```bash
# 查看具体错误
tail -f tw168.log | grep "OKX API.*error"

# 检查 API 状态
curl https://www.okx.com/api/v5/system/status
```

**解决:**
- 增加重试次数 (修改 okx.py max_retries)
- 增加超时时间 (修改 timeout 参数)
- 检查 API key 是否被限流

---

## 📊 性能监控

### 关键指标
```bash
# 每小时记录一次
cat >> /var/log/tw168_metrics.log << EOF
$(date): $(curl -s http://localhost:8000/metrics)
EOF

# 分析止损成功率
curl -s http://localhost:8000/metrics | jq '.sl_failure_rate'

# 分析紧急平仓次数
curl -s http://localhost:8000/metrics | jq '.emergency_closes_total'
```

---

## 🔄 回滚计划

如果部署后出现严重问题:

### 快速回滚
```bash
# 1. 停止服务
sudo supervisorctl stop tw168

# 2. 恢复备份
cd /home/ubuntu/tw168
rm -rf app
mv app.backup.YYYYMMDD_HHMMSS app
cp .env.backup.YYYYMMDD_HHMMSS .env

# 3. 重启服务
sudo supervisorctl start tw168

# 4. 验证
curl http://localhost:8000/health
```

---

## 📞 紧急联系

### 告警渠道优先级
1. **Telegram Bot** (实时告警) - 最高优先级
2. **/emergency 端点** (主动查询)
3. **日志文件** (事后分析)

### 手动干预流程
如果收到 CRITICAL 告警:

1. **立即检查** `/emergency` 端点
2. **登录交易所** 查看实际仓位
3. **手动设置止损** (如果自动失败)
4. **记录问题** 到日志
5. **事后分析** 失败原因

---

## ✅ 部署完成确认

- [ ] 代码已同步
- [ ] 依赖已安装
- [ ] 配置已更新
- [ ] 服务已重启
- [ ] /health 端点正常
- [ ] /emergency 端点正常
- [ ] /metrics 端点正常
- [ ] WebSocket 连接正常
- [ ] 日志无异常错误
- [ ] Telegram 告警测试通过
- [ ] 监控脚本已配置

---

## 📝 部署记录

**部署人员:** ___________________

**部署时间:** ___________________

**备份位置:** ___________________

**验证结果:**
- [ ] 通过
- [ ] 失败 (原因: _______________)

**备注:**
```
_____________________________________
_____________________________________
_____________________________________
```

---

**重要提醒: 部署后至少观察 24 小时,密切关注日志和告警!**
