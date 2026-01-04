# Lighter 挂单清理问题分析和解决方案

## 问题描述

使用 Ladder 策略交易时，会创建多级限价单（L1/L2/L3）。如果只有部分订单成交，会残留未成交的挂单。平仓时如果不清理这些挂单，会导致：

1. **风险**: 挂单可能在后续成交，形成新的持仓
2. **资金占用**: 挂单占用保证金
3. **状态混乱**: 影响下次交易

用户截图显示：**946 EIGEN @ 0.37360** 的限价单在平仓后仍然存在。

---

## Lighter SDK API 限制

### 1. `get_active_orders()` 不可用

**问题**: Lighter SDK 的 `OrderApi` 和 `AccountApi` 都没有提供可靠的方法查询账户的活动订单。

**表现**:
- `lighter.py:911-929` 中的 `get_active_orders()` 方法会返回空列表
- 试图访问 `self._api.get_open_orders()` 会失败（属性不存在）
- 无法通过 SDK 查询订单列表

**结果**: 无法程序化验证订单是否已撤销。

### 2. `cancel_all_orders()` 参数问题

**测试结果**:

| time_in_force | timestamp_ms | 结果 |
|---------------|--------------|------|
| 0 | 当前时间 | `CancelAllTime should be nil` |
| 0 | 0 | `Timeout context manager error` |
| 1 | 0 | `CancelAllTime should be larger than 0` |
| 1 | 当前时间 | `CancelAllTime should be nil` |
| 1 | 未来时间 | `Timeout context manager error` |
| 2 | 未来时间 | `Timeout context manager error` |
| 3 | 任何值 | `CancelAllTimeInForce is invalid` |

**根本问题**:
- Lighter SDK 的 `cancel_all_orders()` 内部使用 aiohttp 的超时上下文管理器
- 从 `LighterClient._run_coro()` （使用 `run_coroutine_threadsafe`）调用时，aiohttp 抛出 `RuntimeError: "Timeout context manager should be used inside a task"`
- 这是 Lighter SDK 设计问题 - 它期望在原生 asyncio 上下文中运行，而不是通过 `run_coroutine_threadsafe`

### 3. 单个订单撤销 `cancel_order()` 可用

**工作方式**: 使用 `client.cancel_order(order_id=xxx, symbol="EIGEN/USDT")` 可以成功撤销单个订单。

**限制**: 需要知道 `order_id` (client_order_index)，但无法通过 SDK 查询。

---

## 临时解决方案（手动操作）

由于 SDK 限制，目前最可靠的方法是手动在 Lighter 平台清理挂单：

### 步骤

1. **访问 Lighter 平台**
   ```
   https://mainnet.zklighter.elliot.ai/
   ```

2. **连接钱包**
   - 点击右上角 "Connect Wallet"
   - 使用配置文件中对应的钱包地址（Account Index: 694324）

3. **查看挂单**
   - 点击 "Open Orders" 标签
   - 查找 EIGEN 相关订单

4. **撤销订单**
   - 点击每个 EIGEN 订单旁边的 "Cancel" 按钮
   - 确认交易
   - 等待几秒让交易确认

5. **验证**
   - 刷新页面
   - 确认 "Open Orders" 中没有 EIGEN 订单

---

## 长期解决方案

### 方案 A: 直接使用 Lighter Web API

绕过 SDK，直接调用 Lighter 的 REST API 查询和撤销订单。

**优点**:
- 不受 SDK 限制
- 可以自己控制 async 上下文

**缺点**:
- 需要研究 Lighter 的 API 文档
- 需要处理认证和签名逻辑

### 方案 B: 修改 LighterClient 的 async 架构

将 `LighterClient` 改为原生 async 类，去掉 `run_coroutine_threadsafe` 的包装。

**优点**:
- 可以使用所有 SDK 功能
- 更符合 Python async 最佳实践

**缺点**:
- 需要大量重构
- 会破坏现有的同步调用接口
- 影响 `main.py` 和其他依赖代码

### 方案 C: 记录 order_id，使用 cancel_order()

在创建 Ladder 订单时，记录所有的 `order_id`。平仓时，逐个撤销这些订单。

**优点**:
- `cancel_order()` 方法可用
- 不依赖 `get_active_orders()`

**缺点**:
- 需要维护订单状态
- 系统重启会丢失未清理订单的记录
- 实现复杂

### 方案 D: 不使用 Ladder，只下单个市价单

最简单的方案 - 放弃 Ladder 策略，直接使用市价单。

**优点**:
- 不会有残留挂单问题
- 实现简单

**缺点**:
- 失去 Ladder 的滑点优化
- 可能降低成交质量

---

## 当前代码修复

已完成的修复：

1. **修复 `get_active_orders()`** ([lighter.py:951-970](../../src/perpbot/exchanges/lighter.py#L951-L970))
   - 移除了错误的 `self._api` 访问
   - 添加文档说明该方法不可用
   - 返回空列表并记录警告

2. **添加 `cancel_all_orders()` 辅助方法** ([lighter.py:911-949](../../src/perpbot/exchanges/lighter.py#L911-L949))
   - 包装 `SignerClient.cancel_all_orders()`
   - 处理常见错误
   - 添加日志记录
   - **注意**: 由于 asyncio 上下文问题，该方法仍然不可用

3. **创建清理脚本**
   - `/tmp/cleanup_eigen_now.py` - 简化版清理脚本
   - `/tmp/cancel_eigen_fixed.py` - 使用 SignerClient 直接调用
   - `/tmp/cancel_eigen_final.py` - 测试不同参数组合

---

## 推荐操作流程

### 开发/测试环境

每次测试后手动清理：

```bash
# 1. 平仓（自动化）
python /tmp/close_eigen_position.py

# 2. 撤单（手动）
#    访问 https://mainnet.zklighter.elliot.ai/
#    在 "Open Orders" 中撤销所有 EIGEN 订单
```

### 生产环境

**重要**: 在实盘环境中使用 Ladder 策略前，必须解决挂单清理问题。

**临时方案**:
1. 监控 "Open Orders"
2. 定期手动清理（每天）
3. 设置告警（如果订单数超过阈值）

**长期方案**: 实施方案 A（直接 API）或方案 C（记录 order_id）

---

## 技术细节

### 为什么 asyncio 上下文会出问题？

```python
# LighterClient 使用的方式（错误）
def _run_coro(self, coro, timeout=15.0):
    fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
    return fut.result(timeout=timeout)

# 调用链:
# LighterClient.cancel_all_orders()
#   -> _run_coro(signer_client.cancel_all_orders(...))
#     -> run_coroutine_threadsafe(...)
#       -> SignerClient.cancel_all_orders()
#         -> self.send_tx()
#           -> aiohttp.ClientSession.request()
#             -> aiohttp timeout context manager
#               -> ❌ RuntimeError: "should be used inside a task"
```

**原因**: `aiohttp.ClientTimeout` 需要在 asyncio Task 中运行，而 `run_coroutine_threadsafe` 创建的是 Future，不是 Task。

### 正确的调用方式

```python
# 需要在原生 async 函数中调用
async def cancel_all():
    client = LighterClient(use_testnet=False)
    client.connect()

    # 直接 await，不通过 _run_coro
    result, tx_hash, error = await client._signer_client.cancel_all_orders(
        time_in_force=1,
        timestamp_ms=int((time.time() + 3600) * 1000)
    )

# 运行
asyncio.run(cancel_all())
```

**问题**: `LighterClient.connect()` 在同步上下文中，创建了单独的事件循环。要使用上述方式，需要重构整个 `LighterClient`。

---

## 总结

### 现状
- ✅ 平仓功能正常
- ❌ 自动化撤单不可用（SDK 限制）
- ⚠️  手动撤单可行但不理想

### 建议
1. **短期**: 手动在 Lighter 平台清理挂单
2. **中期**: 实施方案 C（记录 order_id，使用 cancel_order()）
3. **长期**: 实施方案 A（直接 REST API）或方案 B（重构为原生 async）

### 风险
在没有自动化撤单前，使用 Ladder 策略有一定风险。建议：
- 测试环境：继续使用，手动清理
- 生产环境：考虑暂时使用单个市价单，或严格监控挂单

---

最后更新: 2025-12-30
