# Lighter 异步重构 - 快速参考

## 当前状态 ✅

### 已完成
- ✅ 创建 `app/lighter_adapter.py` - 异步适配层
- ✅ 修改 `app/main.py` - 使用适配器
- ✅ 创建测试脚本 `test_lighter_adapter.py`
- ✅ 文档 `LIGHTER_ASYNC_ADAPTER.md`

### 架构
```
main.py (FastAPI app)
    ↓
lighter_adapter.py (异步适配层)
    ↓ asyncio.to_thread (桥接)
    ↓
LighterClient (perpbot 包，当前同步)
    ↓
Lighter SDK (原生 async)
```

## 快速测试

### 1. 测试适配器
```bash
cd /home/fordxx/perp-tools/_remote_tw168/tw168
source .venv/bin/activate
python test_lighter_adapter.py
```

预期输出：
- ✅ 适配器创建成功
- ✅ 连接成功
- ✅ 各交易对价格正常显示
- ✅ 查询功能正常

### 2. 测试并发性能
```bash
python test_lighter_adapter.py --concurrent
```

### 3. 测试完整交易流程
```bash
# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 发送 ZONE 信号
curl -X POST http://127.0.0.1:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "你的密钥",
    "type": "ZONE",
    "instId": "EIGEN-USDT-SWAP",
    "tf": "5m",
    "zone": "OVERSOLD",
    "close": "3.5"
  }'

# 发送 DIV 信号
curl -X POST http://127.0.0.1:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "你的密钥",
    "type": "DIV",
    "instId": "EIGEN-USDT-SWAP",
    "tf": "5m",
    "side": "buy"
  }'
```

## 关键检查点

### 日志检查
```bash
tail -f tw168.log | grep -E "(Lighter|adapter|canceled_pending)"
```

应该看到：
- ✅ `Lighter adapter created`
- ✅ `Lighter client connected via adapter`
- ✅ `canceled_pending_order` (平仓时)
- ❌ **不应该**看到 `Timeout context manager` 错误

### 问题诊断

**症状 1: import 错误**
```
ModuleNotFoundError: No module named 'app.lighter_adapter'
```
**解决:** 检查文件是否创建成功，路径是否正确

**症状 2: 适配器创建失败**
```
AttributeError: 'LighterClient' object has no attribute ...
```
**解决:** 检查 perpbot 包版本，可能需要更新

**症状 3: cancel_all_orders 仍然失败**
```
RuntimeError: Timeout context manager should be used inside a task
```
**原因:** LighterClient 尚未重构为 async，adapter 通过 `asyncio.to_thread()` 调用同步方法，但无法解决 aiohttp 的上下文问题
**解决:** 需要完成 LighterClient 的原生 async 重构

## 下一步（LighterClient 重构）

### 目标
将 `perpbot/exchanges/lighter.py` 中的 LighterClient 重构为原生 async。

### 关键改动
```python
# 之前（同步）
class LighterClient:
    def place_order(self, ...):
        return self._run_coro(self._signer_client.create_order(...))
    
# 之后（异步）
class LighterClient:
    async def place_order(self, ...):
        return await self._signer_client.create_order(...)
```

### 重构完成后
1. 更新 `lighter_adapter.py`：
   ```python
   self._is_async_mode = True  # 或自动检测
   ```

2. 测试验证：
   ```bash
   python test_lighter_adapter.py
   ```

3. 确认日志：
   ```
   ✅ Lighter adapter (async_mode=True)
   ✅ cancel_all_orders 不再报错
   ```

## 文件清单

| 文件 | 作用 | 状态 |
|------|------|------|
| `app/lighter_adapter.py` | 异步适配层 | ✅ 已创建 |
| `app/main.py` | FastAPI 应用（已修改） | ✅ 已集成 |
| `test_lighter_adapter.py` | 测试脚本 | ✅ 已创建 |
| `LIGHTER_ASYNC_ADAPTER.md` | 详细文档 | ✅ 已创建 |
| `LIGHTER_ASYNC_QUICK_REF.md` | 本文档 | ✅ 已创建 |

## 常用命令

```bash
# 启动服务（开发模式）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 查看日志
tail -f tw168.log

# 测试适配器
python test_lighter_adapter.py

# 检查 Lighter 状态
bash check_lighter_status.sh

# 管理挂单
python manage_lighter_orders.py --cancel EIGEN/USDT
```

## 联系与反馈

如有问题，检查：
1. 日志文件 `tw168.log`
2. 测试输出 `python test_lighter_adapter.py`
3. 文档 `LIGHTER_ASYNC_ADAPTER.md`
