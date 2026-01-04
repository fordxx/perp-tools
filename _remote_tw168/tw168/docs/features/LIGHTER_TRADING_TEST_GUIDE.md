# Lighter 完整交易测试指南

## 📋 测试现状

### ✅ 已完成的测试
1. **接口完整性测试** - `get_position()` 方法存在性和签名
2. **格式转换测试** - OKX ↔ Lighter 格式互转
3. **Mock 单元测试** - 基本功能逻辑验证

### ❌ 未完成的测试（关键！）
以下是**真实交易流程**，目前**尚未测试**：

| 功能 | 状态 | 风险等级 | 说明 |
|------|------|---------|------|
| 开仓 (市价单) | ❌ 未测试 | 🔴 高 | 可能失败导致无法交易 |
| 开仓 (限价单) | ❌ 未测试 | 🔴 高 | Ladder 订单依赖此功能 |
| 开仓 (Ladder 阶梯单) | ❌ 未测试 | 🔴 高 | 当前配置启用，未验证 |
| 止损单 (SL) | ❌ 未测试 | 🔴 极高 | 无止损 = 爆仓风险！ |
| 止盈单 (TP) | ❌ 未测试 | 🟡 中 | 影响盈利能力 |
| 移动止损 (Trailing SL) | ❌ 未测试 | 🟡 中 | 当前配置启用 |
| 平仓 (市价) | ❌ 未测试 | 🔴 高 | 无法平仓 = 锁死资金 |
| 撤单 | ❌ 未测试 | 🟡 中 | Ladder 订单需要撤单 |
| 获取持仓 | ✅ 已测试 | ✅ 低 | 早上修复并验证 |
| 获取订单 | ❌ 未测试 | 🟡 中 | 订单管理依赖 |

## 🚨 当前风险评估

### 极高风险 ⚠️
**止损单未测试** - 如果止损单设置失败：
- 早上收到信号 → 开仓成功 → **止损失败**
- 价格反向波动 → **没有保护**
- 潜在损失：**无限（直到手动介入）**

### 高风险 🔴
**开仓/平仓未测试** - 如果失败：
- 开仓失败 → 错过交易机会（机会成本）
- 平仓失败 → 无法止盈/止损（资金锁死）

### 中风险 🟡
**Ladder 订单未测试**：
- 当前 `.env` 配置：
  ```
  LADDER_ENABLED=true
  LADDER_LEVEL1_BPS=5
  LADDER_LEVEL1_PCT=0.50
  LADDER_LEVEL2_BPS=15
  LADDER_LEVEL2_PCT=0.30
  LADDER_LEVEL3_BPS=30
  LADDER_LEVEL3_PCT=0.20
  ```
- 如果 Ladder 限价单失败 → 仓位未完全开启 → 收益降低

## 🧪 测试建议

### 方案 A: 最小风险测试（推荐）
使用**极小仓位**在真实环境测试完整流程：

```bash
# 1. 在容器内运行测试（真实交易！）
cd /home/ubuntu/tw168
docker compose exec tv-okx python3 /app/test_lighter_full_trading_cycle.py \
  --symbol EIGEN/USDT \
  --size 10

# 预估成本：
# - 开仓: 10 张 EIGEN @ $3.5 = $35
# - 风险: 2% SL = $0.70
# - 手续费: ~$0.10 (Taker 0.06%)
# - 总风险: < $1
```

**测试覆盖**：
1. ✅ 市价开仓
2. ✅ 止损单设置
3. ✅ 止盈单设置
4. ✅ 限价撤单
5. ✅ 市价平仓

### 方案 B: 分步骤测试
逐步验证每个功能：

#### Step 1: 只测试开仓 + 平仓
```python
# 手动执行 Python 代码
docker compose exec -it tv-okx python3
```

```python
import sys
sys.path.insert(0, "/src")
from perpbot.exchanges.lighter import LighterClient
from perpbot.models import OrderRequest

# 连接
client = LighterClient(use_testnet=False)
client.connect()

# 获取价格
quote = client.get_current_price("EIGEN/USDT")
print(f"当前价格: {quote.mid}")

# 开仓 (10 张)
request = OrderRequest(
    symbol="EIGEN/USDT",
    side="buy",
    size=10.0,
    limit_price=None  # 市价
)
order = client.place_open_order(request)
print(f"开仓订单: {order}")

# 等待确认...
import time
time.sleep(5)

# 查看持仓
positions = client.get_account_positions()
for pos in positions:
    if pos.order.symbol == "EIGEN/USDT":
        print(f"持仓: {pos}")

# 平仓
# TODO: 等确认开仓成功后手动执行
```

#### Step 2: 测试止损单
```python
# 获取持仓
positions = client.get_account_positions()
eigen_pos = [p for p in positions if p.order.symbol == "EIGEN/USDT"][0]

# 设置止损 (比入场价低 2%)
entry_price = eigen_pos.order.price
sl_price = entry_price * 0.98

# TODO: 调用 Lighter 止损 API
# 注意: Lighter 可能需要特定的条件单 API
print(f"止损价: {sl_price}")
```

#### Step 3: 测试 Ladder 订单
```python
# 模拟 main.py 的 Ladder 逻辑
signal_price = 3.50

# Level 1: 0.05% from signal, 50% of position
level1_price = signal_price * (1 + 0.0005)
level1_size = 10 * 0.50

# Level 2: 0.15% from signal, 30% of position
level2_price = signal_price * (1 + 0.0015)
level2_size = 10 * 0.30

# Level 3: 0.30% from signal, 20% of position
level3_price = signal_price * (1 + 0.0030)
level3_size = 10 * 0.20

# 下 3 个限价单
for i, (price, size) in enumerate([
    (level1_price, level1_size),
    (level2_price, level2_size),
    (level3_price, level3_size)
], 1):
    request = OrderRequest(
        symbol="EIGEN/USDT",
        side="buy",
        size=size,
        limit_price=price
    )
    order = client.place_open_order(request)
    print(f"Ladder Level {i}: {order.id} @ {price:.4f}")
```

### 方案 C: 等待真实信号测试
**最保守但最慢**：
- 等待下一个 TradingView 信号
- 让系统自动执行
- 监控日志观察是否成功

**优点**：
- 真实场景
- 不需要手动操作

**缺点**：
- 可能等很久（小时到天）
- 如果失败，损失真实交易机会
- 无法控制测试时机

## 📝 测试前检查清单

### 环境检查
- [ ] `.env` 配置正确（API keys, 风险参数）
- [ ] Docker 容器运行正常
- [ ] Lighter API 连接正常
- [ ] 账户有足够余额（至少 $50 USDT）

### 风险确认
- [ ] 理解这是**真实交易**，会产生真实成本
- [ ] 准备好紧急手动平仓（通过 Lighter 界面）
- [ ] 设置资金上限（建议 $5-10 风险）
- [ ] 监控测试过程（不要离开）

### 测试准备
- [ ] 选择流动性好的币种（EIGEN, TON, BTC, ETH）
- [ ] 选择波动较小的时段（避免重大新闻）
- [ ] 准备 Lighter 界面备用（https://app.lighter.xyz）

## 🎯 推荐测试计划

### 第一阶段：基础功能（今天）
1. ✅ 连接测试
2. ✅ get_position 测试
3. 🔴 **开仓 + 平仓测试**（10 张 EIGEN，风险 < $1）

### 第二阶段：风控功能（明天）
4. 🔴 **止损单测试**（最关键！）
5. 🟡 止盈单测试
6. 🟡 撤单测试

### 第三阶段：高级功能（后天）
7. 🟡 Ladder 订单测试
8. 🟡 移动止损测试
9. ✅ 完整周期测试（ZONE + DIV 信号）

## 🚀 执行测试

### 现在就可以做的测试（无需真实交易）
```bash
# 1. 测试连接
docker compose exec -it tv-okx python3 -c "
import sys; sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient
client = LighterClient(use_testnet=False)
client.connect()
print('✅ 连接成功')
balances = client.get_account_balances()
for bal in balances[:3]:
    print(f'{bal.asset}: {bal.free:.2f}')
"

# 2. 测试 get_position（我们修复的功能）
docker compose exec -it tv-okx python3 -c "
import sys; sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient
client = LighterClient(use_testnet=False)
client.connect()
result = client.get_position(inst_id='EIGEN-USDT-SWAP', pos_side='long')
print(f'EIGEN 多仓: {result}')
"
```

### 真实交易测试（需要确认）
```bash
# 完整测试脚本（会询问确认）
cd /home/ubuntu/tw168
docker compose exec -it tv-okx python3 /app/test_lighter_full_trading_cycle.py \
  --symbol EIGEN/USDT \
  --size 10
```

## ⚠️ 测试注意事项

### DO
- ✅ 使用极小仓位测试（10-20 张）
- ✅ 选择流动性好的币种
- ✅ 测试时全程监控
- ✅ 准备好手动操作备份方案
- ✅ 记录所有测试结果

### DON'T
- ❌ 不要在重大新闻前后测试
- ❌ 不要使用大仓位测试
- ❌ 不要测试流动性差的小币种
- ❌ 不要在高波动时段测试
- ❌ 不要离开让测试自动运行

## 📊 测试结果记录

### 建议记录内容
```
测试日期: ____
测试币种: ____
测试仓位: ____
入场价: ____
止损价: ____
止盈价: ____

测试结果:
[ ] 开仓成功
[ ] 止损设置成功
[ ] 止盈设置成功
[ ] 平仓成功

遇到的问题:
_______________

总成本: ____
```

## 🆘 测试失败应急方案

### 如果开仓失败
1. 检查日志: `docker compose logs -f | grep ERROR`
2. 检查 Lighter 余额
3. 检查 API 权限
4. 尝试更小仓位

### 如果止损失败
**紧急！立即手动处理：**
1. 访问 https://app.lighter.xyz
2. 手动设置止损单
3. 或准备手动平仓

### 如果平仓失败
1. 通过 Lighter 界面手动平仓
2. 检查持仓是否真的存在
3. 检查 API 日志

## 📞 下一步行动

### 立即行动（优先级）
1. 🔴 **决定是否执行真实交易测试**
   - 如果是 → 准备 $5-10 风险资金
   - 如果否 → 等待真实信号被动测试

2. 🔴 **测试止损功能**（最关键！）
   - 没有止损 = 系统不安全
   - 这是最大的未知风险

3. 🟡 测试开仓/平仓基本功能

---

**总结**: 我们修复了 `get_position()` 缺失的问题，但整个交易流程（开仓、止损、止盈、平仓）都**尚未在真实环境验证**。建议尽快用极小仓位测试，特别是**止损功能**！
