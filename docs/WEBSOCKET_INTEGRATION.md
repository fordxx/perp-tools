# WebSocket 实时行情集成指南

**版本**: 1.0
**创建日期**: 2025-12-12
**状态**: ✅ 已实现

---

## 📋 概述

本文档介绍 PerpBot V2 的 WebSocket 实时行情数据集成系统。通过 WebSocket 连接，系统可以获得：

- ⚡ **更低延迟**: < 100ms (相比 REST API 的 200-500ms)
- 📡 **更高频率**: 实时推送 (相比 REST 的 1-5秒轮询)
- 🎯 **更高准确性**: 即时更新 (相比 REST 的陈旧快照)
- 💰 **更低成本**: 减少 API 调用次数

---

## 🏗️ 系统架构

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                   WebSocket 行情系统                          │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
│ OKX WebSocket  │  │ Hyperliquid WS  │  │ Paradex WS      │
│ Feed           │  │ Feed            │  │ Feed            │
└───────┬────────┘  └────────┬────────┘  └────────┬────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │ MarketDataUpdate   │
                    │ (归一化数据)        │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ WebSocketQuoteEngine│
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ Scanner V3         │
                    │ (套利扫描)          │
                    └────────────────────┘
```

### 文件结构

```
src/perpbot/exchanges/
├── websocket_manager.py          # WebSocket 管理器基类
├── okx_websocket.py              # OKX WebSocket 实现
├── hyperliquid_websocket.py      # Hyperliquid WebSocket 实现
└── paradex.py                    # Paradex 已有 WebSocket

src/perpbot/scanner/
└── websocket_quote_engine.py     # WebSocket Quote Engine

demos/
└── websocket_arbitrage_demo.py   # 完整演示程序

test_websocket_feeds.py           # WebSocket 连接测试
```

---

## 🚀 快速开始

### 1. 测试 WebSocket 连接

```bash
# 测试 WebSocket 连接到各交易所
python test_websocket_feeds.py
```

**预期输出**:
```
[14:23:45] OKX         BTC/USDT   | Bid:   43250.00 | Ask:   43251.00 | Spread:   2.32bps | Latency:  45.2ms
[14:23:45] HYPERLIQUID BTC/USDC   | Bid:   43249.50 | Ask:   43252.00 | Spread:   5.79bps | Latency:  67.8ms
[14:23:46] OKX         ETH/USDT   | Bid:    2301.50 | Ask:    2301.80 | Spread:   1.30bps | Latency:  42.1ms
```

### 2. 运行实时套利扫描 Demo

```bash
# 运行完整的实时套利扫描演示
python demos/websocket_arbitrage_demo.py
```

**预期输出**:
```
🎯 ===============================================================================
  ARBITRAGE OPPORTUNITY DETECTED
================================================================================

  Symbol:          BTC/USDT
  Exchange A:      OKX             | Bid: $ 43250.00 | Ask: $ 43251.00
  Exchange B:      HYPERLIQUID     | Bid: $ 43254.00 | Ask: $ 43255.50

  📊 Spread:          8.72 bps ( 0.087%)
  💰 Net Profit:      3.72 bps ( 0.037%)
  📈 Gross Profit:    8.72 bps
  💸 Total Fees:      5.00 bps

  ⚡ Strategy:      A_TO_B
  🎲 Score:           7.44
  ⏱️  Timestamp:     14:23:47.234

  📋 Execution Plan:
     1. BUY  on OKX @ $43251.00
     2. SELL on HYPERLIQUID @ $43254.00
```

### 3. 集成到现有代码

```python
from perpbot.scanner.websocket_quote_engine import WebSocketQuoteEngine
from perpbot.scanner.scanner_config import ScannerConfig
from perpbot.scanner.pair_scanner import PairScanner

# 1. 创建 Quote Engine
quote_engine = WebSocketQuoteEngine()

# 2. 启动 WebSocket 连接
exchanges = ["okx", "hyperliquid"]
symbols = ["BTC/USDT", "ETH/USDT"]
quote_engine.start(exchanges, symbols)

# 3. 等待初始行情
import time
time.sleep(3)

# 4. 查询实时报价
quotes = quote_engine.get_all_quotes("BTC/USDT")
print(quotes)
# 输出: {'okx': (43250.0, 43251.0), 'hyperliquid': (43249.5, 43252.0)}

# 5. 使用 Quote Engine 进行套利扫描
config = ScannerConfig(min_spread_bps=5.0, fee_bps=2.5)
scanner = PairScanner(config)

# ... 扫描逻辑

# 6. 停止 Quote Engine
quote_engine.stop()
```

---

## 📚 API 参考

### WebSocketMarketDataManager

中央 WebSocket 连接管理器。

```python
from perpbot.exchanges.websocket_manager import WebSocketMarketDataManager

manager = WebSocketMarketDataManager()

# 注册交易所 Feed
manager.register_feed(okx_feed)
manager.register_feed(hl_feed)

# 订阅行情
await manager.subscribe("okx", ["BTC/USDT", "ETH/USDT"])

# 注册回调
def on_update(update: MarketDataUpdate):
    print(f"{update.exchange} {update.symbol}: {update.bid} / {update.ask}")

manager.add_update_callback(on_update)

# 启动所有连接
await manager.start_all()

# 停止所有连接
await manager.stop_all()
```

### MarketDataUpdate

归一化的市场数据更新。

```python
@dataclass
class MarketDataUpdate:
    exchange: str          # 交易所名称
    symbol: str            # 交易对
    bid: float             # 买一价
    ask: float             # 卖一价
    bid_size: float        # 买一量
    ask_size: float        # 卖一量
    timestamp: datetime    # 时间戳
    latency_ms: float      # 网络延迟

    @property
    def mid(self) -> float:
        """中间价"""
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        """价差（基点）"""
        return (self.ask - self.bid) / self.mid * 10000
```

### WebSocketQuoteEngine

线程安全的实时报价引擎。

```python
from perpbot.scanner.websocket_quote_engine import WebSocketQuoteEngine

engine = WebSocketQuoteEngine()

# 启动（自动在后台线程运行）
engine.start(exchanges=["okx", "hyperliquid"], symbols=["BTC/USDT"])

# 查询单个交易所的报价
quote = engine.get_quote("okx", "BTC/USDT")
# 返回: (bid, ask, age_seconds)

# 查询所有交易所的报价
all_quotes = engine.get_all_quotes("BTC/USDT")
# 返回: {'okx': (bid, ask), 'hyperliquid': (bid, ask)}

# 查询最优报价（跨交易所）
best_bbo = engine.get_bbo("BTC/USDT")
# 返回: (best_bid, best_ask)

# 检查健康状态
is_healthy = engine.is_healthy()

# 获取统计信息
stats = engine.get_statistics()

# 停止
engine.stop()
```

---

## 🔧 支持的交易所

### 1. OKX (CEX)

**WebSocket 端点**:
- 主网: `wss://ws.okx.com:8443/ws/v5/public`
- AWS: `wss://wsaws.okx.com:8443/ws/v5/public`

**订阅频道**: `tickers`

**数据格式**:
```json
{
  "arg": {"channel": "tickers", "instId": "BTC-USDT-SWAP"},
  "data": [{
    "bidPx": "43250.0",
    "askPx": "43251.0",
    "bidSz": "1.5",
    "askSz": "2.3",
    "ts": "1638360000000"
  }]
}
```

**使用示例**:
```python
from perpbot.exchanges.okx_websocket import OKXWebSocketFeed

okx_feed = OKXWebSocketFeed(use_aws=False)
manager.register_feed(okx_feed)
await manager.subscribe("okx", ["BTC/USDT", "ETH/USDT"])
```

### 2. Hyperliquid (DEX)

**WebSocket 端点**:
- 主网: `wss://api.hyperliquid.xyz/ws`
- 测试网: `wss://testnet.api.hyperliquid.xyz/ws`

**订阅频道**: `l2Book`

**数据格式**:
```json
{
  "channel": "l2Book",
  "data": {
    "coin": "BTC",
    "levels": [
      [{"px": "43250.0", "sz": "1.5"}],  // Bids
      [{"px": "43251.0", "sz": "2.3"}]   // Asks
    ],
    "time": 1638360000000
  }
}
```

**使用示例**:
```python
from perpbot.exchanges.hyperliquid_websocket import HyperliquidWebSocketFeed

hl_feed = HyperliquidWebSocketFeed(use_testnet=True)
manager.register_feed(hl_feed)
await manager.subscribe("hyperliquid", ["BTC/USDC", "ETH/USDC"])
```

### 3. Paradex (DEX)

Paradex 已经在客户端中实现了 WebSocket 支持（通过 Paradex SDK）。

参见: [src/perpbot/exchanges/paradex.py](../src/perpbot/exchanges/paradex.py)

---

## 🎯 性能指标

### 延迟对比

| 方法 | 平均延迟 | P99 延迟 | 备注 |
|------|---------|---------|------|
| **REST API 轮询** | 300ms | 500ms | 需要主动请求 |
| **WebSocket 推送** | 60ms | 100ms | 服务端主动推送 |

### 吞吐量对比

| 方法 | 更新频率 | API 调用次数/分钟 |
|------|---------|------------------|
| **REST API 轮询** (1秒间隔) | 1 次/秒 | 60 次/分钟 |
| **WebSocket 推送** | 实时 (10-100次/秒) | 0 次 (仅连接时1次) |

### 资源消耗

| 指标 | REST 轮询 | WebSocket |
|------|----------|-----------|
| **网络带宽** | 高 (重复请求) | 低 (仅推送变化) |
| **CPU 使用率** | 中等 | 低 |
| **API 额度消耗** | 高 (每次轮询) | 低 (仅建立连接) |

---

## 🛠️ 故障排查

### 问题 1: WebSocket 连接失败

**症状**:
```
❌ OKX WebSocket error: Connection refused
```

**解决方案**:
1. 检查网络连接
2. 验证 WebSocket URL 是否正确
3. 检查防火墙设置
4. 尝试使用备用端点 (例如 OKX 的 AWS 端点)

### 问题 2: 没有收到行情更新

**症状**:
```
⚠️ OKX heartbeat stale (45.2s)
```

**解决方案**:
1. 检查订阅是否成功
2. 验证 symbol 格式是否正确
3. 查看 WebSocket 日志
4. 重启连接

### 问题 3: 行情数据陈旧

**症状**:
```python
quote_age_s: 30.5  # 超过 30 秒
```

**解决方案**:
1. 检查网络延迟
2. 检查 WebSocket 连接状态
3. 验证服务端是否正常推送
4. 考虑切换到备用端点

### 问题 4: 高延迟

**症状**:
```
Latency: 450.2ms  # 超过 100ms
```

**解决方案**:
1. 使用地理位置更近的端点 (如 OKX AWS)
2. 优化网络路由
3. 检查本地CPU负载
4. 减少订阅的 symbol 数量

---

## 📊 监控与告警

### 健康检查

```python
# 检查 Quote Engine 是否健康
if not quote_engine.is_healthy():
    logger.error("Quote engine unhealthy!")

    # 获取详细状态
    status = quote_engine.get_connection_status()
    for exchange, info in status.items():
        if not info['connected']:
            logger.error(f"{exchange} disconnected")
        if info['heartbeat_age'] > 30:
            logger.error(f"{exchange} heartbeat stale: {info['heartbeat_age']:.1f}s")
```

### 性能监控

```python
# 获取详细统计信息
stats = quote_engine.get_statistics()

for key, data in stats.items():
    print(f"{key}: "
          f"updates={data['updates']}, "
          f"avg_latency={data['avg_latency_ms']:.2f}ms, "
          f"age={data['quote_age_s']:.2f}s")
```

### 推荐告警阈值

| 指标 | 告警阈值 | 严重性 |
|------|---------|-------|
| **WebSocket 断开** | 连接状态 = false | 🔴 严重 |
| **心跳超时** | heartbeat_age > 30s | 🟠 警告 |
| **行情陈旧** | quote_age_s > 10s | 🟡 注意 |
| **高延迟** | avg_latency_ms > 200ms | 🟡 注意 |
| **更新率低** | updates/sec < 0.1 | 🟠 警告 |

---

## 🔮 未来改进

### 短期 (1-2周)

- [ ] 添加 Paradex WebSocket Feed 实现
- [ ] 支持更多交易所 (Extended, Lighter, EdgeX)
- [ ] 添加 WebSocket 重连指数退避
- [ ] 实现行情数据持久化

### 中期 (1个月)

- [ ] 添加 WebSocket 订单推送支持
- [ ] 实现多层级订单簿缓存
- [ ] 添加 WebSocket 数据压缩
- [ ] 性能优化 (零拷贝、批处理)

### 长期 (3个月+)

- [ ] 实现自适应订阅策略
- [ ] 添加 WebSocket 数据回放功能
- [ ] 机器学习延迟预测
- [ ] 多区域 WebSocket 代理

---

## 📖 相关文档

- [ARCHITECTURE.md](../ARCHITECTURE.md) - 系统架构文档
- [DEVELOPMENT_ROADMAP.md](../DEVELOPMENT_ROADMAP.md) - 开发路线图
- [README.md](../README.md) - 项目概览

---

**最后更新**: 2025-12-12
**维护者**: PerpBot 开发团队
