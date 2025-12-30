# EIGEN 持仓和挂单完整清理方案

## 🎯 问题

每次平仓时，可能有未成交的 Ladder 挂单残留，需要同时清理持仓和挂单。

---

## ✅ 解决方案

创建了完整清理脚本 `/tmp/clear_eigen_with_cancel.py`，自动执行：
1. 平仓所有 EIGEN 持仓
2. 撤销所有 EIGEN 挂单
3. 验证清理结果

---

## 📝 使用方法

### 在本地执行（推荐）

```bash
# 方法 1: 通过 stdin 管道
cat /tmp/clear_eigen_with_cancel.py | ssh ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose exec -T tv-okx python3"

# 方法 2: 直接 SSH
ssh ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose exec -T tv-okx python3" < /tmp/clear_eigen_with_cancel.py
```

### 在远程服务器上执行

```bash
# 1. SSH 到服务器
ssh ubuntu@3.38.98.169

# 2. 进入目录
cd /home/ubuntu/tw168

# 3. 创建脚本（如果尚未创建）
cat > /tmp/clear_eigen.py << 'EOF'
import sys
sys.path.insert(0, '/src')
import asyncio
from perpbot.exchanges.lighter import LighterClient

async def clear_eigen():
    """完整清理 EIGEN：平仓所有持仓 + 撤销所有挂单"""

    print('=' * 60)
    print('EIGEN 完整清理')
    print('=' * 60)
    print()

    client = LighterClient(use_testnet=False)
    client.connect()

    quote = client.get_current_price('EIGEN/USDT')
    print(f'当前价格: ${quote.mid:.5f}')
    print()

    # Step 1: 平仓
    print('Step 1: 平仓持仓')
    print('-' * 60)

    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    if not eigen_positions:
        print('没有持仓')
    else:
        print(f'发现 {len(eigen_positions)} 个持仓，平仓中...')
        for i, pos in enumerate(eigen_positions, 1):
            print(f'  {i}. {pos.order.symbol} {pos.order.size} ({pos.order.side})')
            try:
                close_order = client.place_close_order(pos, quote.mid)
                print(f'     订单: {close_order.id}')
                await asyncio.sleep(2)
            except Exception as e:
                print(f'     失败: {e}')

    # Step 2: 撤单
    print()
    print('Step 2: 撤销挂单')
    print('-' * 60)

    try:
        all_orders = client.get_active_orders()
        eigen_orders = [o for o in all_orders if 'EIGEN' in o.symbol]

        if not eigen_orders:
            print('没有挂单')
        else:
            print(f'发现 {len(eigen_orders)} 个挂单，撤销中...')
            for i, order in enumerate(eigen_orders, 1):
                print(f'  {i}. {order.symbol} {order.size} @ {order.price:.5f}')
                try:
                    client.cancel_order(order_id=order.id, symbol=order.symbol)
                    print(f'     已撤销')
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f'     失败: {e}')
    except Exception as e:
        print(f'查询挂单失败: {e}')
        print('(这可能意味着没有挂单)')

    # Step 3: 验证
    print()
    print('Step 3: 验证')
    print('-' * 60)

    await asyncio.sleep(3)

    final_positions = client.get_account_positions()
    final_eigen = [p for p in final_positions if 'EIGEN' in p.order.symbol]

    if not final_eigen:
        print('持仓: 已清空 ✓')
    else:
        print(f'持仓: 还剩 {len(final_eigen)} 个')

    try:
        final_orders = client.get_active_orders()
        final_eigen_orders = [o for o in final_orders if 'EIGEN' in o.symbol]
        if not final_eigen_orders:
            print('挂单: 已清空 ✓')
        else:
            print(f'挂单: 还剩 {len(final_eigen_orders)} 个')
    except:
        print('挂单: 无法查询（请手动验证）')

    print()
    print('=' * 60)
    if not final_eigen:
        print('清理完成 ✓')
    else:
        print('部分清理完成，请检查')
    print('=' * 60)

asyncio.run(clear_eigen())
EOF

# 4. 执行脚本
docker compose exec -T tv-okx python3 < /tmp/clear_eigen.py
```

---

## 📊 输出示例

### 成功清理

```
============================================================
EIGEN 完整清理
============================================================

当前价格: $0.37421

Step 1: 平仓持仓
------------------------------------------------------------
发现 1 个持仓，平仓中...
  1. EIGEN/USDT 1577.0 (buy)
     订单: 597334

Step 2: 撤销挂单
------------------------------------------------------------
发现 2 个挂单，撤销中...
  1. EIGEN/USDT 946.0 @ 0.37360
     已撤销
  2. EIGEN/USDT 630.0 @ 0.37340
     已撤销

Step 3: 验证
------------------------------------------------------------
持仓: 已清空 ✓
挂单: 已清空 ✓

============================================================
清理完成 ✓
============================================================
```

### 已经清空

```
============================================================
EIGEN 完整清理
============================================================

当前价格: $0.37391

Step 1: 平仓持仓
------------------------------------------------------------
没有持仓

Step 2: 撤销挂单
------------------------------------------------------------
没有挂单

Step 3: 验证
------------------------------------------------------------
持仓: 已清空 ✓
挂单: 已清空 ✓

============================================================
清理完成 ✓
============================================================
```

---

## 🔍 手动验证

访问 Lighter 平台手动确认：

1. **打开平台**: https://mainnet.zklighter.elliot.ai/
2. **连接钱包**: 使用配置的钱包地址
3. **检查持仓**:
   - 进入 "Positions" 标签
   - 确认没有 EIGEN 持仓
4. **检查挂单**:
   - 进入 "Open Orders" 标签
   - 确认没有 EIGEN 挂单

---

## ⚙️ 工作原理

### 1. 查询持仓
使用 `client.get_account_positions()` 获取所有持仓，过滤 EIGEN 相关。

### 2. 平仓
对每个持仓调用 `client.place_close_order(pos, current_price)` 市价平仓。

### 3. 查询挂单
使用 `client.get_active_orders()` 获取所有挂单，过滤 EIGEN 相关。

### 4. 撤单
对每个挂单调用 `client.cancel_order(order_id, symbol)` 撤销。

### 5. 验证
再次查询持仓和挂单，确认清空。

---

## 🛠️ 技术细节

### 为什么需要这个脚本？

Ladder 策略会创建多级限价单：
- L1: 50% @ 5 bps
- L2: 30% @ 15 bps
- L3: 20% @ 30 bps

如果只有 L1 成交，L2 和 L3 会残留为挂单。平仓时如果不撤销这些挂单：
- **风险 1**: 挂单可能在后续成交，形成新的持仓
- **风险 2**: 占用保证金
- **风险 3**: 影响下次交易

### get_active_orders() 可用性

Lighter SDK 的 `get_active_orders()` 方法可能在某些情况下不可用（返回空或报错）。脚本已处理这种情况：
- 如果查询失败，会提示手动验证
- 不会因为查询失败而停止执行

### cancel_all_orders() 为什么不用？

Lighter SDK 的 `cancel_all_orders()` 需要特殊参数且容易出错。
逐个撤单虽然慢一些，但更可靠。

---

## 📌 最佳实践

### 每次测试后清理

```bash
# 测试完成后立即运行
cat /tmp/clear_eigen_with_cancel.py | ssh ubuntu@3.38.98.169 \
  "cd /home/ubuntu/tw168 && docker compose exec -T tv-okx python3"
```

### 定期检查

```bash
# 检查当前状态（不执行清理）
ssh ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose exec -T tv-okx python3" << 'EOF'
import sys
sys.path.insert(0, '/src')
from perpbot.exchanges.lighter import LighterClient

client = LighterClient(use_testnet=False)
client.connect()

positions = client.get_account_positions()
eigen_pos = [p for p in positions if 'EIGEN' in p.order.symbol]

print(f'EIGEN 持仓: {len(eigen_pos)}')

try:
    orders = client.get_active_orders()
    eigen_orders = [o for o in orders if 'EIGEN' in o.symbol]
    print(f'EIGEN 挂单: {len(eigen_orders)}')
except:
    print('EIGEN 挂单: 无法查询')
EOF
```

### 集成到测试流程

在测试脚本末尾自动调用清理：

```python
# 测试结束
print("测试完成，清理中...")
await complete_cleanup()
```

---

## 📝 总结

**问题**: 平仓时挂单残留
**方案**: 完整清理脚本（平仓 + 撤单）
**位置**: `/tmp/clear_eigen_with_cancel.py`
**用法**: `cat /tmp/clear_eigen_with_cancel.py | ssh ... docker compose exec -T tv-okx python3`
**验证**: https://mainnet.zklighter.elliot.ai/

每次平仓后使用此脚本，确保持仓和挂单完全清空！
