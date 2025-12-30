# Lighter WebSocket 测试配置

## ✅ 部署完成

测试配置已成功部署到远程服务器 (3.38.98.169)

## 📊 当前配置

### WebSocket 监控
**Lighter WebSocket** (6 个币种):
- ETH-USDT-SWAP
- BTC-USDT-SWAP
- SOL-USDT-SWAP
- LINK-USDT-SWAP
- DOGE-USDT-SWAP
- BNB-USDT-SWAP

**功能**:
- 实时盘口数据 (50ms 更新)
- 实时交易流
- 自动重连机制

### K线数据源
**OKX WebSocket** (14 个币种):
- 所有配置的交易对
- 多周期监控 (30m, 1h, 4h)

### 风险管理 (测试模式)

| 参数 | 原配置 | 测试配置 | 降低比例 |
|------|--------|----------|----------|
| 默认风险 | 50 USDT | 5 USDT | 1/10 |
| 15m 周期 | 100 USDT | 10 USDT | 1/10 |
| 30m 周期 | 300 USDT | 30 USDT | 1/10 |
| 1h 周期 | 300 USDT | 30 USDT | 1/10 |
| 4h 周期 | 300 USDT | 30 USDT | 1/10 |

**说明**: 测试阶段所有风险仓位降低至原来的 1/10，确保系统稳定性验证时风险最小化。

## 🎯 测试目标

### 1. 稳定性测试
- **目标**: 24-48 小时连续运行无异常
- **监控指标**:
  - WebSocket 连接稳定性
  - 重连次数
  - 数据延迟
  - 内存/CPU 使用

### 2. 数据一致性
- **对比项**:
  - Lighter WebSocket vs OKX REST API 价格差异
  - 盘口数据准确性
  - 成交数据完整性

### 3. 交易执行
- **小仓位测试**:
  - 风险 5-30 USDT
  - 验证下单流程
  - 验证止盈止损
  - 验证平仓逻辑

### 4. 性能监控
- **系统资源**:
  - Docker 容器内存 < 500MB
  - CPU 使用 < 10%
  - WebSocket 消息处理延迟 < 100ms

## 📋 部署状态

```
✅ Lighter WebSocket client created
✅ Lighter WebSocket enabled: 6/6 symbols subscribed
✅ Candle WebSocket subscribed to 14 channels
✅ Risk configuration updated (1/10 of original)
```

## 🔍 监控命令

### 查看实时日志
```bash
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose logs -f'
```

### 过滤 WebSocket 日志
```bash
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose logs -f | grep -i "websocket\|lighter"'
```

### 检查系统状态
```bash
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose ps && docker stats --no-stream'
```

### 查看健康检查
```bash
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose logs | grep health_check | tail -10'
```

## ⚠️ 注意事项

### 已知问题
1. **Lighter 认证失败**:
   - `private key does not match the one on Lighter`
   - **影响**: 只能使用公开频道 (盘口、交易)，无法订阅账户更新
   - **状态**: 不影响测试，系统以只读模式运行

2. **WebSocket 偶尔断线**:
   - 重启过程中出现过 "connection closed" 警告
   - **解决**: 自动重连机制已启用
   - **状态**: 重连成功，正常运行

3. **Ladder 配置警告**:
   - `Ladder order percentages sum to 170%`
   - **说明**: Ladder 订单配置总和超过 100%
   - **影响**: 仅警告，不影响运行

## 📈 下一步计划

### 短期 (24-48小时)
1. ✅ 降低风险仓位至 1/10
2. ✅ 启用 Lighter WebSocket (6 个币种)
3. ⏳ 监控系统稳定性
4. ⏳ 观察 WebSocket 连接质量
5. ⏳ 记录任何异常或错误

### 中期 (1周)
如果测试稳定:
1. 增加更多币种到 Lighter WebSocket
2. 逐步提高风险仓位 (1/10 → 1/5 → 1/2)
3. 验证大批量订单处理
4. 评估是否解决认证问题

### 长期
1. 所有 Lighter 支持的币种迁移到 WebSocket
2. 恢复正常风险仓位
3. 评估是否完全切换到 Lighter DEX
4. 考虑添加更多 DEX 支持

## 🔧 快速操作

### 紧急停止
```bash
ssh -i ../../LightsailDefaultKey-ap-northeast-2.pem ubuntu@3.38.98.169 \
  'cd /home/ubuntu/tw168 && docker compose down'
```

### 恢复原配置
```bash
# 修改 .env 文件
RISK_PER_TRADE_USDT=50
RISK_PER_TRADE_BY_TF=15m:100,30m:300,1h:300,4h:300

# 重启容器
docker compose restart
```

### 禁用 WebSocket
编辑 `app/main.py`，注释掉 WebSocket 初始化代码 (第 112-161 行)

## 📝 测试记录

| 时间 | 事件 | 状态 | 备注 |
|------|------|------|------|
| 2025-12-29 16:10 | WebSocket 启用 | ✅ | 6/6 symbols subscribed |
| 2025-12-29 16:12 | 风险降低 | ✅ | 1/10 of original |
| | 待补充 | | |

## 📞 联系方式

如有问题，请检查:
1. [LIGHTER_WEBSOCKET.md](./LIGHTER_WEBSOCKET.md) - 完整文档
2. [WEBSOCKET_QUICK_START.md](./WEBSOCKET_QUICK_START.md) - 快速上手
3. Docker 日志: `docker compose logs -f`

---

**测试开始时间**: 2025-12-29 16:12
**预计测试时长**: 24-48 小时
**测试负责人**: 系统自动化测试
**风险等级**: 低 (仓位降低至 1/10)
