# 资金系统安全降级重构说明

## 🎯 重构目标

将复杂的五层资金系统（L1-L5）安全降级为对外的三层抽象（S1/S2/S3），简化策略模块的资金访问接口，同时保持内部兼容性。

## 📊 三层资金模型

### 对外接口（所有策略模块使用）

| 资金池 | 用途 | 默认占比 | 内部映射 |
|--------|------|----------|----------|
| **S1 (wash_pool)** | 刷量/对冲成交主层 | 70% | L1 + L2 |
| **S2 (arb_pool)** | 微利套利增强层 | 20% | L3 |
| **S3 (reserve_pool)** | 风险备用层 | 10% | L4 + L5 |

### 内部映射关系（隐藏）

```
L1 (刷量层1) ──┐
L2 (刷量层2) ──┴─→ S1_wash (刷量对冲主层, 70%)

L3 (套利层)   ────→ S2_arb (套利增强层, 20%)

L4 (底仓层)   ──┐
L5 (安全层)   ──┴─→ S3_reserve (风险备用层, 10%)
```

## 🔧 核心变更

### 1. 新增资金管理模块

**文件**: `src/perpbot/capital/simple_capital_orchestrator.py`

```python
from perpbot.capital import SimpleCapitalOrchestrator, CapitalPool

# 创建资金调度器
capital = SimpleCapitalOrchestrator(
    wu_size=10_000.0,
    s1_wash_pct=0.70,   # S1: 70%
    s2_arb_pct=0.20,    # S2: 20%
    s3_reserve_pct=0.10 # S3: 10%
)

# 刷量任务使用 S1
reservation = capital.reserve_wash("binance", 3000.0)

# 套利任务使用 S2
reservation = capital.reserve_arb("okx", 1500.0)

# 紧急情况使用 S3（不推荐）
reservation = capital.reserve_reserve("edgex", 500.0)

# 释放资金
capital.release(reservation)
```

### 2. HedgeScheduler 自动池选择

**修改**: `src/perpbot/hedge_scheduler.py`

调度器现在根据任务类型自动选择资金池：

```python
# 任务来源 → 资金池映射
HEDGE_VOLUME      → S1_wash   # 刷量任务
ARBITRAGE         → S2_arb    # 套利任务
MARKET_MAKING     → S2_arb    # 做市任务
MANUAL            → S2_arb    # 手动任务
```

**日志输出示例**：

```
[调度器] 任务 abc123 使用 S1_wash 池: binance 3000.00
[调度器] 任务 def456 使用 S2_arb 池: okx 1500.00
✅ [binance] 成功从 S1_wash 预留 3000.00
```

### 3. RiskManager 保持不变

**文件**: `src/perpbot/risk_manager.py`

风控层已经是统一评分，不区分 L 层级，无需修改。

## 🚀 快速开始

### 运行资金降级 Demo

```bash
PYTHONPATH=src python -m perpbot.demos.capital_downgrade_demo
```

**演示内容**：
- ✅ 基础资金预留与释放
- ✅ 安全模式触发与池限制
- ✅ 多交易所独立资金池
- ✅ 调试视图（显示 L1-L5 映射）

### 运行调度器联动 Demo

```bash
PYTHONPATH=src python -m perpbot.demos.scheduler_capital_demo
```

**演示内容**：
- ✅ 调度器根据任务类型自动选择池
- ✅ 资金不足时的任务拒绝
- ✅ 安全模式下的资金限制
- ✅ 实时状态监控

## 📋 API 接口

### SimpleCapitalOrchestrator

```python
class SimpleCapitalOrchestrator:
    """简化资金调度器"""

    def __init__(
        wu_size: float = 10_000.0,
        s1_wash_pct: float = 0.70,
        s2_arb_pct: float = 0.20,
        s3_reserve_pct: float = 0.10,
        drawdown_limit_pct: float = 0.05,
    )

    # 核心接口
    def reserve_wash(exchange: str, amount: float) -> CapitalReservation
    def reserve_arb(exchange: str, amount: float) -> CapitalReservation
    def reserve_reserve(exchange: str, amount: float) -> CapitalReservation
    def release(reservation: CapitalReservation) -> None

    # 状态管理
    def update_equity(exchange: str, equity: float) -> None
    def update_drawdown(exchange: str, drawdown_pct: float) -> None
    def record_volume_result(exchange: str, volume: float, fee: float, pnl: float) -> None

    # 监控接口
    def get_snapshot() -> Dict  # 对外：只显示 S1/S2/S3
    def get_debug_snapshot() -> Dict  # 调试：显示 L1-L5 映射
```

### CapitalReservation

```python
@dataclass
class CapitalReservation:
    approved: bool              # 是否批准
    pool: CapitalPool           # 使用的池 (S1/S2/S3)
    exchange: str               # 交易所
    amount: float               # 金额
    reason: Optional[str]       # 拒绝原因
```

## 🔒 安全模式

当交易所回撤超过阈值（默认 5%）时，自动进入安全模式：

```python
# 触发安全模式
capital.update_drawdown("binance", 0.06)  # 6% 回撤

# 安全模式下只允许使用 S1_wash + S3_reserve
# S2_arb 被禁用，所有套利任务会被拒绝
```

**允许的池**（可配置）：
- ✅ S1_wash（刷量对冲，继续提供流动性）
- ❌ S2_arb（套利，风险较高，被禁用）
- ✅ S3_reserve（备用资金，紧急情况）

## 📈 状态监控

### Web 控制台集成

```python
@app.get("/api/capital/state")
async def get_capital_state():
    return orchestrator.get_snapshot()

# 返回示例：
{
    "binance": {
        "equity": 10000.0,
        "safe_mode": false,
        "pools": {
            "S1_wash": {
                "pool_size": 7000.0,
                "allocated": 3000.0,
                "available": 4000.0,
                "utilization_pct": 42.9
            },
            "S2_arb": { ... },
            "S3_reserve": { ... }
        }
    }
}
```

### 调试视图

```python
# 仅限开发/调试使用
debug_snapshot = orchestrator.get_debug_snapshot()

# 额外包含内部映射信息：
{
    "binance": {
        "pools": { ... },
        "internal_mapping": {
            "S1_wash": ["L1", "L2"],
            "S2_arb": ["L3"],
            "S3_reserve": ["L4", "L5"]
        }
    }
}
```

## ⚠️ 迁移注意事项

### ✅ 允许的操作

```python
# ✅ 通过 SimpleCapitalOrchestrator 访问 S1/S2/S3
capital.reserve_wash("binance", 3000.0)
capital.reserve_arb("okx", 1500.0)

# ✅ 调度器自动选择资金池
scheduler.submit_job(hedge_job)  # 自动使用 S1
scheduler.submit_job(arb_job)    # 自动使用 S2
```

### ❌ 禁止的操作

```python
# ❌ 禁止直接访问 L1-L5 层级
# 旧代码：capital.reserve_for_strategy(exchanges, amount, "L1")  # 错误！

# ❌ 禁止策略模块绕过资金系统
# 直接下单而不预留资金  # 错误！

# ❌ 禁止在代码中硬编码 L 层级概念
# if layer == "L4": ...  # 错误！应使用 S3_reserve
```

## 📊 日志规范

所有日志必须使用 S1/S2/S3，禁止暴露 L 层级：

```python
# ✅ 正确
logger.info("[调度器] 任务 %s 使用 S1_wash 池", job_id)
logger.info("✅ [%s] 成功从 S2_arb 预留 %.2f", exchange, amount)

# ❌ 错误
logger.info("使用 L1 层资金")  # 不要暴露内部实现
logger.info("预留 L3 资金")    # 应使用 S2_arb
```

## 🧪 测试

两个完整的演示脚本已通过测试：

```bash
# 资金系统降级演示
PYTHONPATH=src python -m perpbot.demos.capital_downgrade_demo
✅ 演示 1: 基础资金预留与释放
✅ 演示 2: 安全模式触发与限制
✅ 演示 3: 多交易所独立资金池
✅ 演示 4: 调试视图（L1-L5 映射）

# 调度器联动演示
PYTHONPATH=src python -m perpbot.demos.scheduler_capital_demo
✅ 演示 1: 调度器与资金系统基础集成
✅ 演示 2: 资金不足时的任务拒绝
✅ 演示 3: 安全模式下的资金限制
✅ 演示 4: 调度器状态监控
```

## 📁 文件结构

```
src/perpbot/
├── capital/                          # 新增资金管理模块
│   ├── __init__.py
│   └── simple_capital_orchestrator.py  # 三层资金调度器
│
├── hedge_scheduler.py                # 已修改：集成三层资金接口
│
├── demos/
│   ├── capital_downgrade_demo.py     # 资金降级演示
│   └── scheduler_capital_demo.py     # 调度器联动演示
│
├── capital_orchestrator.py           # 旧版（兼容保留）
└── risk_manager.py                   # 无需修改
```

## 🎉 迁移收益

1. **简化接口**：3 个方法 vs 复杂的 5 层配置
2. **清晰分工**：刷量用 S1，套利用 S2，应急用 S3
3. **自动选择**：调度器根据任务类型自动选池
4. **日志友好**：所有日志使用 S1/S2/S3，易于理解
5. **向后兼容**：内部保留 L1-L5 映射，平滑迁移
6. **多所独立**：每个交易所独立管理三层资金池

## 📞 联系方式

如有问题，请查看：
- 演示脚本：`src/perpbot/demos/capital_downgrade_demo.py`
- 调度器演示：`src/perpbot/demos/scheduler_capital_demo.py`
- 源代码：`src/perpbot/capital/simple_capital_orchestrator.py`
