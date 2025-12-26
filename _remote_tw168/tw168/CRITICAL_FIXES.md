# 关键修复总结 - tw168 交易系统

> 修复日期: 2025-12-26
> 状态: ✅ 已完成

本文档记录了针对 tw168 交易系统的三个高优先级安全修复。

---

## 🔴 修复 1: 细化异常处理 (高风险)

### 问题描述
- 代码中多处使用泛化的 `Exception` 捕获,无法区分不同类型的错误
- 缺少针对性的错误恢复策略
- JSON 解析、网络错误等没有细分处理

### 修复内容

#### 1.1 main.py - Webhook JSON 解析 (行 1052-1064)
**修改前:**
```python
except Exception as e:  # noqa: BLE001
    snippet = raw_body[:500].decode("utf-8", errors="replace")
    logger.warning("tv_webhook invalid_json err=%s body=%s", e, snippet)
    raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
```

**修改后:**
```python
except (json.JSONDecodeError, UnicodeDecodeError) as e:
    snippet = raw_body[:500].decode("utf-8", errors="replace")
    logger.warning("tv_webhook invalid_json err=%s body=%s", e, snippet)
    raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
except Exception as e:
    # Catch any other unexpected errors
    snippet = raw_body[:200].decode("utf-8", errors="replace")
    logger.error("tv_webhook unexpected_error err=%s body_snippet=%s", e, snippet, exc_info=True)
    raise HTTPException(status_code=500, detail="Internal server error") from e
```

#### 1.2 main.py - Extended 订单异常 (行 1695-1712)
**新增细分异常处理:**
- `ConnectionError, TimeoutError` → 返回 503 (网络故障)
- `ValueError` → 返回 400 (参数错误)
- 其他异常 → 完整日志记录 + 重新抛出

#### 1.3 okx.py - API 请求重试机制 (行 43-131)
**新增功能:**
- **指数退避重试**: 1s → 2s → 4s (最多 3 次)
- **智能重试策略**:
  - 4xx 客户端错误 (除 429) → 不重试,立即失败
  - 429 速率限制 → 重试
  - 5xx 服务器错误 → 重试
  - 网络超时 → 重试
- **详细日志**: 记录每次重试的进度和原因

**关键代码:**
```python
except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
    if attempt < max_retries - 1:
        backoff = 2 ** attempt  # Exponential backoff
        logger.warning("OKX API request failed (attempt %d/%d), retrying in %ds",
                      attempt + 1, max_retries, backoff)
        time.sleep(backoff)
    else:
        raise
```

### 收益
- ✅ 减少因临时网络故障导致的交易失败
- ✅ 更清晰的错误日志,便于问题定位
- ✅ 区分可恢复错误和致命错误

---

## 🔴 修复 2: 优化 WebSocket 重连逻辑 (资源泄漏风险)

### 问题描述
- WebSocket 连接失败后固定 3 秒重连,可能导致频繁重连
- 没有连续错误计数,可能无限重试
- 缺少资源清理和超时保护

### 修复内容

#### 2.1 candle_cache.py - OKX K线 WebSocket (行 108-206)
**新增功能:**
1. **指数退避**: 1s → 2s → 4s → ... → 60s (最大)
2. **连续错误计数**: 超过 10 次连续错误后停止重连
3. **连接成功时重置**: 重新连接成功后重置延迟和错误计数
4. **异常分类处理**:
   - `asyncio.CancelledError` → 正常退出,不重连
   - `WebSocketException` → 记录错误,计数+1
   - `ConnectionError, TimeoutError` → 网络问题,计数+1
   - `json.JSONDecodeError` → 不计入连续错误(数据异常)
5. **超时保护**: `close_timeout=5` 防止关闭时阻塞

**关键代码:**
```python
retry_delay = 1.0
max_retry_delay = 60.0
consecutive_errors = 0
max_consecutive_errors = 10

while not stop_event.is_set():
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
            retry_delay = 1.0  # 连接成功,重置
            consecutive_errors = 0
            logger.info("OKX candle ws subscribed to %d symbols", len(sub_args))
            # ... 处理消息 ...
    except (websockets.exceptions.ConnectionClosed, ...) as e:
        consecutive_errors += 1
        if consecutive_errors >= max_consecutive_errors:
            logger.error("Max consecutive errors reached, stopping")
            break

    if not stop_event.is_set():
        await asyncio.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, max_retry_delay)
```

#### 2.2 ws_fills.py - OKX 成交 WebSocket (行 51-180)
**与 K线 WebSocket 相同的优化**,额外增加:
- 登录事件错误检测
- 订单/算法订单频道的错误处理
- 更详细的日志信息

#### 2.3 ws_fills.py - Extended 成交 WebSocket (行 183-258)
**同样的指数退避和错误计数机制**

### 收益
- ✅ 避免在网络故障时频繁重连消耗资源
- ✅ 检测持续性问题并停止无效重试
- ✅ 连接成功后快速恢复,保持低延迟
- ✅ 更好的资源管理和清理

---

## 🔴 修复 3: 增强止损失败兜底机制 (资金安全)

### 问题描述
**这是最关键的安全问题!**
- 如果止损单下单失败,系统会尝试紧急平仓
- 但如果紧急平仓也失败,仓位将**完全无保护**
- 原有逻辑只记录日志,没有后续监控和告警

### 修复内容

#### 3.1 新增 emergency_handler.py (全新模块)
**核心功能:**

1. **紧急仓位注册和跟踪**
```python
@dataclass
class EmergencyPosition:
    inst_id: str           # 交易对
    pos_side: str          # 多/空
    size: str              # 仓位大小
    entry_price: float     # 入场价
    stop_loss: float       # 预期止损价
    failure_reason: str    # 失败原因
    timestamp: float       # 发生时间
    retry_count: int       # 重试次数
    max_retries: int = 3   # 最大重试次数
```

2. **后台监控任务**
- 每 10 秒检查一次所有紧急仓位
- 仓位存在超过 30 秒 → 发送周期性提醒
- 重试次数达到上限 → 发送 CRITICAL 告警

3. **多级告警机制**
```python
async def _monitor_loop(self):
    while not stop_event.is_set():
        await asyncio.sleep(10)
        for pos in emergency_positions:
            if pos.retry_count >= pos.max_retries:
                notify_error(
                    f"🚨 CRITICAL ALERT - MAX RETRIES REACHED 🚨\n"
                    f"⚠️ IMMEDIATE MANUAL INTERVENTION REQUIRED"
                )
```

4. **恢复接口**
```python
async def attempt_recovery(inst_id, pos_side, recovery_func):
    """尝试使用自定义恢复函数修复紧急仓位"""
    # 可用于后续手动干预或自动化恢复脚本
```

#### 3.2 main.py - 集成紧急处理 (行 1978-2074)

**止损失败流程 (多层防护):**

```
1. 主止损单 (place_algo_order)
   ↓ 失败
2. 备用止损单 (limit order) [如果启用 BACKUP_SL_ENABLED]
   ↓ 仍失败
3. 注册到紧急处理器 (emergency_handler.register_emergency)
   ↓
4. 尝试紧急市价平仓 (place_order market reduce_only)
   ↓ 成功 → 清除紧急记录,返回错误响应
   ↓ 失败 ↓
5. 发送 CRITICAL 告警 + 继续跟踪仓位
   - 通知包含所有关键信息:
     * 交易对、方向、大小
     * 入场价、预期止损价
     * 失败原因
     * 备用止损是否尝试
     * 紧急平仓结果
   - 紧急处理器持续监控
   - 周期性提醒 (每 30 秒)
   - 达到最大重试后升级告警
```

**关键代码片段:**
```python
# 注册紧急仓位
emergency_handler = get_emergency_handler()
await emergency_handler.register_emergency(
    inst_id=inst_id,
    pos_side=pos_side,
    size=order_sz,
    entry_price=filled_price,
    stop_loss=float(sl),
    cl_ord_id=cl_ord_id,
    failure_reason=f"SL order failed (backup_attempted={backup_sl_attempted}): {sl_failure_reason}",
)

# 尝试紧急平仓
emergency_close_resp = exchange.place_order(
    inst_id=inst_id,
    side=sl_side,
    pos_side=pos_side,
    ord_type="market",
    sz=order_sz,
    cl_ord_id=f"{cl_ord_id}_emerg"[:32],
    reduce_only=True,
)

if emergency_close_success:
    # 平仓成功,清除紧急记录
    await emergency_handler.clear_emergency(inst_id, pos_side)
else:
    # 平仓失败,发送 CRITICAL 告警
    notify_error(
        f"🚨 CRITICAL ALERT 🚨\n"
        f"Position opened WITHOUT PROTECTION\n"
        f"⚠️ IMMEDIATE MANUAL INTERVENTION REQUIRED\n"
        f"⚠️ Position is being monitored by emergency handler"
    )
```

#### 3.3 新增 /emergency 端点 (行 1045-1067)

**实时查询紧急仓位状态:**
```bash
curl http://localhost:8000/emergency
```

**返回示例:**
```json
{
  "count": 1,
  "positions": [
    {
      "inst_id": "BTC-USDT-SWAP",
      "pos_side": "long",
      "size": "10",
      "entry_price": 42000.0,
      "stop_loss": 41500.0,
      "failure_reason": "SL order failed (backup_attempted=true): code=50000",
      "age_seconds": 45,
      "retry_count": 0,
      "max_retries": 3
    }
  ]
}
```

### 收益
- ✅ **资金安全**: 即使止损和紧急平仓都失败,系统仍会持续监控
- ✅ **及时告警**: 多级告警确保人工能及时介入
- ✅ **完整记录**: 记录所有失败原因,便于事后分析
- ✅ **可观测性**: 通过 `/emergency` 端点实时查看问题仓位
- ✅ **防止遗漏**: 后台监控任务确保不会忘记处理

---

## 📊 测试建议

### 1. 异常处理测试
```bash
# 测试无效 JSON
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"invalid json'

# 测试网络超时 (需要配置 OKX API 模拟)
# 应该看到重试日志
```

### 2. WebSocket 重连测试
```bash
# 断开网络后重新连接,观察日志:
# - 应该看到指数退避: "reconnecting in 1.0s", "2.0s", "4.0s"...
# - 连接成功后: "retry_delay reset to 1.0s"
# - 连续失败 10 次: "max consecutive errors reached, stopping"
```

### 3. 止损失败测试
```bash
# 模拟止损失败场景 (需要修改配置或模拟 API 响应)
# 1. 主止损失败
# 2. 备用止损失败 (BACKUP_SL_ENABLED=true)
# 3. 紧急平仓失败

# 预期行为:
# - 发送 CRITICAL 告警到 Telegram
# - /emergency 端点显示仓位
# - 每 30 秒发送提醒
# - 达到最大重试后升级告警
```

---

## 🔧 配置建议

### 启用备用止损
```env
BACKUP_SL_ENABLED=true  # 强烈推荐开启
```

### WebSocket 监控
```bash
# 通过日志监控 WebSocket 健康状态
tail -f tw168.log | grep "ws"

# 应该看到:
# - "OKX candle ws subscribed"
# - "OKX fill ws connected and subscribed"
# - "Extended fill ws connected and subscribed"
```

### 紧急仓位监控
```bash
# 定期检查紧急状态
watch -n 5 'curl -s http://localhost:8000/emergency | jq'

# 设置告警 (如果 count > 0)
if [ $(curl -s http://localhost:8000/emergency | jq '.count') -gt 0 ]; then
    echo "⚠️ WARNING: Emergency positions detected!"
fi
```

---

## 📝 代码变更总结

| 文件 | 变更行数 | 主要修改 |
|------|---------|---------|
| `app/main.py` | +120 | 异常细化、紧急处理集成、/emergency 端点 |
| `app/okx.py` | +60 | 重试机制、指数退避 |
| `app/candle_cache.py` | +50 | WebSocket 重连优化 |
| `app/ws_fills.py` | +80 | WebSocket 重连优化 (OKX + Extended) |
| `app/emergency_handler.py` | +230 | **新增模块** - 紧急仓位管理 |
| **总计** | **+540 行** | 5 个文件修改,1 个新增 |

---

## ⚠️ 重要提醒

1. **测试环境验证**: 请先在测试环境充分测试所有修改
2. **监控告警**: 确保 Telegram 通知正常工作
3. **日志审查**: 部署后检查日志中是否有新的错误信息
4. **备份配置**: 部署前备份 `.env` 和现有代码
5. **逐步部署**: 建议先部署 WebSocket 优化,再部署紧急处理

---

## 🎯 下一步建议

基于这些修复,建议继续完善:

1. **数据库持久化**: 将紧急仓位记录持久化到数据库
2. **自动恢复**: 实现更智能的自动恢复策略
3. **监控大盘**: 集成 Prometheus/Grafana 监控
4. **回测验证**: 使用历史数据验证修复的有效性
5. **压力测试**: 模拟高并发场景测试稳定性

---

## 📞 联系支持

如遇到问题,请检查:
- 日志文件: `tw168.log`
- 紧急状态: `curl http://localhost:8000/emergency`
- 系统指标: `curl http://localhost:8000/metrics`

**关键修复完成 ✅**
