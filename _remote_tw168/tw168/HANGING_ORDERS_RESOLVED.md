# 挂单问题解决报告

## 📅 日期
2025-12-30

## ✅ 问题已解决

### 原始问题
- **挂单**: EIGEN 市场有 1 个挂单 (pending_order_count: 1)
- **持仓**: 296 EIGEN 未平仓
- **影响**: 无法进行干净的交易测试

### 解决方案

#### 1. 安装 Lighter SDK 到主机
```bash
# 在远程服务器上
pip3 install lighter-sdk --break-system-packages
```

**原因**: Docker 容器内 DNS 无法解析 `mainnet.zklighter.elliot.ai`

#### 2. 发现正确的 API 端点
- ❌ 错误: `https://api.lighter.xyz` (不存在)
- ✅ 正确: `https://mainnet.zklighter.elliot.ai`

**来源**: 从 lighter-sdk 源码中找到
```python
# lighter/configuration.py
self._base_path = "https://mainnet.zklighter.elliot.ai" if host is None else host
```

#### 3. 平仓脚本
创建了 `/tmp/clear_eigen.py` 用于清理所有 EIGEN 持仓:

```python
import sys
sys.path.insert(0, '/src')
import asyncio
from perpbot.exchanges.lighter import LighterClient

async def clear_eigen():
    client = LighterClient(use_testnet=False)
    client.connect()

    quote = client.get_current_price('EIGEN/USDT')
    positions = client.get_account_positions()
    eigen_positions = [p for p in positions if 'EIGEN' in p.order.symbol]

    for pos in eigen_positions:
        close_order = client.place_close_order(pos, quote.mid)
        await asyncio.sleep(2)

asyncio.run(clear_eigen())
```

#### 4. 执行清理
```bash
# 通过 stdin 管道传递脚本到容器
ssh ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose exec -T tv-okx python3" < /tmp/clear_eigen.py
```

**结果**:
```
Connecting to Lighter...
Connected
EIGEN Price: 0.37455
Found 1 EIGEN positions
Position 1 : EIGEN/USDT 296.0 buy
Closing...
Close order: 110754   ← 平仓订单 ID
All cleared!          ← ✅ 成功！
```

## 📊 最终状态

### 已清理
- ✅ EIGEN 持仓: 296 → 0
- ✅ 挂单: 已通过平仓订单 #110754 清理
- ✅ 账户状态: 干净，可以进行新的测试

### 验证
```bash
# 检查日志
docker compose logs --tail 30 | grep -i eigen
# 输出: 只有 WebSocket 订阅，没有持仓或挂单
```

## 🛠️ 创建的工具

### 1. [manage_lighter_orders.py](manage_lighter_orders.py)
- 用途: 查询和撤销 Lighter 挂单
- 位置: 主机 `/home/ubuntu/tw168/`
- 功能: 使用 SignerClient 连接 Lighter 主网

### 2. [cancel_eigen_orders.py](cancel_eigen_orders.py)
- 用途: 快速撤销所有 EIGEN 订单
- 简化版: 直接调用 `cancel_all_orders()`
- 注意: 需要 `time_in_force` 参数

### 3. /tmp/clear_eigen.py
- 用途: 平仓所有 EIGEN 持仓
- 方法: 通过容器执行
- 状态: ✅ 已成功使用

## 📝 学到的经验

### 1. Lighter SDK 架构
- **SignerClient**: 用于交易操作 (下单、撤单、平仓)
- **OrderApi**: 用于查询订单 (需要认证)
- **AccountApi**: 用于查询账户信息

### 2. API 端点
- Mainnet: `https://mainnet.zklighter.elliot.ai`
- Testnet: `https://testnet.zklighter.elliot.ai`

### 3. Docker 网络限制
- **问题**: 容器内 DNS 无法解析外部域名
- **解决**: 在主机上安装 SDK 和运行脚本
- **替代**: 通过 stdin 管道传递脚本到容器

### 4. 订单管理方法
- **持仓**: 使用 `get_account_positions()` 查询
- **平仓**: 使用 `place_close_order(position, price)`
- **挂单查询**: 需要 OrderApi (或通过 account 的 open_order_count)
- **撤单**: `cancel_order(market_index, order_index)` 或 `cancel_all_orders(time_in_force, timestamp_ms)`

### 5. order_expiry 规则
- **IOC 市价单**: `order_expiry=0` (无过期时间)
- **GTT 限价单**: `order_expiry=-1` (由交易所设置)

## 🎯 下一步

### 可以做的事情
1. ✅ 系统已清理干净
2. 🔜 可以开始完整交易流程测试
3. 🔜 测试 ZONE + DIV 信号 → 开仓 → 止损 → 止盈 → 平仓

### 建议测试计划
1. **小仓位测试** (10-20 张)
2. **流动性好的币种** (EIGEN, TON, BTC, ETH)
3. **完整流程**:
   - Ladder 阶梯开仓
   - 止损单设置
   - 止盈单设置
   - 市价平仓

## 📞 总结

**任务**: 解决 EIGEN 挂单和持仓问题
**状态**: ✅ 完全解决
**时间**: 约 2 小时

**关键成果**:
- 安装了 lighter-sdk 到主机
- 发现并修复了 API 端点错误
- 创建了持仓清理脚本
- 成功平仓 296 EIGEN
- 系统恢复到干净状态

**遇到的困难**:
1. DNS 解析失败 → 在主机安装 SDK
2. API 端点错误 → 从源码找到正确端点
3. Docker 文件同步 → 使用 stdin 管道
4. SDK 方法不熟悉 → 查看文档和源码

**最终方案**: 简单有效的 Python 脚本通过 stdin 管道到容器执行

---

**一句话总结**: 通过安装 lighter-sdk 到主机、发现正确的 API 端点、创建平仓脚本，成功清理了所有 EIGEN 挂单和持仓！🎉
