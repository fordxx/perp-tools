# LighterClient 重构为原生 Async - 实施指南

## 目标

将 `LighterClient` 从当前的"同步包装 + 后台线程"架构重构为原生异步（async/await）架构，以解决 `cancel_all_orders()` 等方法的兼容性问题。

---

## 当前问题

### 现有架构

**文件**: `/home/fordxx/perp-tools/src/perpbot/exchanges/lighter.py`

**当前实现**:
```python
class LighterClient(ExchangeClient):
    def __init__(self, use_testnet: bool = False):
        # 创建独立的事件循环和后台线程
        self._ensure_loop()
        self._run_coro(self._async_initialize(), timeout=30.0)

    def _ensure_loop(self):
        """创建后台事件循环和线程"""
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=lambda: loop.run_forever(), daemon=True)
        thread.start()
        self._loop = loop

    def _run_coro(self, coro, timeout=15.0):
        """在后台线程中同步运行协程"""
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # 所有方法都是同步的
    def place_order(self, request: OrderRequest) -> Order:
        order = self._run_coro(self._signer_client.create_order(...))
        return order

    def cancel_all_orders(self) -> bool:
        result = self._run_coro(self._signer_client.cancel_all_orders(...))
        return True
```

**问题**:
- `run_coroutine_threadsafe` 创建 `Future`，不是 `Task`
- Lighter SDK 的 `aiohttp` 要求在 `Task` 中运行
- 导致错误: `RuntimeError: Timeout context manager should be used inside a task`

---

## 目标架构

### 新的实现

```python
class LighterClient(ExchangeClient):
    """完全异步的 Lighter 客户端"""

    def __init__(self, use_testnet: bool = False):
        # 不再创建后台线程和事件循环
        self.use_testnet = use_testnet
        self._connected = False
        self._trading_enabled = False
        # ... 其他初始化（不调用 async 方法）

    async def connect(self) -> None:
        """异步连接方法"""
        from lighter import ApiClient, Configuration
        from lighter.signer_client import SignerClient

        self._api_client = ApiClient(...)
        self._order_api = OrderApi(self._api_client)

        # 直接 await，不需要 _run_coro
        resp = await self._order_api.order_books()
        self._markets = {...}

        self._signer_client = SignerClient(...)
        self._connected = True

    async def disconnect(self) -> None:
        """异步断开连接"""
        if self._api_client:
            await self._api_client.close()
        # 不再需要停止事件循环

    async def place_order(self, request: OrderRequest) -> Order:
        """异步下单"""
        # 直接 await，不需要包装
        create_order, tx_hash, error = await self._signer_client.create_order(...)
        return Order(...)

    async def cancel_order(self, order_id: str, symbol: str = None) -> None:
        """异步撤单"""
        cancel_result, tx_hash, error = await self._signer_client.cancel_order(...)

    async def cancel_all_orders(self) -> bool:
        """异步撤销所有订单 - 现在能工作了！"""
        result, tx_hash, error = await self._signer_client.cancel_all_orders(...)
        return True

    async def get_account_positions(self) -> List[Position]:
        """异步获取持仓"""
        positions_resp = await self._account_api.get_positions(...)
        return [...]

    async def get_current_price(self, symbol: str) -> PriceQuote:
        """异步获取价格"""
        resp = await self._order_api.order_book_details(...)
        return PriceQuote(...)
```

---

## 实施步骤

### Phase 1: 重构 LighterClient 核心

**文件**: `/home/fordxx/perp-tools/src/perpbot/exchanges/lighter.py`

#### 步骤 1.1: 移除线程相关代码

**删除这些方法**:
```python
# Lines ~201-216
def _ensure_loop(self) -> None:
    # 删除整个方法

# Lines ~217-221
def _run_coro(self, coro, timeout: float = 15.0):
    # 删除整个方法
```

**删除这些属性**:
```python
# __init__ 中删除
self._loop = None
self._loop_thread = None
```

#### 步骤 1.2: 修改 __init__

**当前** (Lines ~54-162):
```python
def __init__(self, use_testnet: bool = False) -> None:
    # ... 初始化属性 ...

    try:
        self._ensure_loop()
        self._run_coro(self._async_initialize(), timeout=30.0)
        self._connected = True
    except Exception as e:
        self._connected = False
        raise
```

**修改为**:
```python
def __init__(self, use_testnet: bool = False) -> None:
    """
    初始化 Lighter 客户端（不连接）

    使用方式:
        client = LighterClient(use_testnet=False)
        await client.connect()
    """
    self.name = "lighter"
    self.venue_type = "dex"
    self.use_testnet = use_testnet

    # ... 其他属性初始化 ...

    self._connected = False
    self._trading_enabled = False

    # 不再调用 connect - 让调用者显式 await connect()
```

#### 步骤 1.3: 创建 async connect()

**新增方法**:
```python
async def connect(self) -> None:
    """
    异步连接到 Lighter

    Usage:
        client = LighterClient(use_testnet=False)
        await client.connect()
    """
    try:
        await self._async_initialize()
        self._connected = True
        logger.info(
            "✅ Lighter connected (testnet=%s, trading=%s, markets=%d)",
            self.use_testnet,
            self._trading_enabled,
            len(self._markets),
        )
    except Exception as e:
        self._connected = False
        self._trading_enabled = False
        logger.exception("❌ Lighter connection failed: %s", e)
        try:
            await self.disconnect()
        except Exception:
            pass
        raise
```

#### 步骤 1.4: 修改 disconnect()

**当前** (Lines ~164-198):
```python
def disconnect(self) -> None:
    try:
        if self._ws_client and self._loop and self._loop.is_running():
            self._run_coro(self._ws_client.disconnect(), timeout=5.0)

        if self._api_client and self._loop and self._loop.is_running():
            self._run_coro(self._api_client.close(), timeout=5.0)
    finally:
        # ... cleanup ...
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
```

**修改为**:
```python
async def disconnect(self) -> None:
    """异步断开连接"""
    try:
        if self._ws_client:
            await self._ws_client.disconnect()

        if self._api_client:
            await self._api_client.close()
    finally:
        self._ws_client = None
        self._api_client = None
        self._order_api = None
        self._account_api = None
        self._signer_client = None
        self._connected = False
        self._trading_enabled = False
```

#### 步骤 1.5: 转换所有公共方法为 async

**需要修改的方法列表** (搜索 `def ` 排除 `async def`):

1. **get_current_price** (~Lines 300-350)
2. **get_order_book** (~Lines 350-450)
3. **place_order** (~Lines 450-600)
4. **place_open_order** (~Lines 600-700)
5. **place_close_order** (~Lines 700-800)
6. **cancel_order** (~Lines 850-910)
7. **cancel_all_orders** (~Lines 911-950)
8. **get_active_orders** (~Lines 951-970)
9. **get_position** (~Lines 962-1000)
10. **get_account_positions** (~Lines 1000-1100)
11. **get_balances** (~Lines 1100-1150)

**转换模板**:
```python
# 当前
def method_name(self, arg1, arg2):
    result = self._run_coro(
        self._some_async_method(arg1, arg2),
        timeout=15.0
    )
    return result

# 修改为
async def method_name(self, arg1, arg2):
    # 直接 await，移除 _run_coro
    result = await self._some_async_method(arg1, arg2)
    return result
```

**示例 - place_order**:

**当前** (~Lines 450-600):
```python
def place_order(
    self,
    *,
    inst_id: str,
    td_mode: str,
    side: str,
    pos_side: str,
    ord_type: str,
    sz: str,
    px: str | None,
    ...
) -> dict:
    # ... 准备参数 ...

    create_order, tx_hash, error = self._run_coro(
        self._signer_client.create_order(...),
        timeout=15.0
    )

    # ... 处理结果 ...
```

**修改为**:
```python
async def place_order(
    self,
    *,
    inst_id: str,
    td_mode: str,
    side: str,
    pos_side: str,
    ord_type: str,
    sz: str,
    px: str | None,
    ...
) -> dict:
    # ... 准备参数 ...

    create_order, tx_hash, error = await self._signer_client.create_order(...)

    # ... 处理结果 ...
```

---

### Phase 2: 更新 main.py 调用代码

**文件**: `/home/fordxx/perp-tools/_remote_tw168/tw168/app/main.py`

#### 步骤 2.1: 修改初始化 (Lines ~89-100)

**当前**:
```python
elif SETTINGS.exchange == "lighter":
    env = os.getenv("LIGHTER_ENV", "mainnet").lower()
    use_testnet = env == "testnet"
    exchange = LighterClient(use_testnet=use_testnet)
    exchange.connect()  # 同步调用
    logger.info(f"✅ Lighter client initialized (env={env})")
```

**修改为**:
```python
elif SETTINGS.exchange == "lighter":
    env = os.getenv("LIGHTER_ENV", "mainnet").lower()
    use_testnet = env == "testnet"
    exchange = LighterClient(use_testnet=use_testnet)
    # connect() 现在是 async，需要在 startup 事件中调用
    logger.info(f"ℹ️  Lighter client created (env={env}), will connect on startup")
```

#### 步骤 2.2: 在 startup 事件中连接

**找到 startup 事件** (搜索 `@app.on_event("startup")`):

**当前**:
```python
@app.on_event("startup")
async def startup_event() -> None:
    """Application startup."""
    global _health_task, _refresh_task
    # ... 其他启动逻辑 ...
```

**修改为**:
```python
@app.on_event("startup")
async def startup_event() -> None:
    """Application startup."""
    global _health_task, _refresh_task, exchange

    # 连接 Lighter (如果使用)
    if SETTINGS.exchange == "lighter" and exchange is not None:
        try:
            await exchange.connect()
            logger.info("✅ Lighter client connected")
        except Exception as e:
            logger.exception("❌ Lighter connection failed: %s", e)
            raise

    # ... 其他启动逻辑 ...
```

#### 步骤 2.3: 在 shutdown 事件中断开

**找到 shutdown 事件** (搜索 `@app.on_event("shutdown")`):

**添加**:
```python
@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Application shutdown."""
    global exchange

    # 断开 Lighter
    if SETTINGS.exchange == "lighter" and exchange is not None:
        try:
            await exchange.disconnect()
            logger.info("✅ Lighter client disconnected")
        except Exception as e:
            logger.warning("Lighter disconnect error: %s", e)

    # ... 其他清理逻辑 ...
```

#### 步骤 2.4: 修改 webhook 处理函数

**当前** (Lines ~1297-1300):
```python
@app.post("/webhook/tradingview")
async def webhook_tradingview(req: Request) -> dict:
    raw_body = await req.body()
    payload = TvPayload.model_validate_json(raw_body)
    return await _process_payload(payload)
```

**保持不变** - 已经是 async，但需要修改 `_process_payload` 内部调用

#### 步骤 2.5: 修改 _process_payload 中的 exchange 调用

**搜索所有 `exchange.` 调用** (约有几十处):

**模式**:
```python
# 当前
result = exchange.some_method(arg1, arg2)

# 修改为
result = await exchange.some_method(arg1, arg2)
```

**关键位置**:

1. **获取持仓** (~Line 1815):
```python
# 当前
existing_pos = exchange.get_position(inst_id=inst_id, pos_side=pos_side)

# 修改为
existing_pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
```

2. **获取价格** (多处):
```python
# 当前
quote = exchange.get_current_price(symbol)

# 修改为
quote = await exchange.get_current_price(symbol)
```

3. **下单** (~Line 2100+):
```python
# 当前
resp = exchange.place_order(
    inst_id=inst_id,
    td_mode=SETTINGS.okx_td_mode,
    ...
)

# 修改为
resp = await exchange.place_order(
    inst_id=inst_id,
    td_mode=SETTINGS.okx_td_mode,
    ...
)
```

4. **撤单** (~Line 2373):
```python
# 当前
cancel_resp = exchange.cancel_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])

# 修改为
cancel_resp = await exchange.cancel_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])
```

5. **_cancel_pending_ladder_orders 函数** (Lines 69-126):

**当前**:
```python
def _cancel_pending_ladder_orders(key: str, inst_id: str, exchange_obj: Any) -> tuple[int, int]:
    # ...
    cancel_resp = exchange_obj.cancel_order(
        inst_id=inst_id,
        cl_ord_id=order_id
    )
```

**修改为**:
```python
async def _cancel_pending_ladder_orders(key: str, inst_id: str, exchange_obj: Any) -> tuple[int, int]:
    # ...
    cancel_resp = await exchange_obj.cancel_order(
        inst_id=inst_id,
        cl_ord_id=order_id
    )
```

**调用处也要 await**:
```python
# 当前
_cancel_pending_ladder_orders(key, inst_id, exchange)

# 修改为
await _cancel_pending_ladder_orders(key, inst_id, exchange)
```

---

### Phase 3: 更新其他依赖文件

#### 如果有 trade_manager.py

**搜索 `LighterClient` 使用**:
```bash
grep -n "\.place_order\|\.cancel_order\|\.get_position" app/trade_manager.py
```

**每个调用都要 await**。

---

## 测试清单

### 单元测试

**文件**: 创建 `/home/fordxx/perp-tools/tests/test_lighter_async.py`

```python
import pytest
import asyncio
from perpbot.exchanges.lighter import LighterClient

@pytest.mark.asyncio
async def test_lighter_connect():
    """测试异步连接"""
    client = LighterClient(use_testnet=True)

    # 初始状态
    assert not client._connected

    # 连接
    await client.connect()
    assert client._connected

    # 断开
    await client.disconnect()
    assert not client._connected

@pytest.mark.asyncio
async def test_lighter_get_price():
    """测试获取价格"""
    client = LighterClient(use_testnet=False)
    await client.connect()

    try:
        quote = await client.get_current_price("ETH/USDT")
        assert quote.mid > 0
    finally:
        await client.disconnect()

@pytest.mark.asyncio
async def test_lighter_cancel_all_orders():
    """测试撤销所有订单（关键测试）"""
    client = LighterClient(use_testnet=False)
    await client.connect()

    try:
        # 这个调用不应该报错
        result = await client.cancel_all_orders()
        # 即使没有订单，也应该返回 True
        assert isinstance(result, bool)
    finally:
        await client.disconnect()
```

**运行**:
```bash
cd /home/fordxx/perp-tools
pytest tests/test_lighter_async.py -v
```

### 集成测试

**手动测试 - webhook 流程**:

```bash
ssh ubuntu@3.38.98.169
cd /home/ubuntu/tw168

# 1. 部署新代码
# (从本地上传后)

# 2. 重启服务
docker compose down
docker compose build --no-cache tv-okx
docker compose up -d tv-okx

# 3. 检查启动日志
docker compose logs -f tv-okx | grep -E "Lighter|connect"

# 期望看到:
# INFO: ℹ️  Lighter client created (env=mainnet), will connect on startup
# INFO: ✅ Lighter client connected
# INFO: ✅ Lighter connected (testnet=False, trading=True, markets=122)

# 4. 测试 webhook
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret":"rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
    "type":"ZONE",
    "instId":"EIGEN-USDT-SWAP",
    "tf":"5m",
    "zone":"oversold",
    "close":"0.374"
  }'

# 期望: {"ok":true,"type":"ZONE","zone":"OVERSOLD"}

# 5. 测试完整流程（见之前的测试文档）
```

---

## 潜在问题和解决方案

### 问题 1: 同步代码调用异步方法

**症状**:
```python
RuntimeWarning: coroutine 'LighterClient.place_order' was never awaited
```

**原因**: 忘记在某处加 `await`

**解决**: 搜索所有 `exchange.` 调用，确保都有 `await`
```bash
cd /home/fordxx/perp-tools/_remote_tw168/tw168
grep -n "exchange\\.place_order\\|exchange\\.cancel_order\\|exchange\\.get_" app/main.py | grep -v "await"
```

### 问题 2: 事件循环已关闭

**症状**:
```python
RuntimeError: Event loop is closed
```

**原因**: 在 `__del__` 或 cleanup 中调用 async 方法

**解决**: 在 shutdown 事件中正确清理
```python
@app.on_event("shutdown")
async def shutdown_event():
    if exchange:
        await exchange.disconnect()  # 正确方式
```

### 问题 3: 性能问题

**症状**: 请求变慢

**原因**: 每个请求都创建新连接

**解决**: 确保 `exchange` 是全局单例，在 startup 时连接一次
```python
# 全局变量
exchange: LighterClient | None = None

# startup 时连接
@app.on_event("startup")
async def startup_event():
    global exchange
    if SETTINGS.exchange == "lighter":
        exchange = LighterClient(use_testnet=False)
        await exchange.connect()  # 只连接一次
```

---

## 回滚计划

如果重构失败，快速回滚：

```bash
# 1. 备份当前代码
cd /home/fordxx/perp-tools
git stash  # 或 git commit

# 2. 恢复之前的版本
git checkout <commit_before_refactor>

# 3. 重新部署
cd _remote_tw168/tw168
rsync -avz ../../src ubuntu@3.38.98.169:/home/ubuntu/perp-tools/
ssh ubuntu@3.38.98.169 "cd /home/ubuntu/tw168 && docker compose down && docker compose build && docker compose up -d"
```

---

## 完成标准

重构完成后，应该满足：

- [ ] `LighterClient` 所有公共方法都是 `async def`
- [ ] 移除了 `_ensure_loop()` 和 `_run_coro()`
- [ ] `__init__` 不再调用 async 方法
- [ ] `connect()` 和 `disconnect()` 是 async
- [ ] `main.py` 中所有 `exchange.` 调用都有 `await`
- [ ] `_cancel_pending_ladder_orders` 是 async
- [ ] startup/shutdown 事件中连接/断开
- [ ] 单元测试通过
- [ ] webhook 测试成功
- [ ] `cancel_all_orders()` 不再报错 `Timeout context manager`
- [ ] 完整 Ladder 流程测试通过
- [ ] 日志中看到挂单清理成功

---

## 参考资料

### AsyncIO 最佳实践

1. **永远在最顶层 await**
   ```python
   # 好
   @app.post("/webhook")
   async def handler():
       result = await async_function()

   # 坏
   @app.post("/webhook")
   def handler():
       result = async_function()  # 忘记 await
   ```

2. **不要在 __init__ 中调用 async**
   ```python
   # 好
   def __init__(self):
       self._connected = False

   async def connect(self):
       await self._async_init()

   # 坏
   def __init__(self):
       self._run_coro(self._async_init())
   ```

3. **使用 async context manager**
   ```python
   # 如果需要
   async def __aenter__(self):
       await self.connect()
       return self

   async def __aexit__(self, *args):
       await self.disconnect()

   # 使用
   async with LighterClient() as client:
       await client.place_order(...)
   ```

---

## 估算工作量

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| Phase 1 | 重构 LighterClient | 1.5-2 小时 |
| Phase 2 | 更新 main.py | 1-1.5 小时 |
| Phase 3 | 测试和调试 | 1-2 小时 |
| **总计** | | **3.5-5.5 小时** |

---

## 最后检查清单

部署前确认：

```bash
# 1. 语法检查
cd /home/fordxx/perp-tools
python3 -m py_compile src/perpbot/exchanges/lighter.py
python3 -m py_compile _remote_tw168/tw168/app/main.py

# 2. 搜索遗漏的同步调用
grep -r "exchange\\.place_order\\|exchange\\.cancel" _remote_tw168/tw168/app/ | grep -v "await"

# 3. 搜索 _run_coro 残留
grep -r "_run_coro" src/perpbot/exchanges/lighter.py

# 4. 确认 connect 在 startup
grep -A10 "on_event.*startup" _remote_tw168/tw168/app/main.py | grep "connect"
```

---

**创建时间**: 2025-12-30
**目标**: 解决 Lighter `cancel_all_orders()` 的 asyncio 兼容性问题
**预计工作量**: 3.5-5.5 小时
**风险等级**: 中（需要全面测试）
