# Lighter WebSocket 心跳修复 - 2025-12-29

## 🎯 问题根源

### 发现过程
通过分析 crypto-trading-open 项目 (https://github.com/cryptocj520/crypto-trading-open)，发现 Lighter WebSocket 的关键特性：

**Lighter 使用 JSON 心跳协议，而不是 WebSocket 协议级别的 ping/pong！**

### 问题症状
- ⚠️  连接每 ~120 秒关闭一次
- ❌ 重连逻辑从未触发
- 📊 日志显示 "⚠️ Lighter WebSocket connection closed" 重复出现

---

## 🔍 根本原因分析

### Lighter 心跳协议

**服务器 → 客户端:**
```json
{"type": "ping"}
```

**客户端 → 服务器 (必须):**
```json
{"type": "pong"}
```

**超时规则**: 如果 **120 秒**内服务器没有收到任何消息（包括 pong），会主动断开连接。

### 我们的错误实现

```python
# 修复前 - lighter_websocket.py:77-80
self._ws = await websockets.connect(
    self.ws_url,
    ping_interval=20,      # ❌ WebSocket 协议 ping (Lighter 不响应)
    ping_timeout=10,       # ❌ 期待协议 pong (永远不会来)
)
```

**问题**:
1. `websockets` 库发送 WebSocket 协议级别的 **Ping 帧**
2. Lighter 服务器**不响应**协议级别的 Ping/Pong 帧
3. Lighter 只理解 JSON 格式的 `{"type": "ping"}` / `{"type": "pong"}`
4. 我们没有监听 JSON ping，也没有主动发送 JSON pong
5. **120 秒后服务器超时断开连接**

---

## ✅ 修复方案

### 1. 禁用协议级别 Ping

```python
# lighter_websocket.py:84-88
self._ws = await websockets.connect(
    self.ws_url,
    ping_interval=None,  # ✅ 禁用协议 ping (Lighter 不需要)
    ping_timeout=None,
)
```

### 2. 添加 JSON Ping 检测和响应

```python
# lighter_websocket.py:268-271
# Lighter uses JSON ping/pong heartbeat (not WebSocket protocol)
# Server sends {"type": "ping"}, client must reply {"type": "pong"}
if msg_type == "ping":
    await self._send_pong()
    logger.debug("📡 Received ping, sent pong")
    return
```

### 3. 实现主动心跳循环

```python
# lighter_websocket.py:338-366
async def _heartbeat_loop(self) -> None:
    """Proactive heartbeat loop - sends pong every 30 seconds.

    Lighter WebSocket has a 120-second idle timeout. By proactively
    sending pong messages every 30 seconds, we prevent disconnections
    even during periods of low market activity.
    """
    logger.info("💓 Lighter heartbeat loop started (interval: %ds)", self._heartbeat_interval)

    try:
        while self._running and self._connected:
            await asyncio.sleep(self._heartbeat_interval)

            if self._connected and self._ws:
                try:
                    await self._send_pong()
                    logger.debug("💓 Heartbeat pong sent (keepalive)")
                except Exception as e:
                    logger.error("❌ Heartbeat failed: %s", e)
                    break

    except asyncio.CancelledError:
        logger.info("💓 Heartbeat loop cancelled")
```

### 4. 发送 Pong 方法

```python
# lighter_websocket.py:323-336
async def _send_pong(self) -> None:
    """Send JSON pong message to server.

    Lighter uses application-layer heartbeat with JSON messages:
    Server sends {"type": "ping"}, client responds with {"type": "pong"}

    This prevents the 120-second idle timeout that causes disconnections.
    """
    if self._ws and self._connected:
        try:
            pong_msg = json.dumps({"type": "pong"})
            await self._ws.send(pong_msg)
        except Exception as e:
            logger.error("❌ Failed to send pong: %s", e)
```

---

## 📊 验证结果

### 修复前 (18:06-18:40, 35分钟运行)
```
连接关闭次数: 16 次
关闭频率: 16 / 35 分钟 ≈ 每 2.2 分钟一次
重连尝试: 0 次 (重连逻辑存在但从未触发)
状态: ❌ 不稳定
```

### 修复后 (19:23-19:27, 4分钟运行)
```
连接关闭次数: 0 次  ✅
运行时长: 4 分钟 (240 秒)
超过 Lighter 超时阈值: 240秒 > 120秒  ✅
状态: ✅ 稳定
```

**监控记录**:
| 检查 | 时间 | 连接关闭 | 运行时长 | 状态 |
|------|------|----------|----------|------|
| #1 | 19:24 | 0 | 1分2秒 | ✅ |
| #2 | 19:25 | 0 | 2分3秒 | ✅ |
| #3 | 19:27 | 0 | 4分3秒 | ✅ |

**结论**: 成功通过 Lighter 的 120 秒超时测试！

---

## 🔧 部署信息

### 修改文件
- `/home/fordxx/perp-tools/src/perpbot/exchanges/lighter_websocket.py`

### 修改内容
1. **初始化** (行 67-70): 添加心跳配置变量
2. **连接** (行 84-103): 禁用协议 ping，启动心跳任务
3. **断开** (行 116-123): 取消心跳任务
4. **消息处理** (行 260-271): 检测并响应 JSON ping
5. **心跳方法** (行 323-366): 实现 `_send_pong()` 和 `_heartbeat_loop()`

### 部署时间
- **修复开始**: 2025-12-29 19:20
- **容器重启**: 2025-12-29 19:23
- **验证完成**: 2025-12-29 19:27

---

## 📈 关键改进

### 心跳策略 (参考 crypto-trading-open)

**3 层防护**:
1. **被动响应**: 收到 `{"type": "ping"}` 立即回复
2. **主动心跳**: 每 30 秒主动发送 `{"type": "pong"}`
3. **超时监控**: 跟踪最后消息时间（未来可扩展）

**时间配置**:
```python
_heartbeat_interval = 30  # 主动发送间隔
Lighter 超时 = 120 秒     # 服务器限制
安全余量 = 4x (120/30)   # 提供充足的安全边际
```

---

## 🎓 经验教训

### WebSocket 协议 vs 应用层协议

**WebSocket 协议级别** (Ping/Pong 帧):
- 由 WebSocket 库自动处理
- 用于连接活性检测
- 不是所有服务器都支持/响应

**应用层协议** (JSON 消息):
- 需要应用代码实现
- Lighter/某些 DEX 使用这种方式
- 更灵活，但需要显式处理

### 重要检查清单

在集成任何 WebSocket API 时：

✅ **检查官方文档**
- 心跳机制（协议级 vs 应用层）
- 超时时间
- 重连策略

✅ **参考官方 SDK**
- 查看示例代码
- 检查心跳实现
- 学习最佳实践

✅ **分析开源项目**
- crypto-trading-open 提供了完整的 Lighter 实现
- 包含生产环境验证的代码
- 值得深入研究

---

## 📚 参考资源

### Lighter 官方
- WebSocket API: https://apidocs.lighter.xyz/docs/websocket-reference
- Python SDK: https://github.com/elliottech/lighter-python

### 参考项目
- crypto-trading-open: https://github.com/cryptocj520/crypto-trading-open
  - 文件: `core/adapters/exchanges/adapters/lighter_websocket.py`
  - 完整的心跳实现和连接管理

### WebSocket 最佳实践
- websockets 文档: https://websockets.readthedocs.io/
- 心跳机制: https://websockets.readthedocs.io/en/stable/topics/keepalive.html

---

## ✅ 修复状态

- ✅ 问题已识别
- ✅ 根本原因已确认
- ✅ 修复已实现
- ✅ 代码已部署
- ✅ 验证通过 (240秒 > 120秒超时阈值)
- ⏳ 长期稳定性监控中

---

**文档创建**: 2025-12-29 19:30  
**修复负责人**: Claude Code  
**验证状态**: ✅ 成功  
**下次检查**: 持续监控 24 小时稳定性
