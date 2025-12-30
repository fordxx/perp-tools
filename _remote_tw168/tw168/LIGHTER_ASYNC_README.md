# Lighter 异步适配器 - 文档索引

## 📚 文档清单

| 文档 | 用途 | 读者 |
|------|------|------|
| **[LIGHTER_ASYNC_STATUS.md](LIGHTER_ASYNC_STATUS.md)** | 📊 **从这里开始** - 项目状态和交付总结 | 所有人 |
| **[LIGHTER_ASYNC_QUICK_REF.md](LIGHTER_ASYNC_QUICK_REF.md)** | ⚡ 快速参考 - 常用命令和故障排查 | 开发者 |
| **[LIGHTER_ASYNC_ADAPTER.md](LIGHTER_ASYNC_ADAPTER.md)** | 📖 详细指南 - API 文档和使用示例 | 开发者 |
| **[LIGHTER_ASYNC_IMPLEMENTATION.md](LIGHTER_ASYNC_IMPLEMENTATION.md)** | 🏗️ 实施总结 - 架构变化和迁移路径 | 架构师 |

## 🚀 快速开始（5 分钟）

### 1️⃣ 验证集成
```bash
bash check_lighter_adapter.sh
```

### 2️⃣ 运行测试
```bash
python test_lighter_adapter.py
```

### 3️⃣ 启动服务
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4️⃣ 查看日志
```bash
tail -f tw168.log | grep -i lighter
```

**预期输出:**
```
✅ Lighter adapter created (env=mainnet)
✅ Lighter client connected via adapter
```

## 📋 常见问题

### Q1: 为什么需要适配器？
**A:** LighterClient 当前使用线程 + `run_coroutine_threadsafe`，导致某些 async 功能（如 `cancel_all_orders`）失败。适配器提供统一的异步接口，为后续原生 async 重构做准备。

### Q2: 适配器有性能影响吗？
**A:** 有轻微影响（+10-50ms/调用），因为使用 `asyncio.to_thread()` 桥接。完成 LighterClient 重构后，性能将恢复正常。

### Q3: 需要修改业务代码吗？
**A:** 不需要。`main.py` 中的业务逻辑无需修改，只是初始化方式改变了。

### Q4: cancel_all_orders 还会失败吗？
**A:** 可能。桥接模式无法完全解决 aiohttp 的 timeout context 问题。完整解决需要 LighterClient 原生 async 重构。

### Q5: 什么时候切换到原生模式？
**A:** 当 LighterClient 完成 async 重构后，只需调用：
```python
exchange.set_async_mode(True)
```

## 🎯 核心文件

### 实现
- [`app/lighter_adapter.py`](app/lighter_adapter.py) - 异步适配器（434 行）
- [`app/main.py`](app/main.py) - 已集成适配器

### 测试
- [`test_lighter_adapter.py`](test_lighter_adapter.py) - 单元测试（201 行）
- [`check_lighter_adapter.sh`](check_lighter_adapter.sh) - 验证脚本

### 文档
- [`LIGHTER_ASYNC_STATUS.md`](LIGHTER_ASYNC_STATUS.md) - 项目状态 ⭐
- [`LIGHTER_ASYNC_QUICK_REF.md`](LIGHTER_ASYNC_QUICK_REF.md) - 快速参考
- [`LIGHTER_ASYNC_ADAPTER.md`](LIGHTER_ASYNC_ADAPTER.md) - 详细指南
- [`LIGHTER_ASYNC_IMPLEMENTATION.md`](LIGHTER_ASYNC_IMPLEMENTATION.md) - 实施总结

## 📊 当前状态

```
✅ 适配器已实现
✅ 集成到 main.py
✅ 测试脚本就绪
✅ 文档完整
✅ 所有验证通过（19/19）

⏳ 等待 LighterClient 原生 async 重构
```

## 🔗 相关文档

- [项目交接文档](PROJECT_HANDOFF_LADDER_CLEANUP.md)
- [Lighter 交易测试指南](LIGHTER_TRADING_TEST_GUIDE.md)
- [Lighter WebSocket 集成](LIGHTER_WEBSOCKET.md)

---

**需要帮助？**
1. 先读 [LIGHTER_ASYNC_STATUS.md](LIGHTER_ASYNC_STATUS.md)
2. 运行 `bash check_lighter_adapter.sh` 验证集成
3. 查看 [LIGHTER_ASYNC_QUICK_REF.md](LIGHTER_ASYNC_QUICK_REF.md) 的故障排查部分
