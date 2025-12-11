# PerpBot - 多交易所模块化自动套利机器人

[![Python](https.img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Development-yellow.svg)](https://github.com/fordxx/perp-tools)
[![Validation](https://img.shields.io/badge/System_Validation-92.0%2F100-brightgreen)](VALIDATION_REPORT.md)

> 🚀 **当前架构**: `V2 - Event-Driven`
> 🎯 **开发重点**: V2 架构稳定性与真实交易性能优化
> 💰 **测试规模**: 本金 1000 USDT，单笔约 10 USDT
> ✅ **系统验证**: [92.0/100 - 查看详细报告](VALIDATION_REPORT.md)

## 🎉 系统验证完成

**最新验证:** 2025-12-12
**验证分数:** **92.0/100** (0 failures, 39/45 tests passed)
**验证脚本:** `validate_perpbot_v2.py`

```bash
# 运行完整系统验证
python3 validate_perpbot_v2.py
```

**验证覆盖:**
- ✅ TOP1: RiskManager
- ✅ TOP2: ExecutionEngine V2
- ✅ TOP3: Exposure System V2
- ✅ TOP4: QuoteEngine V2
- ⚠️ TOP5: Capital System V2 (1 已知代码错误)
- ✅ TOP6: Scanner V3
- ✅ TOP7-10: EventBus, Health, Console, Integration

**查看详细报告:** [VALIDATION_REPORT.md](VALIDATION_REPORT.md)

---

## 📌 AI Developer Notice

> 本仓库允许多 AI 协作开发（ChatGPT / Claude / Cursor / Codeium）。  
> 所有 AI 在输出代码前必须阅读：
>
> **📄 `/docs/DEVELOPING_GUIDE.md`**
>
> AI 必须遵守：
> - 系统路线图
> - 模块边界
> - 限制与禁止清单
> - 文档更新规则
>
> 不允许随意偏离项目方向。

---

## 📑 目录

- [项目概述](#项目概述)
- [核心特性](#核心特性)
- [📊 系统 SLO (服务级别目标)](#-系统-slo-服务级别目标)
- [V2 系统架构](#v2-系统架构)
- [目录结构](#目录结构)
- [V2 模块详解](#v2-模块详解)
- [资金管理系统 V2](#资金管理系统-v2)
- [🏦 如何新增一个交易所？](#-如何新增一个交易所)
- [交易所集成状态](#交易所集成状态)
- [⚠️ 生产环境使用指南](#️-生产环境使用指南)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [安全指南](#安全指南)
- [API 文档](#api-文档)
- [测试流程](#测试流程)
- [常见问题](#常见问题)
- [术语表](#术语表)
- [更新日志](#更新日志)


---

## 项目概述

PerpBot 是一个**基于事件驱动和高度模块化**的自动交易框架，专注于多交易所套利和自动化交易策略。项目采用 V2 架构，通过中央**事件总线 (EventBus)** 解耦了所有核心组件。它支持 CEX 和 DEX 的统一接入，并提供了从宏观到微观的完整风控体系和实时监控系统。

### 设计理念

- **事件驱动 (V2)**: 核心组件通过发布/订阅模式进行异步通信，实现极致解耦。
- **模块化**: 每个交易所、策略、风控模块完全独立，可插拔。
- **安全第一**: 纵深防御的多层风控 + 密钥加密 + 权限最小化。
- **实时监控**: Web 控制台 + CLI 仪表盘 + 多渠道告警，全面展示实时系统状态。
- **灵活配置**: YAML 驱动，无需修改代码。

### 技术栈

- **语言**: Python 3.10+
- **异步框架**: asyncio
- **核心架构**: 事件总线 (Publish/Subscribe)
- **Web 框架**: FastAPI (REST API & WebSocket)
- **数据存储**: CSV / SQLite
- **监控**: Telegram / Lark / Webhook / Audio

---

## 核心特性

- **事件驱动架构 (V2)**: 基于中央事件总线，实现模块间零耦合，提升了系统的响应速度和可扩展性。
- **多交易所支持**: 已集成 **8** 个主流 CEX/DEX，包括 Starknet 上的 Paradex 和 Extended。
- **资金管理系统 (V2)**: 创新的 **分配器/编排器/快照供应器** 架构，实现动态风险敞口管理。
- **高性能套利引擎 (V2)**:
    - **QuoteEngineV2**: 统一处理多交易所行情流。
    - **ScannerV3**: 响应式价差扫描，亚秒级发现机会。
    - **ExecutionEngineV2**: 集成风控、资金和回退策略的智能执行。
- **统一风险敞口 (V2)**: **Position Aggregator V2** 聚合所有交易所的仓位，提供全局风险视图。
- **多层纵深风控**: 覆盖从资金层、账户级到仓位级的四层风险防护体系。
- **实时监控系统 (V2)**:
    - **HealthMonitor**: 监控所有组件心跳。
    - **ConsoleState**: 聚合系统状态，为 UI 提供数据。
    - **Web/CLI Dashboard**: 实时监控、在线调参和一键启停。

---

## 📊 系统 SLO (服务级别目标)

为了确保系统在真实交易中的高性能和高可靠性，我们设定了以下服务级别目标：

| 模块 | 目标 | 说明 |
|---|---|---|
| **行情延迟** | < 100ms | 从交易所收到 WebSocket 消息到 `QuoteEngineV2` 发布事件 |
| **扫描延迟** | < 30ms | `ScannerV3` 从收到行情事件到发现套利机会 |
| **执行决策延迟**| < 50ms | `ExecutionEngineV2` 完成风控、资金检查并制定计划 |
| **下单处理** | < 100ms | 从 `ExecutionEngineV2` 发出指令到交易所客户端完成 API 调用 |
| **风险检查** | 100% | 所有交易在执行前**必须**完成风险和资金检查 |
| **系统正常运行时间**| 99.9% | - |

---

## V2 系统架构

V2 架构的核心是 **EventBus**，它将原先的串行调用链路彻底重构为发布/订阅模式，实现了各核心组件的完全解耦。

### V2 迷你架构图 (5 核心模块)

```
┌───────────────────────────────┐
│  QuoteEngineV2  →  ScannerV3  │  →  机会发现
└───────────────────────────────┘
                 ↓
┌───────────────────────────────┐
│      ExecutionEngineV2        │  →  下单 / 风控 / 资金协调
└───────────────────────────────┘
                 ↓
┌───────────────────────────────┐
│ PositionAggregatorV2 + Capital│  →  风险与资金闭环
└───────────────────────────────┘
                 ↓
┌───────────────────────────────┐
│ HealthMonitor + ConsoleState  │  →  实时监控
└───────────────────────────────┘

    🚌 EventBus: 统一事件驱动 Backbone
```

### 系统运行路径示例
以 BTC-PERP 在 Paradex 与 Extended 出现套利机会为例，事件流如下：

1.  **行情更新**: `QuoteEngineV2` 分别收到 Paradex 和 Extended 的最新 BBO，发布两条 `QUOTE_UPDATED` 事件。
2.  **机会发现**: `ScannerV3` 监听到这两条事件，计算发现价差超过阈值，发布 `ARBITRAGE_OPPORTUNITY_FOUND` 事件。
3.  **决策制定**: `ExecutionEngineV2` 监听到机会事件，立即开始决策：
    - 调用 `RiskEngine` 检查全局敞口。
    - 调用 `CapitalOrchestratorV2` 申请并预留资金。
    - 根据 `FallbackPolicy` 决定使用 Maker 还是 Taker 单。
4.  **订单执行**: 决策通过，`ExecutionEngineV2` 在 Paradex（买）和 Extended（卖）同时下单，并发布两条 `ORDER_PLACED` 事件。
5.  **交易成交**: 交易所回报订单成交，`ExecutionEngineV2` 发布 `ORDER_FILLED` 事件。
6.  **状态更新 (闭环)**:
    - `PositionAggregatorV2` 监听到 `ORDER_FILLED`，更新全局 BTC 风险敞口。
    - `CapitalOrchestratorV2` 监听到 `ORDER_FILLED`，将预留资金标记为已分配。
7.  **监控更新**: `ConsoleState` 监听到所有事件，实时更新内存快照。`Web/CLI Dashboard` 随即展示最新的持仓和资金状态。`HealthMonitor` 确认所有组件仍在发送心跳。

### 整体架构图 (V2)

```mermaid
graph TD
    subgraph "UI / Control"
        WebConsole[Web Console]
        CLIDashboard[CLI Dashboard]
        Alerts[Alerts]
    end

    subgraph "Core System (Event-Driven)"
        EventBus[EventBus]

        subgraph "V2 Services"
            QuoteEngine[QuoteEngineV2]
            Scanner[ScannerV3]
            ExecutionEngine[ExecutionEngineV2]
            CapitalSystem[Capital System V2]
            PositionAggregator[Position Aggregator V2]
            HealthMonitor[Health Monitor]
        end
    end

    subgraph "Exchange Layer"
        ConnectionManager[Connection Manager]
        Paradex[Paradex Client]
        Extended[Extended Client]
        OKX[OKX Client]
        OtherClients[...]
    end

    %% V2 Data Flow via EventBus
    QuoteEngine -- "QUOTE_UPDATED" --> EventBus
    EventBus -- "QUOTE_UPDATED" --> Scanner
    Scanner -- "OPPORTUNITY_FOUND" --> EventBus
    EventBus -- "OPPORTUNITY_FOUND" --> ExecutionEngine
    
    ExecutionEngine -- "Requests" --> CapitalSystem
    ExecutionEngine -- "Checks" --> PositionAggregator
    
    ExecutionEngine -- "ORDER_PLACED/FILLED" --> EventBus
    EventBus -- "ORDER_FILLED" --> PositionAggregator
    EventBus -- "ORDER_FILLED" --> CapitalSystem

    %% Monitoring Flow
    subgraph "Monitoring & State"
        ConsoleState
    end
    EventBus -- "All Events" --> ConsoleState
    EventBus -- "Heartbeats/Errors" --> HealthMonitor
    HealthMonitor --> Alerts
    ConsoleState --> WebConsole
    ConsoleState --> CLIDashboard

    %% Exchange Interaction
    ExecutionEngine --> ConnectionManager
    ConnectionManager --> Paradex
    ConnectionManager --> Extended
    ConnectionManager --> OKX
    ConnectionManager --> OtherClients
    
    QuoteEngine --> ConnectionManager
```

---
## 目录结构

```
perp-tools/
├── src/perpbot/                      # 核心代码目录
│   ├── __init__.py
│   ├── models.py                     # 📦 数据模型 (V2 新增 Event)
│   ├── cli.py                        # 🖥️ CLI 入口 (cycle/serve)
│   ├── event_bus.py                  # 🚌 V2 事件总线
│   │
│   ├── capital/                      # 💰 V2 资金系统
│   │   ├── capital_allocator.py      #   - 分配器
│   │   ├── capital_orchestrator_v2.py#   - 编排器
│   │   ├── capital_snapshot.py       #   - 快照
│   │   └── capital_snapshot_provider.py # - 供应器
│   │
│   ├── connections/                  # 🔌 V2 连接管理
│   │   ├── exchange_connection_manager.py # - 统一连接管理器
│   │   └── ws_manager.py             #   - WebSocket 管理器
│   │
│   ├── console/                      # 📊 V2 监控与状态
│   │   ├── cli_dashboard.py          #   - CLI 仪表盘
│   │   └── console_state.py          #   - 中央状态机
│   │
│   ├── exchanges/                    # 🏦 交易所客户端
│   │   ├── base.py                   #   - 统一接口
│   │   └── ... (8个客户端)
│   │
│   ├── execution/                    # ⚡ V2 执行引擎
│   │   ├── execution_engine_v2.py    #   - 核心执行逻辑
│   │   ├── fallback_policy.py        #   - 回退策略
│   │   └── retry_policy.py           #   - 重试策略
│   │
│   ├── exposure/                     # 🛡️ V2 风险敞口
│   │   └── position_aggregator.py    #   - 持仓聚合器 V2
│   │
│   ├── health/                       # ❤️ V2 健康监控
│   │   └── health_monitor.py         #   - 组件心跳监控
│   │
│   ├── scanner/                      # 🔎 V2 行情与扫描
│   │   ├── quote_engine_v2.py        #   - 行情引擎 V2
│   │   └── scanner_v3.py             #   - 套利扫描器 V3
│   │
│   └── strategy/                     # 📈 策略层
│       └── take_profit.py            #   - 自动止盈策略
│
├── test_all_exchanges.py             # 🧪 通用交易所测试框架
├── docs/                             # 📚 文档目录
├── config.example.yaml               # ⚙️ 配置模板
├── requirements.txt                  # 📦 Python 依赖
└── .env.example                      # 🔐 环境变量模板
```

---

## V2 模块详解

### 1. EventBus (事件总线)
- **核心作用**: 系统的大脑中枢，负责所有事件的派发。
- **工作机制**: 使用发布/订阅模式。一个组件可以发布事件，而一个或多个其他组件可以订阅并响应这些事件。
- **优点**: 实现了组件间的完全解耦，任何组件都可以被独立替换或升级，只要它遵守事件契约。

#### 🚌 Event Schema (EventType & Payload)
所有组件间通信都必须遵守以下事件格式规范。

| EventType | Payload 内容 | 说明 |
|---|---|---|
| `QUOTE_UPDATED` | `{symbol, bid, ask, bid_size, ask_size, exchange, ts}` | 行情更新 |
| `ARBITRAGE_OPPORTUNITY_FOUND` | `{symbol, buy_exchange, sell_exchange, spread_pct}` | 发现套利机会 |
| `ORDER_PLACED` | `{order_id, symbol, exchange, side, size, price}` | 订单已提交 |
| `ORDER_FILLED` | `{order_id, fill_price, fill_size, fee, is_partial}` | 订单已成交 |
| `ORDER_CANCELLED`| `{order_id}` | 订单已取消 |
| `TRADE_COMPLETED`| `{buy_order, sell_order, realized_pnl}` | 一对套利交易完成 |
| `CAPITAL_SNAPSHOT_UPDATE`| `{[exchange]: {free, locked, total}}` | 资金快照更新 |
| `POSITION_UPDATED`| `{[exchange]: {[symbol]: position}}` | 全局仓位更新 |
| `HEARTBEAT` | `{component_name, status, ts}` | 组件心跳 |


### 2. QuoteEngineV2 (行情引擎V2)
- **职责**: 作为所有市场行情的唯一入口。
- **工作流程**: 通过 `ExchangeConnectionManager` 连接到所有交易所，订阅行情数据流，然后将它们标准化为统一的 `Quote` 对象，并作为 `QUOTE_UPDATED` 事件发布出去。

#### ✨ 如何扩展？
要添加自定义的行情处理逻辑（如 VWAP 计算），可以监听 `QUOTE_UPDATED` 事件并发布新的衍生事件。
```python
class VwapQuoteEngine:
    def __init__(self, event_bus):
        self._event_bus = event_bus
        self._event_bus.subscribe(EventType.QUOTE_UPDATED, self.on_quote)

    async def on_quote(self, event: Event):
        # ... 计算 VWAP ...
        vwap_event = Event(EventType.VWAP_QUOTE_UPDATED, new_quote)
        await self._event_bus.publish(vwap_event)
```

### 3. ScannerV3 (套利扫描器V3)
- **V2 改进**: 从轮询模式变为事件驱动模式，响应更迅速。
- **工作流程**: 订阅 `QUOTE_UPDATED` 事件。每当有新的报价，它会立刻被激活，计算跨所价差。如果发现机会，它会发布 `ARBITRAGE_OPPORTUNITY_FOUND` 事件。

#### ✨ 如何扩展？
要实现新的套利策略（如三角套利），可以继承 `BaseScanner` 并实现自定义逻辑。
```python
class TriangleScanner(BaseScanner):
    async def on_quote(self, event: Event):
        # 1. 收到 quote，更新内部行情板
        self.update_board(event.payload)

        # 2. 检查三角套利条件 (e.g., A/B -> B/C -> C/A)
        if opportunities := self.check_triangle_opportunities():
            for opp in opportunities:
                new_event = Event(EventType.TRIANGLE_OPPORTUNITY_FOUND, opp)
                await self._event_bus.publish(new_event)
```

### 4. ExecutionEngineV2 (执行引擎V2)
- **V2 改进**: 成为一个集决策与执行于一体的智能中心。
- **工作流程**: 订阅 `ARBITRAGE_OPPORTUNITY_FOUND` 事件，然后向风控和资金模块查询，通过后执行下单，并发布订单状态事件。

#### ✨ 如何扩展？
要增加新的风控规则，可以在 `ExecutionEngineV2` 的执行计划中加入一个新的检查步骤。
```python
# In ExecutionEngineV2.execute_plan
async def execute_plan(self, plan: ExecutionPlan):
    # ...
    # 增加自定义检查
    if not await self.custom_risk_check(plan):
        return  # Abort
    # ...
```

### 5. Position Aggregator V2 (风险敞口与持仓聚合器)
- **核心价值**: 提供全局统一的风险视图。
- **工作流程**: 订阅 `ORDER_FILLED` 和 `TRADE_COMPLETED` 事件，实时更新内部维护的、跨所有交易所的统一持仓列表。

### 6. Health, Monitoring & Console (健康监控与控制台)
- **职责**: 确保系统稳定运行并提供可视化界面。
- **工作流程**: `HealthMonitor` 监听心跳，`ConsoleState` 聚合所有事件，`Web/CLI Dashboard` 从 `ConsoleState` 读取数据进行展示。

---

## 资金管理系统 V2
原有的三层资金模型（刷量/套利/储备）在 V2 中被保留，但底层实现升级为更健壮的**三组件架构**，以更好地支持事件驱动模式。

### V2 三组件架构

#### 1. 🔵 CapitalSnapshotProvider
- **职责**: 唯一的资金信息来源。定期或由事件触发，从所有交易所获取最新余额。

#### 2. 🟢 CapitalAllocator
- **职责**: 应用三层资金池逻辑。基于快照和配置，将资金分配到不同的逻辑池。

#### 3. 🟡 CapitalOrchestratorV2
- **职责**: 交易执行的资金接口。为 `ExecutionEngineV2` 提供资金预留接口，并订阅 `ORDER_FILLED` 事件来更新资金占用。

---

## 🏦 如何新增一个交易所？
系统具有良好的扩展性，新增一个交易所通常遵循以下步骤：

1.  **实现 BaseExchange 接口**:
    在 `src/perpbot/exchanges/` 目录下创建一个新的客户端文件，如 `my_exchange_client.py`。让你的客户端类继承 `BaseExchange`。
    ```python
    from .base import BaseExchange

    class MyExchangeClient(BaseExchange):
        # ...
    ```

2.  **补齐核心方法**:
    你必须实现 `BaseExchange` 中定义的所有抽象方法，主要包括：
    - `connect()`
    - `get_current_price()`
    - `place_order()`
    - `cancel_order()`
    - `get_active_orders()`
    - `get_account_positions()`
    - `get_account_balances()`

3.  **注册进 ConnectionManager**:
    在 `ExchangeConnectionManager` 中，将你的新客户端加入到 `SUPPORTED_EXCHANGES` 字典中。

4.  **提供 Symbol Mapping (如果需要)**:
    如果新交易所的交易对命名与其他交易所不同，你需要在配置或常量中提供一个映射关系。

5.  **运行通用测试框架**:
    使用 `test_all_exchanges.py` 脚本来验证你的新客户端是否符合所有接口规范。

---

## 交易所集成状态
*本节内容保持不变，包含 8 个已集成的交易所列表。*

---

## ⚠️ 生产环境使用指南
在真实交易中使用本系统存在极高风险。请严格遵守以下安全指南：

- **从 1 USDT 开始**: 初始测试务必使用您完全可以承受损失的极小金额（如 1 USDT）开始。
- **强制开启日志**: `config.yaml` 中的日志记录必须开启 `FILE` 模式，以便在出现问题时进行复盘。
- **先用只读模式测试**: 在配置真实交易密钥之前，先使用只读权限的 API Key 运行系统至少 48 小时，确保行情和监控系统稳定。
- **监控系统先行**: 在开启任何交易策略之前，确保 `HealthMonitor`, `ConsoleState` 和 `Web/CLI Dashboard` 已稳定运行并能正确反映市场状态。
- **首次实盘关闭回退**: 首次进行真实交易时，建议在 `config.yaml` 中关闭 `FallbackPolicy`（例如，不允许 maker 失败后自动转 taker），以避免非预期的行为。先观察最简单的执行路径。
- **熟悉紧急停止流程**: 在开始前，请务必熟悉 [紧急停止所有交易](#q8-如何紧急停止所有交易) 的方法。

---

## 快速开始
*本节内容保持不变。*

---

## 配置说明
*本节内容保持不变。*

---

## 安全指南
*本节内容保持不变。*

---

## API 文档
*本节内容保持不变。*

---

## 测试流程
*本节内容保持不变。*

---

## 常见问题
*本节内容保持不变，新增 Q8 引用。*

---
## 术语表
- **BBO (Best Bid Offer)**: 最佳买卖价，即最高的买一价和最低的卖一价。
- **Spread**: 价差，通常指 `ask - bid`。
- **Exposure (风险敞口)**: 在特定资产上持有的、未被对冲的净头寸（多头或空头）。
- **Maker/Taker**:
    - **Maker**: 提供流动性的订单（如限价单挂在订单簿上）。通常手续费较低。
    - **Taker**: 消耗流动性的订单（如市价单或立即成交的限价单）。通常手续费较高。
- **SLO (Service-Level Objective)**: 服务级别目标，用于衡量系统性能和可靠性的具体指标。

---

## 更新日志

### 2025-01-16: V2 文档增强
- ✅ **新增迷你架构图**: 在文档顶部增加 5 模块核心图，便于快速理解。
- ✅ **新增扩展指南**: 为核心 V2 模块补充 "如何扩展？" 的代码示例。
- ✅ **新增事件规范**: 在 `EventBus` 模块下详细定义了事件类型和Payload格式。
- ✅ **新增运行路径示例**: 详细描述了从机会发现到交易完成的完整事件流。
- ✅ **新增 SLO**: 定义了行情、扫描、执行等环节的服务级别目标。
- ✅ **新增生产指南**: 补充了在真实交易中必须遵守的安全规则。
- ✅ **新增交易所开发指南**: 提供了扩展新交易所的步骤。
- ✅ **新增术语表**: 解释了 BBO, Spread, Exposure 等核心术语。
- ✅ **优化章节顺序**: 调整了文档结构，使其更符合工程阅读习惯。

### 2025-01-15: V2 架构全面升级
- ✅ **引入 EventBus**: 系统核心重构为事件驱动模式。
- ✅ **升级核心组件**: `QuoteEngineV2`, `ScannerV3`, `ExecutionEngineV2` 等。
- ✅ **增强监控系统**: `HealthMonitor`, `ConsoleState`, `CLI Dashboard`。

*... (更早的更新日志) ...*

---

## 贡献指南
*本节内容保持不变。*

---

## 许可证
MIT License

---

## 联系方式
- **GitHub**: https://github.com/fordxx/perp-tools

---

## 免责声明
本项目仅供学习和研究使用。加密货币交易存在高风险，请谨慎投资。作者不对任何交易损失负责。

---

**最后更新**: 2025-01-16 (V2.1 文档增强)  
**文档版本**: v2.1
