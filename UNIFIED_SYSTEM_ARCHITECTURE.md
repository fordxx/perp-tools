# 统一资金中枢 + 风控中枢 + 对冲任务调度系统架构

## 🎯 系统目标

升级 perp 多交易所系统为完整的"统一资金中枢 + 风控中枢 + 对冲任务调度 + 完整监控面板"架构，实现多交易所、多交易对的低风险对冲成交/套利系统（自然产生大量成交量，非违规洗盘）。

## 📐 四大核心模块

### A. 三层极简资金模型（CoreCapitalOrchestrator） ✅ **已完成**

**文件**: `src/perpbot/core_capital_orchestrator.py`

**核心功能**：
- ✅ S1 (wash_pool): 70% - 刷量/对冲成交层
- ✅ S2 (arb_pool): 20% - 微利套利/机会增强层
- ✅ S3 (reserve_pool): 10% - 风控备用/救火层
- ✅ 按交易所维度管理资金
- ✅ 支持多对刷量并发

**关键方法**：
```python
update_equity(exchange, equity)              # 更新交易所权益
reserve_for_wash(exchange, amount)           # S1 池预留
reserve_for_arb(exchange, amount)            # S2 池预留
release(exchange, amount, pool)              # 释放资金
can_reserve_for_job(job)                     # 检查任务是否可预留
reserve_for_job(job)                         # 为任务实际锁定资金
record_pnl(exchange, pnl, volume, fees)      # 记录 PnL
current_snapshot()                           # 获取资金快照
```

**约束机制**：
- ✅ 单笔占用 ≤ 10% (可配置 `max_single_reserve_pct`)
- ✅ 总在途 ≤ 30% (可配置 `max_total_notional_pct`)
- ✅ 安全模式下仅允许 S1_wash + S3_reserve

**Demo**: `src/perpbot/demos/core_capital_demo.py` - 已测试通过 ✅

---

### B. 风控中枢与风险模式（EnhancedRiskManager） 🚧 **规划中**

**文件**: `src/perpbot/enhanced_risk_manager.py` (待实现)

**风险维度**：
1. **资金费率风险 (Funding)**
   - 双边资金费率差值检查
   - 资金费率结算黑窗检测 (`blackout_minutes`)
   - 方向是否对冲验证

2. **价差 + 滑点风险 (Spread & Slippage)**
   - 基于盘口 bid/ask 和深度估算执行价
   - 检查：预期收益 ≥ 手续费 + 滑点 - max_acceptable_loss_bps

3. **延迟风险 (Latency)**
   - 各交易所下单→成交平均延迟统计
   - 高延迟交易所降低评分或直接拒绝

4. **波动风险 (Volatility)**
   - 最近 N 秒波动率监控
   - 点差异常放大检测

5. **杠杆 / 爆仓距离 (Leverage)**
   - 对冲两腿预估爆仓价检查
   - 低杠杆安全要求

6. **当日损失限制 (Daily Loss)**
   - `daily_loss_limit_pct` 或固定金额
   - 超限自动拒绝新任务

7. **连续失败保护 (Consecutive Failures)**
   - `max_consecutive_failures` 触发 `auto_halt`

**风险模式** (RiskMode enum):
```python
class RiskMode(Enum):
    CONSERVATIVE = "conservative"  # 严格：min_edge≥5bps, vol_threshold=0.4%
    BALANCED = "balanced"          # 均衡：min_edge≥3bps, vol_threshold=0.6%
    AGGRESSIVE = "aggressive"      # 激进：min_edge≥1.5bps, vol_threshold=1%
```

**评分公式**：
```python
safety_score = f(
    funding,      # 资金费率安全性
    volatility,   # 波动率
    latency,      # 延迟
    leverage,     # 杠杆安全性
    drawdown,     # 回撤状态
    failures      # 连续失败次数
)

volume_score = g(
    notional,                    # 任务名义金额
    daily_volume_gap             # 与目标量的差距
)

final_score = (
    w1 * safety_score +          # conservative: w1=0.8
    w2 * volume_score            # balanced: w1=0.65, w2=0.35
)                                # aggressive: w1=0.55, w2=0.45
```

**人工 Override**：
```python
# 当 auto_halt=True 时
if manual_override:
    # 允许继续，但：
    # 1. 硬风控仍生效（daily_loss_limit, 爆仓风险）
    # 2. 日志明确标记"人工覆盖模式"
    logger.warning("⚠️ 在人工覆盖模式下接受任务")
```

**核心方法**：
```python
evaluate_job(job, market_data) -> (
    decision: "accept" | "reject",
    safety_score: float,
    volume_score: float,
    final_score: float,
    reason: Optional[str]
)

update_market_volatility(symbol, price)
update_exchange_latency(exchange, latency_ms)
update_funding_rate(exchange, symbol, rate)
record_failure() / record_success()
set_risk_mode(mode: RiskMode)
manual_override(enabled: bool)
```

---

### C. 多对冲任务调度器（UnifiedHedgeScheduler） 🚧 **规划中**

**文件**: `src/perpbot/unified_hedge_scheduler.py` (待实现)

**HedgeJob 模型**：
```python
@dataclass
class Leg:
    exchange: str
    side: Literal["buy", "sell"]
    quantity: float
    instrument: str  # 合约类型

@dataclass
class HedgeJob:
    job_id: str
    strategy_type: str           # "wash", "arb", "hedge_rebalance"
    symbol: str                  # "BTC/USDT"
    legs: List[Leg]              # 多腿对冲
    exchanges: Set[str]          # 从 legs 推导
    notional: float              # 名义金额
    expected_edge_bps: float     # 预期收益（基点）
    est_volume: float            # 预计贡献成交量
    created_at: datetime
    metadata: Dict[str, Any]
```

**调度器状态**：
```python
pending_jobs: PriorityQueue[HedgeJob]  # 按 final_score 排序
running_jobs: Dict[str, JobInfo]       # job_id -> 执行信息
finished_jobs: List[JobSummary]        # 最近完成的任务
per_exchange_concurrent: Dict[str, int]  # 各所并发数
```

**调度参数**：
```python
MAX_GLOBAL_CONCURRENT_JOBS = 50
MAX_CONCURRENT_PER_EXCHANGE = 10
MAX_NOTIONAL_PER_EXCHANGE = 50000.0
risk_mode: RiskMode  # 透传给 RiskManager
```

**调度主循环** (tick()):
```
1. 获取 pending_jobs
2. For each job:
   - 调用 RiskManager.evaluate_job() 获取评分和决策
   - 过滤被拒绝的 job
   - 过滤资金不足 / 并发超限 / 快市黑名单等
3. 按 final_score 降序排序
4. 贪心选择：
   - 检查交易所并发数与 notional 限制
   - 调用 CapitalOrchestrator.reserve_for_job()
   - 成功则移入 running_jobs，交给执行模块
5. 等待执行完成回调 on_job_finished()
   - 释放资金
   - 记录 PnL / volume
```

**核心方法**：
```python
submit_job(job: HedgeJob)
tick()  # 每次调度决策
on_job_finished(job_id, result: Dict)
get_scheduler_state() -> Dict  # 监控展示
```

---

### D. 监控状态结构（UnifiedMonitoringState） 🚧 **规划中**

**文件**: `src/perpbot/monitoring/unified_monitoring_state.py` (待实现)

**顶层结构**：
```python
@dataclass
class UnifiedMonitoringState:
    # 全局统计
    global_stats: GlobalStats

    # 资金统计 (按交易所)
    capital_stats: Dict[str, ExchangeCapitalStats]

    # 交易所统计
    exchange_stats: Dict[str, ExchangeStats]

    # 任务统计
    jobs_stats: JobsStats

    # 风控统计
    risk_stats: RiskStats

    # 行情统计
    market_stats: Dict[str, Dict[str, MarketData]]

    last_update: datetime
```

**GlobalStats**：
```python
@dataclass
class GlobalStats:
    system_status: Literal["running", "paused", "manual_override"]
    risk_mode: str
    today_volume_usd: float
    today_fees_usd: float
    today_pnl_usd: float
    daily_loss_limit: float
    daily_loss_used: float
```

**CapitalStats**：
```python
@dataclass
class ExchangeCapitalStats:
    exchange: str
    equity: float
    wash_used: float
    wash_budget: float
    arb_used: float
    arb_budget: float
    reserve_size: float
    total_in_flight: float
```

**ExchangeStats**：
```python
@dataclass
class ExchangeStats:
    exchange: str
    api_latency_ms: float
    open_positions_count: int
    funding_rates: Dict[str, float]  # symbol -> rate
    concurrent_jobs_count: int
    safe_mode: bool
```

**JobsStats**：
```python
@dataclass
class JobsStats:
    running_jobs: List[RunningJobSummary]
    pending_jobs_count: int
    completed_today: int
    failed_today: int
    recent_completed: List[JobSummary]
```

**RiskStats**：
```python
@dataclass
class RiskStats:
    fast_markets: List[str]           # 快市符号
    delayed_exchanges: List[str]      # 高延迟交易所
    consecutive_failures: int
    auto_halt: bool
    manual_override: bool
```

**MarketData**：
```python
@dataclass
class MarketData:
    symbol: str
    last: float
    bid: float
    ask: float
    spread: float
    short_term_volatility: float
    timestamp: datetime
```

**更新机制**：
```python
# 各模块定期更新 MonitoringState
capital_orchestrator.update_monitoring_state(state)
risk_manager.update_monitoring_state(state)
hedge_scheduler.update_monitoring_state(state)
market_data_bus.update_monitoring_state(state)

# Web 控制台只读
@app.get("/api/monitoring/state")
async def get_state():
    return monitoring_state.to_dict()
```

---

## 🔗 模块集成流程

### 1. 任务提交流程

```
Strategy Module (e.g., WashTradeStrategy)
    ↓
  creates HedgeJob
    ↓
HedgeScheduler.submit_job(job)
    ↓
  adds to pending_jobs queue
```

### 2. 调度执行流程

```
HedgeScheduler.tick()
    ↓
For each pending job:
    ↓
  RiskManager.evaluate_job(job) → (decision, scores)
    ↓
  if decision == "reject": skip
    ↓
  CapitalOrchestrator.can_reserve_for_job(job) → bool
    ↓
  if cannot reserve: skip
    ↓
  Sort by final_score (descending)
    ↓
Greedy selection:
    ↓
  CapitalOrchestrator.reserve_for_job(job)
    ↓
  if success:
      move to running_jobs
      call ExecutionModule.execute(job)
```

### 3. 任务完成流程

```
ExecutionModule finishes job
    ↓
  calls HedgeScheduler.on_job_finished(job_id, result)
    ↓
HedgeScheduler:
    - CapitalOrchestrator.release()
    - CapitalOrchestrator.record_pnl()
    - RiskManager.record_success() / record_failure()
    - MonitoringState.update_stats()
```

---

## 📊 监控与控制

### Web 控制台接口

```python
GET  /api/monitoring/state          # 获取完整状态
GET  /api/capital/snapshot           # 资金快照
GET  /api/jobs/running               # 运行中任务
GET  /api/jobs/pending               # 待调度任务

POST /api/control/pause              # 暂停系统
POST /api/control/resume             # 恢复运行
POST /api/control/set_risk_mode      # 切换风险模式
POST /api/control/manual_override    # 人工覆盖
```

### CLI 命令

```bash
# 查看状态
PYTHONPATH=src python -m perpbot.cli status

# 切换风险模式
PYTHONPATH=src python -m perpbot.cli set-risk-mode aggressive

# 暂停/恢复
PYTHONPATH=src python -m perpbot.cli pause
PYTHONPATH=src python -m perpbot.cli resume
```

---

## ⚠️ 硬风控规则（不可覆盖）

即使在 `manual_override=True` 时，以下硬风控仍生效：

1. **Daily Loss Limit**: 当日亏损超限时绝对拒绝
2. **爆仓风险**: 预估爆仓距离过近时绝对拒绝
3. **资金不足**: 无可用资金时绝对拒绝
4. **交易所熔断**: API 完全不可用时绝对拒绝

人工覆盖只能绕过软风控（如波动率阈值、延迟阈值等）。

---

## 📁 文件结构

```
src/perpbot/
├── core_capital_orchestrator.py      ✅ 已完成
├── enhanced_risk_manager.py          🚧 待实现
├── unified_hedge_scheduler.py        🚧 待实现
│
├── monitoring/
│   └── unified_monitoring_state.py   🚧 待实现
│
├── demos/
│   ├── core_capital_demo.py          ✅ 已完成
│   ├── enhanced_risk_demo.py         🚧 待实现
│   ├── unified_scheduler_demo.py     🚧 待实现
│   └── full_system_demo.py           🚧 待实现
│
└── integration/
    └── unified_system.py              🚧 待实现 (集成所有模块)
```

---

## 🚀 实施计划

### Phase 1: 核心资金管理 ✅ **已完成**
- [x] CoreCapitalOrchestrator 实现
- [x] Demo 和测试
- [x] 文档

### Phase 2: 风控中枢 🚧 **进行中**
- [ ] EnhancedRiskManager 实现
- [ ] 多维度风险评估
- [ ] Demo 和测试

### Phase 3: 任务调度器 📋 **计划中**
- [ ] UnifiedHedgeScheduler 实现
- [ ] HedgeJob 模型定义
- [ ] 调度主循环
- [ ] Demo 和测试

### Phase 4: 监控系统 📋 **计划中**
- [ ] UnifiedMonitoringState 实现
- [ ] Web 控制台集成
- [ ] 实时状态更新

### Phase 5: 系统集成 📋 **计划中**
- [ ] 模块间接口对接
- [ ] 完整系统测试
- [ ] 性能优化

---

## 📝 使用示例

### 完整系统启动

```python
from perpbot.integration.unified_system import UnifiedSystem

# 创建系统实例
system = UnifiedSystem(
    risk_mode=RiskMode.BALANCED,
    exchanges=["binance", "okx", "edgex", "paradex"],
)

# 初始化权益
system.capital.update_equity("binance", 50000.0)
system.capital.update_equity("okx", 30000.0)

# 启动系统
await system.start()

# 提交任务
job = HedgeJob(
    symbol="BTC/USDT",
    strategy_type="wash",
    exchanges={"binance", "okx"},
    notional=5000.0,
    expected_edge_bps=2.0,
)

system.scheduler.submit_job(job)

# 运行调度循环
while True:
    system.scheduler.tick()
    await asyncio.sleep(2)
```

---

## 📚 相关文档

- [CAPITAL_DOWNGRADE_README.md](./CAPITAL_DOWNGRADE_README.md) - 三层资金系统详细说明
- [HEDGE_SCHEDULER_README.md](./HEDGE_SCHEDULER_README.md) - 任务调度器使用指南

---

**最后更新**: 2025-12-06
**状态**: Phase 1 完成，Phase 2-5 规划中
