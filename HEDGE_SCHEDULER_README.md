# 多对冲任务调度器 (Hedge Scheduler)

## 概述

`HedgeScheduler` 是一个统一的任务调度模块，用于协调和管理来自不同策略（刷量、套利、做市）的对冲任务。该模块通过多维度评分系统，在资金、并发、风险等约束下，智能选择最优任务组合执行。

## 核心特性

### 1. 统一任务模型 (HedgeJob)

所有策略模块通过统一的 `HedgeJob` 数据模型提交任务：

- **基础信息**：symbol、exchanges、notional
- **收益指标**：expected_edge_bps、expected_pnl
- **风险评分**：risk_score、latency_score、vol_score、funding_score、liquidity_score
- **状态管理**：PENDING → RUNNING → COMPLETED/FAILED
- **元数据**：保存策略特定参数

### 2. 多维度评分系统

任务评分基于以下维度：

| 指标 | 说明 | 权重（均衡模式） |
|------|------|------------------|
| **expected_edge_bps** | 预期收益率（基点） | 25% |
| **expected_pnl** | 预期绝对收益 | 20% |
| **risk_score** | 风险评分（取反） | 20% |
| **latency_score** | 执行延迟评分 | 10% |
| **vol_score** | 成交量贡献 | 10% |
| **funding_score** | 资金费率影响 | 10% |
| **liquidity_score** | 流动性评分 | 5% |

### 3. 四种风险模式

不同模式下各指标权重不同：

| 模式 | 侧重点 | 适用场景 |
|------|--------|----------|
| **CONSERVATIVE** | 风险优先（40%权重） | 保守稳健策略 |
| **BALANCED** | 收益与风险平衡 | 通用场景 |
| **AGGRESSIVE** | 收益优先（65%权重） | 高风险高收益 |
| **VOLUME_FOCUSED** | 成交量优先（40%权重） | 刷量/做市场景 |

### 4. 约束检查

调度器在选择任务前会检查：

- ✅ 全局最大并发数限制
- ✅ 单交易所最大并发数限制
- ✅ 单交易所最大在途名义金额限制
- ✅ 交易所黑名单
- ✅ 交易对黑名单（快市/异常波动）
- ✅ 资金可用性（与 CapitalOrchestrator 集成）
- ✅ 最低评分门槛

### 5. 贪心调度算法

每次 `tick()` 调用执行以下流程：

```python
1. 过滤不满足约束的任务
2. 计算每个候选任务的 final_score
3. 按评分降序排序
4. 贪心选择任务，直到：
   - 达到全局/单所并发上限
   - 或没有合格任务
5. 为选中任务预留资金并提交执行
```

## 使用示例

### 基础用法

```python
from perpbot.hedge_scheduler import (
    HedgeJob, HedgeScheduler, JobSource, RiskMode, SchedulerConfig
)

# 1. 创建调度器
config = SchedulerConfig(
    max_global_concurrent_jobs=10,
    max_concurrent_per_exchange=3,
    risk_mode=RiskMode.BALANCED,
    min_score_threshold=30.0,
)
scheduler = HedgeScheduler(config=config)

# 2. 注册执行器
def my_arbitrage_executor(job: HedgeJob):
    # 执行套利逻辑
    pass

scheduler.register_executor(JobSource.ARBITRAGE, my_arbitrage_executor)

# 3. 提交任务
job = HedgeJob(
    symbol="BTC/USDT",
    exchanges={"binance", "okx"},
    notional=5000.0,
    expected_edge_bps=25.0,  # 0.25% 收益
    expected_pnl=12.5,
    risk_score=30.0,
    source=JobSource.ARBITRAGE,
)
job_id = scheduler.submit_job(job)

# 4. 运行调度
result = scheduler.tick()
print(f"调度成功: {result['scheduled']}, 拒绝: {result['rejected']}")

# 5. 任务完成回调
scheduler.on_job_finished(job_id, {
    "success": True,
    "pnl": 11.8,
    "volume": 10000.0,
})

# 6. 查看状态
state = scheduler.get_scheduler_state()
print(f"待调度: {state['pending_count']}, 运行中: {state['running_count']}")
```

### 集成 CapitalOrchestrator

```python
from perpbot.capital_orchestrator import CapitalOrchestrator

capital = CapitalOrchestrator(...)
scheduler = HedgeScheduler(
    capital_orchestrator=capital,
    config=config
)

# 调度器会自动调用 capital.reserve_for_strategy() 预留资金
# 任务完成后自动调用 capital.release() 释放资金
```

### 主循环集成

```python
import asyncio

async def trading_loop():
    while True:
        # 执行一次调度
        result = scheduler.tick()

        # 每 2 秒调度一次
        await asyncio.sleep(2)
```

### 监控集成

```python
# 在 Web API 中暴露调度器状态
@app.get("/api/scheduler/state")
def get_scheduler_state():
    return scheduler.get_scheduler_state()

# 返回示例：
# {
#     "pending_count": 3,
#     "running_count": 5,
#     "completed_count": 42,
#     "total_pnl": 285.6,
#     "total_volume": 500000.0,
#     "exchange_running": {"binance": 2, "okx": 3},
#     "top_pending_jobs": [...]
# }
```

## 运行 Demo

```bash
# 运行演示脚本
PYTHONPATH=src python -m perpbot.demos.hedge_scheduler_demo
```

Demo 演示了：
- 提交 7 个不同类型的任务
- 执行 2 轮调度
- 模拟任务完成
- 展示不同风险模式下的评分差异

## 核心类和方法

### HedgeJob

```python
@dataclass
class HedgeJob:
    job_id: str
    symbol: str
    exchanges: Set[str]
    notional: float
    expected_edge_bps: float
    expected_pnl: float
    risk_score: float      # 0-100
    latency_score: float   # 0-100
    vol_score: float       # 0-100
    funding_score: float   # 0-100
    liquidity_score: float # 0-100
    status: JobStatus
    source: JobSource
    metadata: Dict

    def calculate_final_score(
        risk_mode: RiskMode,
        custom_weights: Optional[Dict] = None
    ) -> float
```

### HedgeScheduler

```python
class HedgeScheduler:
    def __init__(
        capital_orchestrator: Optional[CapitalOrchestrator],
        config: Optional[SchedulerConfig]
    )

    def register_executor(source: JobSource, executor_func: Callable)
    def submit_job(job: HedgeJob) -> str
    def cancel_job(job_id: str) -> bool
    def tick() -> Dict  # 执行一次调度
    def on_job_finished(job_id: str, result: Dict)
    def get_scheduler_state() -> Dict
    def clear_history(keep_recent: int = 100)
```

### SchedulerConfig

```python
@dataclass
class SchedulerConfig:
    max_global_concurrent_jobs: int = 10
    max_concurrent_per_exchange: int = 3
    max_notional_per_exchange: float = 50000.0
    risk_mode: RiskMode = RiskMode.BALANCED
    min_score_threshold: float = 30.0
    exchange_blacklist: Set[str] = set()
    symbol_blacklist: Set[str] = set()
```

## 与现有模块的集成点

### 1. 套利模块集成

```python
# 在 arbitrage_executor.py 中
from perpbot.hedge_scheduler import HedgeJob, JobSource

def submit_arbitrage_opportunity(opp: ArbitrageOpportunity):
    job = HedgeJob(
        symbol=opp.symbol,
        exchanges={opp.buy_exchange, opp.sell_exchange},
        notional=opp.size * opp.buy_price,
        expected_edge_bps=opp.net_profit_pct * 10000,
        expected_pnl=opp.expected_pnl,
        risk_score=calculate_risk_score(opp),
        liquidity_score=opp.liquidity_score,
        source=JobSource.ARBITRAGE,
        metadata={"opportunity": opp}
    )
    scheduler.submit_job(job)
```

### 2. 刷量引擎集成

```python
# 在 hedge_volume_engine.py 中
def submit_hedge_volume_task(symbol, exchanges, notional):
    job = HedgeJob(
        symbol=symbol,
        exchanges=set(exchanges),
        notional=notional,
        expected_edge_bps=0.0,  # 刷量不追求收益
        vol_score=95.0,  # 高成交量贡献
        source=JobSource.HEDGE_VOLUME,
    )
    scheduler.submit_job(job)
```

### 3. Web 控制台集成

在 `monitoring/web_console.py` 中添加接口：

```python
@app.get("/api/scheduler/state")
async def get_scheduler_state():
    return scheduler.get_scheduler_state()

@app.post("/api/scheduler/config")
async def update_scheduler_config(risk_mode: str):
    scheduler.config.risk_mode = RiskMode(risk_mode)
    return {"status": "ok"}
```

## 扩展建议

1. **异步执行器**：当前执行器是同步的，生产环境应改为异步
2. **持久化**：将任务历史保存到数据库
3. **更多约束**：可添加交易对级别并发限制、时间窗口限制等
4. **动态权重**：根据市场条件动态调整评分权重
5. **优先级队列**：使用堆优化大量任务场景下的排序性能

## 文件结构

```
src/perpbot/
├── hedge_scheduler.py              # 调度器核心模块
└── demos/
    └── hedge_scheduler_demo.py     # 演示脚本
```

## 许可

与主项目保持一致
