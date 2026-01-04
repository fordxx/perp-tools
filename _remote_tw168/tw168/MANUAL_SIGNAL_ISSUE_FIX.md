# 手动信号挂单成交后止盈止损未设置 - 问题修复

## 问题描述

手动信号成功开单（使用挂单模式），但挂单成交后**没有自动设置止盈止损单**。

---

## 根本原因

**Lighter API 被限流（HTTP 429 Too Many Requests）**

系统配置的轮询频率过高，导致：
1. `ENTRY_TWO_LIMIT_POLL_SECONDS=1.0` - 每秒查询一次持仓
2. `EXTENDED_REFRESH_SECONDS=60` - 每 60 秒刷新止盈止损
3. `MANAGER_POLL_SECONDS=2` - 每 2 秒轮询订单状态
4. **总请求频率**超过 Lighter API 限制 → **429 错误** → 无法查询持仓 → 无法检测挂单成交 → **止盈止损未设置**

---

## 已修复配置

### 调整的参数

| 参数 | 原值 | 新值 | 说明 |
|-----|------|------|------|
| `ENTRY_TWO_LIMIT_POLL_SECONDS` | 1.0 | **3.0** | 挂单成交监控间隔（秒） |
| `EXTENDED_REFRESH_SECONDS` | 60 | **120** | 止盈止损刷新间隔（秒） |
| `MANAGER_POLL_SECONDS` | 2 | **5** | 订单管理轮询间隔（秒） |

### API 调用频率对比

**修复前**:
- 挂单监控: 1 次/秒
- SL/TP 刷新: 1 次/60秒
- 订单管理: 1 次/2秒
- **峰值**: ~1.5 次/秒 → **触发限流**

**修复后**:
- 挂单监控: 1 次/3秒
- SL/TP 刷新: 1 次/120秒
- 订单管理: 1 次/5秒
- **峰值**: ~0.54 次/秒 → **安全范围内**

---

## 工作流程说明

### 手动信号处理流程（Two-Limit Entry 模式）

```
1. 接收手动信号 (/manual/signal)
   ↓
2. 计算入场价格和止损价格
   ↓
3. 下两个限价挂单（L1: 70%, L2: 30%）
   - L1: entry - 0.2*(entry-SL)
   - L2: entry - 0.6*(entry-SL)
   ↓
4. 启动后台任务 _monitor_entry_and_set_protection
   ↓
5. 每 3 秒轮询一次持仓状态
   ↓
6. 检测到持仓 > 0（挂单成交）
   ↓
7. 计算实际成交价和止损
   ↓
8. 自动设置止盈止损单
   - SL: 止损单（reduce-only）
   - TP1/TP2/TP3/TP4: 止盈梯度单
   ↓
9. 任务完成
```

### 超时机制

- **超时时间**: `ENTRY_TWO_LIMIT_TIMEOUT_CANDLES` × 时间周期
- **示例**:
  - 15m 周期: 1.0 × 15 = 15 分钟超时
  - 1h 周期: 1.5 × 60 = 90 分钟超时（配置：`1h:1.5`）
  - 4h 周期: 1.0 × 240 = 240 分钟超时（配置：`4h:1`）
- **超时后**: 自动取消未成交的挂单

---

## 验证步骤

### 1. 检查容器状态

```bash
ssh ubuntu@3.38.98.169 "docker ps | grep tv-okx"
# 应显示: Up X seconds
```

### 2. 查看实时日志

```bash
ssh ubuntu@3.38.98.169 "docker logs -f tw168-tv-okx-1"
```

**期望看到**:
- ✅ `two_limit_orders_placed` - 挂单成功
- ✅ `two_limit_filled_price` - 检测到成交
- ✅ `two_limit_protection_set` - 止盈止损已设置
- ❌ 不再出现 `429 Too Many Requests`

### 3. 发送测试信号

```bash
# 从本地机器
python3 send_manual_signal.py ETH-USDT-SWAP long -t 15m
```

### 4. 监控后台任务

```bash
# 远程执行
ssh ubuntu@3.38.98.169 "docker logs tw168-tv-okx-1 --tail 50 | grep -E 'two_limit|monitor|protection'"
```

---

## 常见问题排查

### 问题 1: 仍然出现 429 错误

**原因**: 其他程序也在调用 Lighter API

**解决**:
```bash
# 进一步降低轮询频率
ssh ubuntu@3.38.98.169
cd ~/tw168
nano .env

# 修改为更保守的值
ENTRY_TWO_LIMIT_POLL_SECONDS=5.0
EXTENDED_REFRESH_SECONDS=180
MANAGER_POLL_SECONDS=10

# 重启容器
docker compose restart tv-okx
```

### 问题 2: 挂单长时间未成交

**原因**: 市场价格未触及挂单价格

**检查**:
```bash
# 查看挂单价格计算
ssh ubuntu@3.38.98.169 "docker logs tw168-tv-okx-1 | grep -A5 'two_limit_orders_placed'"
```

**解决方案**:
- 调整 `ENTRY_TWO_LIMIT_L1_R` 和 `ENTRY_TWO_LIMIT_L2_R`（减小距离）
- 或使用 market order 模式（禁用 two-limit）

### 问题 3: 挂单被自动取消

**原因**: 超时未成交

**检查配置**:
```bash
grep ENTRY_TWO_LIMIT_TIMEOUT_CANDLES ~/tw168/.env
# ENTRY_TWO_LIMIT_TIMEOUT_CANDLES=1.0
# ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF=30m:2,1h:1.5,4h:1
```

**调整超时时间**（如果需要更长等待）:
```bash
# 编辑配置
nano ~/tw168/.env

# 示例: 15m 周期等待 2 个 K 线
ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF=15m:2,30m:2,1h:1.5,4h:1

# 重启
docker compose restart tv-okx
```

---

## 替代方案：使用 Market Order 模式

如果挂单模式经常未成交，可以改用市价单（立即成交）：

```bash
# 远程执行
cd ~/tw168
nano .env

# 禁用 two-limit 模式
ENTRY_TWO_LIMIT_ENABLED=false

# 重启
docker compose restart tv-okx
```

**优点**:
- ✅ 立即成交
- ✅ 无需监控挂单
- ✅ 降低 API 调用频率

**缺点**:
- ❌ 滑点风险
- ❌ 可能成交价格不理想

---

## 监控与日志

### 实时监控脚本

```bash
#!/bin/bash
# monitor_manual_signals.sh

ssh ubuntu@3.38.98.169 << 'REMOTE_EOF'
echo "=== 监控手动信号处理（按 Ctrl+C 退出） ==="
docker logs -f tw168-tv-okx-1 2>&1 | grep --line-buffered -E "manual.*signal|two_limit|protection|429"
REMOTE_EOF
```

### 检查最近的止盈止损设置

```bash
ssh ubuntu@3.38.98.169 "docker logs tw168-tv-okx-1 --tail 200 | grep -A10 'protection_set'"
```

### 检查 API 限流情况

```bash
ssh ubuntu@3.38.98.169 "docker logs tw168-tv-okx-1 --tail 500 | grep -c '429'"
# 输出应该是 0 或很小的数字
```

---

## 性能优化建议

### 当前配置（已优化）

适用于**偶尔手动开单**的场景：
- 挂单监控: 每 3 秒
- 止盈止损刷新: 每 2 分钟
- 订单管理: 每 5 秒

### 如果需要频繁开单

```bash
# 可以适当提高轮询频率（但不要低于 2 秒）
ENTRY_TWO_LIMIT_POLL_SECONDS=2.0
MANAGER_POLL_SECONDS=3
```

### 如果需要降低 API 使用

```bash
# 关闭非必要的刷新
EXTENDED_REFRESH_ENABLED=false

# 或延长刷新间隔
EXTENDED_REFRESH_SECONDS=300  # 5 分钟
```

---

## 配置文件位置

| 文件 | 路径 | 说明 |
|-----|------|------|
| 环境配置 | `~/tw168/.env` | 主配置文件 |
| 配置备份 | `~/tw168/.env.bak.*` | 自动备份 |
| 容器日志 | `docker logs tw168-tv-okx-1` | 实时日志 |
| 应用日志 | `~/tw168/logs/` | 持久化日志 |

---

## 总结

### ✅ 已修复
- 降低 API 轮询频率（避免 429 限流）
- 调整挂单监控间隔（1秒 → 3秒）
- 调整止盈止损刷新间隔（60秒 → 120秒）
- 调整订单管理轮询间隔（2秒 → 5秒）

### 🔍 后续监控
1. 发送测试信号，观察日志确认止盈止损正常设置
2. 检查是否仍有 429 错误
3. 如有问题，参考上述排查步骤

### 📊 预期效果
- ✅ 挂单成交后自动设置止盈止损
- ✅ 超时未成交自动取消挂单
- ✅ 不再出现 API 限流错误
- ✅ 系统稳定运行

---

**如遇问题，请提供以下日志**:
```bash
ssh ubuntu@3.38.98.169 "docker logs tw168-tv-okx-1 --tail 200" > debug.log
```
