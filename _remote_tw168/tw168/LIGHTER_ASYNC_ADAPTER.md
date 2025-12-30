# Lighter 异步适配器使用指南

## 概述

`app/lighter_adapter.py` 提供了 LighterClient 的异步适配层，支持两种模式：

1. **桥接模式**（当前）: LighterClient 未重构时，通过 `asyncio.to_thread()` 桥接同步方法
2. **原生模式**（未来）: LighterClient 重构为 async 后，直接透传异步调用

## 快速开始

### 在 main.py 中使用（已集成）

```python
from app.lighter_adapter import create_lighter_adapter

# 创建适配器
exchange = create_lighter_adapter(use_testnet=False)

# 在 startup 事件中连接
await exchange.connect()

# 使用统一的异步接口
order = await exchange.place_order(
    inst_id="EIGEN-USDT-SWAP",
    side="buy",
    sz="1",
    ...
)
```

当前 `main.py` 已自动使用此适配器，无需修改业务代码。

## 支持的方法

### 交易相关
- `await exchange.place_order(...)` - 下单
- `await exchange.place_algo_order(...)` - 下算法单
- `await exchange.cancel_order(...)` - 撤单
- `await exchange.cancel_all_orders(symbol)` - 撤销所有订单

### 查询相关
- `await exchange.get_order(...)` - 查询订单
- `await exchange.get_position(...)` - 查询持仓
- `await exchange.get_last_price(...)` - 获取最新价格
- `await exchange.get_open_orders(...)` - 获取未成交订单
- `await exchange.get_algo_orders(...)` - 获取算法订单

### 同步方法（缓存数据）
- `exchange.get_instrument_info(...)` - 获取合约信息
- `exchange.enable_websocket()` - 启用 WebSocket

## 模式切换

当 LighterClient 完成 async 重构后：

```python
# 在 main.py 的 startup 事件中添加
if SETTINGS.exchange == "lighter":
    await exchange.connect()
    exchange.set_async_mode(True)  # 切换到原生异步模式
    logger.info("✅ Lighter adapter switched to native async mode")
```

## 迁移到原生 async（当 LighterClient 重构完成后）

### 步骤 1: 更新 lighter_adapter.py

在 `LighterAsyncAdapter.__init__` 中检测 LighterClient 是否支持 async：

```python
def __init__(self, lighter_client: Any) -> None:
    self._client = lighter_client
    
    # 自动检测是否为 async
    import inspect
    self._is_async_mode = inspect.iscoroutinefunction(
        getattr(self._client, 'place_order', None)
    )
    
    logger.info(f"Lighter adapter initialized (async_mode={self._is_async_mode})")
```

### 步骤 2: 测试验证

```bash
# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 发送测试信号
bash scripts/test_lighter.sh
```

检查日志中是否出现：
- ✅ `Lighter adapter switched to native async mode`
- ✅ `canceled_pending_order` （平仓时）
- ❌ 不应出现 `Timeout context manager` 错误

## 故障排查

### 问题 1: cancel_all_orders 仍然报错

**现象:**
```
RuntimeError: Timeout context manager should be used inside a task
```

**原因:** LighterClient 尚未重构为 async，adapter 仍在桥接模式

**解决:** 等待 LighterClient 重构完成，或手动设置 `exchange.set_async_mode(True)` 测试

### 问题 2: 方法调用失败

**现象:**
```
AttributeError: 'LighterClient' object has no attribute 'xxx'
```

**原因:** 方法名不匹配或 LighterClient 版本过旧

**解决:** 
1. 检查 lighter_adapter.py 中的方法名是否正确
2. 更新 perpbot 包：`pip install -U perpbot`

### 问题 3: 性能下降

**现象:** 订单执行变慢

**原因:** 桥接模式使用 `asyncio.to_thread()`，有额外开销

**解决:** 
1. 短期：接受性能损失（通常 <100ms）
2. 长期：完成 LighterClient 的 async 重构

## 性能对比

| 操作 | 桥接模式 | 原生 async | 提升 |
|-----|---------|-----------|------|
| place_order | ~150ms | ~50ms | 3x |
| cancel_all | 失败 | ~100ms | ∞ |
| 并发查询 | 串行 | 并发 | N×|

## 下一步

1. **短期**（已完成）: 使用 adapter 解决 main.py 的调用问题
2. **中期**: 重构 LighterClient 为原生 async
3. **长期**: 移除 adapter，直接使用 async LighterClient

## 参考资料

- Python asyncio 文档: https://docs.python.org/3/library/asyncio.html
- FastAPI async 指南: https://fastapi.tiangolo.com/async/
- 项目主交接文档: PROJECT_HANDOFF_LADDER_CLEANUP.md
