# 交易所连接与健康管理层

## 概述

连接管理层提供统一的交易所连接管理，支持：
- 行情连接（只读）与交易连接（可下单）分离
- 心跳、重连、限流、熔断机制
- 健康监控与 KILL SWITCH
- 延迟和错误率统计

## 核心组件

### 1. BaseConnection - 基础连接抽象

**连接状态：**
- `CONNECTED`: 已连接（健康）
- `DEGRADED`: 降级（半开状态）
- `DISCONNECTED`: 未连接
- `CIRCUIT_OPEN`: 熔断开启

**核心功能：**
```python
from perpbot.connections import BaseConnection, ConnectionConfig

# 创建配置
config = ConnectionConfig(
    name="binance_market_data",
    exchange="binance",
    readonly=True,
    rate_limit_per_sec=10.0,
    circuit_open_error_streak=5,
)

# 连接
conn = MyConnection(config)
await conn.connect()

# 发送请求（自动限流和重试）
result = await conn.send_request("get_ticker", symbol="BTC/USDT")

# 获取健康信息
health = conn.get_health_info()
```

### 2. ExchangeConnectionManager - 交易所连接管理器

**行情/交易连接分离：**
```python
from perpbot.connections import ExchangeConnectionManager, ConnectionConfig

# 行情连接配置（只读）
market_config = ConnectionConfig(
    name="binance_market_data",
    exchange="binance",
    readonly=True,
)

# 交易连接配置
trading_config = ConnectionConfig(
    name="binance_trading",
    exchange="binance",
    readonly=False,
)

# 创建管理器
manager = ExchangeConnectionManager(
    exchange="binance",
    market_data_config=market_config,
    trading_config=trading_config,
    trade_enabled=True,
    api_key_env="BINANCE_API_KEY",
    api_secret_env="BINANCE_API_SECRET",
)

# 连接
await manager.connect_all()

# 获取行情连接（只读，始终可用）
market_conn = await manager.ensure_market_data()

# 获取交易连接（可写，需要凭证和 trade_enabled=True）
try:
    trading_conn = await manager.ensure_trading()
except ConnectionError as e:
    print(f"交易连接不可用: {e}")
```

### 3. ConnectionRegistry - 连接注册中心

**多交易所管理：**
```python
from perpbot.connections import ConnectionRegistry

# 创建注册中心
registry = ConnectionRegistry()

# 注册多个交易所
for exchange in ["binance", "okx", "edgex"]:
    manager = create_exchange_manager(exchange)
    registry.register(manager)

# 连接所有
await registry.connect_all()

# 检查交易是否允许
if registry.is_trading_allowed("binance"):
    # 执行交易
    pass

# KILL SWITCH
registry.enable_global_kill_switch()  # 全局停止
registry.enable_exchange_kill_switch("binance")  # 单交易所停止
```

### 4. HealthChecker - 健康检查器

**持续监控：**
```python
from perpbot.connections import HealthChecker

# 创建健康检查器
checker = HealthChecker(registry, check_interval_sec=10.0)

# 启动监控
checker.start()

# 获取不健康的交易所
unhealthy = checker.get_unhealthy_exchanges()

# 获取熔断的交易所
circuit_open = checker.get_circuit_open_exchanges()

# 停止监控
checker.stop()
```

## 熔断机制

**触发条件：**
1. 连续错误次数达到 `circuit_open_error_streak`
2. 心跳超时超过 `heartbeat_timeout_sec`

**恢复流程：**
1. 熔断触发 → 状态变为 `CIRCUIT_OPEN`
2. 等待 `circuit_halfopen_wait_sec` 秒
3. 进入半开状态 `DEGRADED`
4. 成功请求 → 恢复 `CONNECTED`
5. 失败请求 → 再次熔断

## 限流机制

**令牌桶算法：**
- 每秒生成 `rate_limit_per_sec` 个令牌
- 桶容量为 `burst_size`
- 请求消耗令牌，无令牌则等待

```python
config = ConnectionConfig(
    rate_limit_per_sec=10.0,  # 每秒10个请求
    burst_size=20,             # 突发容量20
)
```

## KILL SWITCH

**三层控制：**

1. **全局 KILL SWITCH**（最高优先级）
   ```python
   registry.enable_global_kill_switch()  # 停止所有交易
   ```

2. **单交易所 KILL SWITCH**
   ```python
   registry.enable_exchange_kill_switch("binance")
   ```

3. **连接管理器 KILL SWITCH**
   ```python
   manager.enable_kill_switch()
   ```

**效果：**
- KILL SWITCH 启用后，所有交易请求被拒绝
- 行情连接不受影响
- 已在途任务可以完成（平仓/善后）

## 与现有模块集成

### RiskManager 集成

```python
from perpbot.connections import ConnectionRegistry

class EnhancedRiskManager:
    def __init__(self, connection_registry: ConnectionRegistry):
        self.connections = connection_registry

    def evaluate_job(self, job, market_data):
        # 检查连接健康
        for exchange in job.exchanges:
            manager = self.connections.get(exchange)
            if not manager or not manager.is_healthy():
                return RiskEvaluation(
                    decision=DecisionType.REJECT,
                    reason=f"Exchange {exchange} unhealthy"
                )

            # 使用连接延迟作为风险因子
            latency = manager.get_market_data_latency()
            if latency > max_acceptable_latency:
                # 降低评分
                pass
```

### Scheduler 集成

```python
class UnifiedHedgeScheduler:
    def __init__(self, connection_registry: ConnectionRegistry):
        self.connections = connection_registry

    def tick(self, market_data):
        for job in self.pending_jobs:
            # 过滤不健康的交易所
            unhealthy = [
                ex for ex in job.exchanges
                if not self.connections.is_trading_allowed(ex)
            ]

            if unhealthy:
                # 拒绝或降低优先级
                continue
```

### MonitoringState 集成

```python
class UnifiedMonitoringState:
    def __init__(self, connection_registry: ConnectionRegistry):
        self.connections = connection_registry

    def to_dict(self):
        return {
            "connections": self.connections.get_health_summary(),
            # ... other stats
        }
```

## 配置示例

**config.yaml:**
```yaml
exchanges:
  binance:
    market_data:
      rate_limit_per_sec: 10.0
      heartbeat_interval_sec: 30.0
      heartbeat_timeout_sec: 60.0
      max_latency_ms: 500.0
      circuit_open_error_streak: 5
      circuit_halfopen_wait_sec: 60.0

    trading:
      rate_limit_per_sec: 5.0
      trade_enabled: true
      api_key_env: BINANCE_API_KEY
      api_secret_env: BINANCE_API_SECRET

  okx:
    market_data:
      rate_limit_per_sec: 8.0
    trading:
      trade_enabled: false  # 仅行情
```

## API 密钥管理

**环境变量方式：**
```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export OKX_API_KEY="your_api_key"
export OKX_API_SECRET="your_api_secret"
```

**安全原则：**
- ✅ API 密钥存储在环境变量中
- ✅ 配置文件中只保存环境变量名
- ✅ 从不在代码或配置中明文存储密钥
- ✅ `trade_enabled=False` 时不实例化交易连接

## 运行演示

```bash
# 完整演示（6个场景）
PYTHONPATH=src python -m perpbot.demos.connection_demo
```

演示包括：
1. 基础连接 - 心跳、延迟、限流
2. 熔断机制 - 连续错误触发熔断
3. 交易所管理器 - 行情/交易分离
4. 连接注册中心 - 多交易所管理
5. 健康检查器 - 自动监控
6. 完整生命周期 - 正常→失败→熔断→恢复

## 架构设计

```
ConnectionRegistry (全局注册中心)
├── ExchangeConnectionManager (binance)
│   ├── market_data_conn (BaseConnection, readonly=True)
│   └── trading_conn (BaseConnection, readonly=False)
├── ExchangeConnectionManager (okx)
│   ├── market_data_conn
│   └── trading_conn
└── HealthChecker (持续监控)
    ├── 延迟检查
    ├── 错误率检查
    ├── 心跳超时检查
    └── 熔断状态检查
```

## 关键指标

**连接健康指标：**
- `state`: 连接状态
- `avg_latency_ms`: 平均延迟（毫秒）
- `error_rate`: 错误率（0-1）
- `error_streak`: 连续错误次数
- `last_heartbeat`: 最后心跳时间

**告警阈值（可配置）：**
- 延迟 > `max_latency_ms` → ⚠️ 告警
- 错误率 > 10% → ⚠️ 告警
- 连续错误 >= `circuit_open_error_streak` → ⛔ 熔断
- 心跳超时 > `heartbeat_timeout_sec` → ⛔ 熔断

## 最佳实践

1. **行情连接始终开启**：即使 `trade_enabled=False`
2. **交易连接按需开启**：有 API 密钥且 `trade_enabled=True`
3. **监控连接健康**：定期检查 `is_healthy()`
4. **响应熔断事件**：熔断时停止分配新任务
5. **日志所有状态变化**：便于事后分析
6. **定期备份健康快照**：用于趋势分析
7. **测试 KILL SWITCH**：确保紧急情况下能快速停止

## 故障排查

**连接失败：**
- 检查网络连接
- 检查 API 密钥是否正确
- 查看日志中的具体错误信息

**频繁熔断：**
- 检查网络质量
- 增大 `circuit_open_error_streak`
- 检查交易所 API 状态

**延迟过高：**
- 检查本地网络
- 考虑使用 VPN
- 降低 `rate_limit_per_sec`

**KILL SWITCH 无法解除：**
- 检查 `global_kill_switch` 状态
- 检查 `per_exchange_kill_switch`
- 检查连接健康状态
