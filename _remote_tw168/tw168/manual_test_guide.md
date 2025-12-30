# 完整交易流程 - 手动测试指南

## 📋 测试流程

本指南将引导你完成从 ZONE 信号到平仓的完整交易测试。

---

## Step 1: 发送 ZONE 信号 (开仓)

### 1.1 获取当前价格

```bash
cd /home/ubuntu/tw168
docker compose exec -T tv-okx python3 << 'EOF'
import sys
sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()
quote = client.get_current_price('EIGEN/USDT')
print(f'EIGEN Price: ${quote.mid:.5f}')
EOF
```

### 1.2 发送 ZONE webhook

```bash
# 替换 <PRICE> 为上一步获取的价格
curl -X POST http://localhost:8000/tradingview/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EIGEN",
    "timeframe": "30m",
    "zone": "OVERSOLD",
    "price": <PRICE>,
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }'
```

**示例**:
```bash
curl -X POST http://localhost:8000/tradingview/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EIGEN",
    "timeframe": "30m",
    "zone": "OVERSOLD",
    "price": 0.374,
    "timestamp": "2025-12-30T11:00:00Z"
  }'
```

### 1.3 等待订单处理

```bash
# 等待 15 秒
sleep 15
```

### 1.4 检查持仓

```bash
docker compose exec -T tv-okx python3 << 'EOF'
import sys
sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()

positions = client.get_account_positions()
eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

if not eigen_positions:
    print('⚠️  没有 EIGEN 持仓')
else:
    print(f'✅ 找到 {len(eigen_positions)} 个 EIGEN 持仓:')
    for i, pos in enumerate(eigen_positions, 1):
        print(f'\n持仓 {i}:')
        print(f'  Symbol: {pos.order.symbol}')
        print(f'  Side: {pos.order.side}')
        print(f'  Size: {pos.order.size}')
        print(f'  Entry Price: {pos.order.price:.5f}')
EOF
```

### 1.5 查看日志

```bash
# 查看最近的 EIGEN 相关日志
docker compose logs --tail 100 | grep -i eigen
```

**预期结果**:
- ✅ Ladder L1/L2/L3 订单已创建
- ✅ 部分或全部订单已成交
- ✅ 看到持仓信息

---

## Step 2: 发送 DIV 信号 (设置止损/止盈)

### 2.1 发送 DIV webhook

```bash
# 使用与 ZONE 相同的价格
curl -X POST http://localhost:8000/tradingview/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EIGEN",
    "timeframe": "30m",
    "divergence_type": "BULLISH",
    "price": <PRICE>,
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }'
```

**示例**:
```bash
curl -X POST http://localhost:8000/tradingview/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "EIGEN",
    "timeframe": "30m",
    "divergence_type": "BULLISH",
    "price": 0.374,
    "timestamp": "2025-12-30T11:01:00Z"
  }'
```

### 2.2 等待止损/止盈处理

```bash
# 等待 15 秒
sleep 15
```

### 2.3 查看日志验证

```bash
docker compose logs --tail 100 | grep -i -E 'stop|profit|sl|tp'
```

**预期结果**:
- ✅ 看到 "Setting stop loss" 日志
- ✅ 看到 "Setting take profit" 日志
- ✅ 止损/止盈订单已创建

### 2.4 在 Lighter 平台验证

访问: https://mainnet.zklighter.elliot.ai/

- 检查 **Open Orders** - 应该看到止损/止盈订单
- 检查 **Positions** - 应该看到 EIGEN 持仓

---

## Step 3: 验证持仓状态

### 3.1 检查详细持仓信息

```bash
docker compose exec -T tv-okx python3 << 'EOF'
import sys
sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()

print('📊 当前持仓状态:\n')

positions = client.get_account_positions()
eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

if not eigen_positions:
    print('⚠️  没有持仓')
else:
    for i, pos in enumerate(eigen_positions, 1):
        print(f'持仓 {i}:')
        print(f'  Symbol: {pos.order.symbol}')
        print(f'  Size: {pos.order.size}')
        print(f'  Entry Price: {pos.order.price:.5f}')
        print(f'  Side: {pos.order.side}')
        print()

quote = client.get_current_price('EIGEN/USDT')
print(f'当前价格: ${quote.mid:.5f}')
EOF
```

---

## Step 4: 平仓测试

### 4.1 手动平仓

```bash
# 使用之前的 clear_eigen.py 脚本
cat > /tmp/close_eigen.py << 'PYEOF'
import sys
sys.path.insert(0, '/src')
import asyncio
from perpbot.exchanges.lighter import LighterClient

async def close_all():
    client = LighterClient(use_testnet=False)
    client.connect()

    quote = client.get_current_price('EIGEN/USDT')
    print(f'当前价格: ${quote.mid:.5f}')

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if not eigen_positions:
        print('没有持仓需要平仓')
        return

    print(f'\n平仓 {len(eigen_positions)} 个持仓...')

    for i, pos in enumerate(eigen_positions, 1):
        print(f'\n平仓 {i}: {pos.order.symbol} {pos.order.size}')
        try:
            close_order = client.place_close_order(pos, quote.mid)
            print(f'✅ 平仓订单: {close_order.id}')
            await asyncio.sleep(2)
        except Exception as e:
            print(f'❌ 失败: {e}')

    await asyncio.sleep(3)

    final_positions = client.get_account_positions()
    final_eigen = [p for p in final_positions if 'EIGEN' in p.order.symbol]

    if not final_eigen:
        print('\n✅ 所有持仓已平仓!')
    else:
        print(f'\n⚠️  还剩 {len(final_eigen)} 个持仓')

asyncio.run(close_all())
PYEOF

# 在远程服务器上执行
docker compose exec -T tv-okx python3 < /tmp/close_eigen.py
```

### 4.2 验证最终状态

```bash
docker compose exec -T tv-okx python3 << 'EOF'
import sys
sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()

positions = client.get_account_positions()
eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

if not eigen_positions:
    print('✅ 所有 EIGEN 持仓已清空')
else:
    print(f'⚠️  还有 {len(eigen_positions)} 个持仓:')
    for p in eigen_positions:
        print(f'  - {p.order.symbol}: {p.order.size}')
EOF
```

---

## 📊 预期测试结果

### 成功标志

1. **ZONE 信号**:
   - ✅ 3 个 Ladder 订单创建 (L1: 50%, L2: 30%, L3: 20%)
   - ✅ 至少部分订单成交
   - ✅ 看到持仓信息

2. **DIV 信号**:
   - ✅ 止损订单创建
   - ✅ 止盈订单创建
   - ✅ 日志显示 "SL attached" 和 "TP attached"

3. **平仓**:
   - ✅ 平仓订单成交
   - ✅ 持仓清空

### 可能遇到的问题

#### 问题 1: Ladder 订单未成交

**原因**: 价格已经移动，订单价格不再有竞争力

**解决**:
- 等待更长时间
- 或手动撤销未成交的订单
- 或降低 Ladder 间距 (修改 .env 中的 LADDER_LEVEL*_BPS)

#### 问题 2: "invalid nonce" 错误

**原因**: 市价单的 nonce 管理问题 (已知 bug)

**解决**:
- 这个问题影响市价单
- Ladder 限价单应该正常工作
- 如果出现，等待几秒重试

#### 问题 3: 止损/止盈未设置

**原因**:
- Lighter API 可能需要特殊参数
- 或者功能未完全实现

**解决**:
- 检查日志中的错误信息
- 手动在 Lighter 平台上设置

---

## 🔍 调试命令

### 查看所有日志
```bash
docker compose logs -f
```

### 只看 EIGEN 相关
```bash
docker compose logs -f | grep -i eigen
```

### 看错误日志
```bash
docker compose logs | grep -i error
```

### 查看最近 webhook 请求
```bash
docker compose logs --tail 100 | grep -i webhook
```

---

## ✅ 运维指令：强制平仓并清理挂单（CLOSE）

用途：不依赖 TradingView 信号，直接触发“撤单 + 市价平仓”。  
适用于紧急处理或完整流程验证的最后一步。

```bash
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret":"<YOUR_SECRET>",
    "type":"CLOSE",
    "instId":"EIGEN-USDT-SWAP",
    "tf":"30m",
    "t":"'"$(date +%s)000"'"
  }'
```

期望日志：
- `cancel_pending_orders ... count=...`
- `canceled_pending_order ...`
- `state cleared_pending_orders ...`
- `action=close_order ...`

---

## 📝 测试记录模板

```
测试日期: ____
测试币种: EIGEN
测试时段: 30m

=== ZONE 信号 ===
发送时间: ____
信号价格: ____
Ladder L1: [ ] 已创建 [ ] 已成交
Ladder L2: [ ] 已创建 [ ] 已成交
Ladder L3: [ ] 已创建 [ ] 已成交
总持仓: ____

=== DIV 信号 ===
发送时间: ____
止损价格: ____
止损状态: [ ] 已创建 [ ] 生效中
止盈价格: ____
止盈状态: [ ] 已创建 [ ] 生效中

=== 平仓 ===
平仓时间: ____
平仓价格: ____
平仓状态: [ ] 成功 [ ] 部分成功 [ ] 失败

=== 遇到的问题 ===
____________________

=== 总成本 ===
手续费: ____
盈亏: ____
```

---

**一句话总结**: 通过 curl 发送 ZONE 和 DIV webhook，观察 Ladder 开仓、止损/止盈设置，最后手动平仓验证完整流程！
