# PerpBot - 多交易所模块化自动套利机器人

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Development-yellow.svg)](https://github.com/fordxx/perp-tools)

> 🚀 **当前分支**: `claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF`  
> 🎯 **开发重点**: Paradex 和 Extended 两个 DEX 的真实交易实现  
> 💰 **测试规模**: 本金 1000 USDT，单笔约 10 USDT

---

## 📑 目录

- [项目概述](#项目概述)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [资金管理系统](#资金管理系统-3层设计)
- [交易所集成状态](#交易所集成状态)
- [目录结构](#目录结构)
- [模块详解](#模块详解)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [安全指南](#安全指南)
- [API 文档](#api-文档)
- [测试流程](#测试流程)
- [常见问题](#常见问题)
- [更新日志](#更新日志)

---

## 项目概述

PerpBot 是一个**高度模块化**的自动交易框架，专注于多交易所套利和自动化交易策略。本项目采用三层资金管理架构，支持 CEX 和 DEX 的统一接入，提供完整的风控体系和实时监控系统。

### 设计理念

- **模块化**: 每个交易所、策略、风控模块完全解耦
- **安全第一**: 多层风控 + 密钥加密 + 权限最小化
- **实时监控**: Web 控制台 + 多渠道告警
- **灵活配置**: YAML 驱动，无需修改代码

### 技术栈

- **语言**: Python 3.10+
- **异步框架**: asyncio
- **Web 框架**: FastAPI + WebSocket
- **数据存储**: CSV / SQLite
- **监控**: Telegram / Lark / Webhook / Audio

---

## 核心特性

### ✅ 已实现功能

| 功能模块 | 说明 | 状态 |
|---------|------|------|
| 🏦 模块化交易所层 | 统一接口支持多家交易所 | ✅ 完成 |
| 💰 三层资金管理 | 刷量/套利/储备三层资金调度 | ✅ 完成 |
| 📊 自动止盈策略 | 基于收益阈值自动平仓 | ✅ 完成 |
| 🔄 套利扫描引擎 | 跨所价差发现与评分 | ✅ 完成 |
| ⚡ 并发行情获取 | WebSocket + REST 双通道 | ✅ 完成 |
| 🛡️ 多层风控系统 | 账户级 + 仓位级风控 | ✅ 完成 |
| 🔔 智能提醒系统 | 多条件触发 + 自动下单 | ✅ 完成 |
| 🖥️ Web 控制台 | 实时监控 + 在线调参 | ✅ 完成 |
| 🔐 安全审计 | API 调用日志 + 密钥加密 | ✅ 完成 |

### 🚧 开发中功能

| 功能模块 | 说明 | 进度 |
|---------|------|------|
| 🔵 Paradex DEX | 真实下单与持仓管理 | 🚧 80% |
| 🔵 Extended DEX | 真实下单与持仓管理 | 🚧 80% |
| 📈 高级套利策略 | 多腿套利 + 对冲优化 | 🚧 50% |

### ⏸️ 待启用功能

- EdgeX、Backpack、Aster、GRVT 等 DEX（代码已保留）
- 更多 CEX 集成（代码框架已完成）

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      PerpBot 系统架构                         │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Web Console  │  │     CLI      │  │   Alert      │      │
│  │   (FastAPI)  │  │   (Python)   │  │  (Multi-CH)  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                  │                  │              │
│         └──────────────────┼──────────────────┘              │
│                            ↓                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Trading Service (主控循环)                   │    │
│  │  ┌─────────────────────────────────────────────┐   │    │
│  │  │  Capital Orchestrator (资金总控)             │   │    │
│  │  │  ┌────────┬────────┬────────┐               │   │    │
│  │  │  │  刷量层 │ 套利层 │ 储备层 │               │   │    │
│  │  │  │  (70%) │ (20%) │ (10%) │               │   │    │
│  │  │  └────────┴────────┴────────┘               │   │    │
│  │  └─────────────────────────────────────────────┘   │    │
│  └──────────────────┬──────────────────────────────────┘    │
│                     ↓                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │          Strategy Layer (策略层)                     │    │
│  │  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │ Take Profit  │  │  Arbitrage   │               │    │
│  │  │   Strategy   │  │   Scanner    │               │    │
│  │  └──────────────┘  └──────────────┘               │    │
│  └──────────────────┬──────────────────────────────────┘    │
│                     ↓                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │         Risk Management Layer (风控层)               │    │
│  │  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │ Risk Manager │  │Position Guard│               │    │
│  │  │ (账户级风控)  │  │ (仓位级风控)  │               │    │
│  │  └──────────────┘  └──────────────┘               │    │
│  └──────────────────┬──────────────────────────────────┘    │
│                     ↓                                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           Exchange Layer (交易所层)                  │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │    │
│  │  │Paradex │ │Extended│ │  OKX   │ │Binance │      │    │
│  │  │ (DEX)  │ │ (DEX)  │ │ (行情) │ │ (行情) │      │    │
│  │  └────────┘ └────────┘ └────────┘ └────────┘      │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐      │    │
│  │  │ EdgeX  │ │Backpack│ │ Aster  │ │  GRVT  │      │    │
│  │  │(待启用)│ │(待启用)│ │(待启用)│ │(待启用)│      │    │
│  │  └────────┘ └────────┘ └────────┘ └────────┘      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
1. 行情获取
   WebSocket (实时) → Price Cache → Strategy
        ↓
   REST (回退)

2. 套利信号
   Scanner → 价差计算 → 成本校正 → 评分排序 → Executor

3. 下单流程
   Strategy → Risk Check → Capital Reserve → Exchange API
                 ↓              ↓
              拒绝/通过      占用资金池
                                ↓
                          Order Placement
                                ↓
                    Success → Release → Record
                    Failure → Rollback → Alert

4. 监控流程
   Trading Loop → State Update → WebSocket Push → Web Console
        ↓
   Alert Check → Trigger → Notify (Telegram/Lark/etc.)
```

---

## 资金管理系统（3层设计）

### 设计理念

传统的5层资金管理过于复杂，本项目采用**极简三层模型**，专注于刷量对冲和套利场景：

```
总资金 = 刷量层 + 套利层 + 储备层
```

### 三层架构详解

#### 🔵 Layer 1: 刷量层 (Wash Trading Pool)
- **默认占比**: 70%
- **用途**: 
  - 永续合约对冲刷量（HFT 双边开平仓）
  - 高频小额交易
  - 做市商策略
- **风险等级**: 低
- **特点**: 
  - 高频次（每日可能数百笔）
  - 小额（单笔 10-50 USDT）
  - 对冲保护（同时开多/空）
  - 目标：产生交易量，控制成本
- **典型策略**: 
  - `wash_trade`: 刷量对冲
  - `hft`: 高频交易

#### 🟢 Layer 2: 套利层 (Arbitrage Pool)
- **默认占比**: 20%
- **用途**:
  - 跨所套利（价差捕捉）
  - 中频策略（如统计套利）
  - 闪电套利
- **风险等级**: 中
- **特点**:
  - 中频次（每日 10-50 笔）
  - 中等仓位（单笔 50-200 USDT）
  - 快速进出（持仓时间 < 1 小时）
  - 目标：捕捉价差，锁定利润
- **典型策略**:
  - `arbitrage`: 跨所套利
  - `flash`: 闪电套利
  - `stat`: 统计套利
  - `mid_freq`: 中频交易

#### 🟡 Layer 3: 储备层 (Reserve Pool)
- **默认占比**: 10%
- **用途**:
  - 应急补仓
  - 资金费率套利
  - 风险对冲
  - L1/L2 层紧急借用
- **风险等级**: 动态
- **特点**:
  - 低频次（每日 < 5 笔）
  - 按需动用
  - 长期持有（可能 > 24 小时）
  - 目标：保护账户，应对极端行情
- **典型策略**:
  - `funding`: 资金费率套利
  - 紧急补仓
  - 黑天鹅对冲

### 资金调度规则

#### 1. 正常模式
```python
# 策略向资金总控申请资金
orchestrator = CapitalOrchestrator(
    wu_size=10_000.0,        # 单所基准资金（1 WU = 10,000 USDT）
    wash_budget_pct=0.7,     # 刷量层 70%
    arb_budget_pct=0.2,      # 套利层 20%
    reserve_pct=0.1          # 储备层 10%
)

# 申请刷量资金
reservation = orchestrator.reserve_for_wash(
    exchange="paradex",
    amount=20.0  # 20 USDT
)

# 申请套利资金
reservation = orchestrator.reserve_for_arb(
    exchange="extended",
    amount=100.0  # 100 USDT
)
```

#### 2. 安全模式（回撤触发）
当单个交易所回撤达到 **5%** 时，自动触发安全模式：

```python
# 触发条件
if drawdown_pct >= 5%:
    safe_mode = True
    allowed_layers = ["wash", "reserve"]  # 仅允许刷量和储备
```

**安全模式限制**:
- ❌ 禁止套利层下单（停止所有套利策略）
- ✅ 允许刷量层继续运行（降低风险，保持活跃）
- ✅ 允许储备层应急操作（对冲/平仓）
- 🔄 自动降仓（逐步减少敞口）

#### 3. 跨层借用
当某层资金不足时，可以临时从储备层借用：

```python
# L2 套利层资金不足时
if arb_pool.available < required_amount:
    if allow_borrow_from_reserve:
        borrow_from_reserve(shortage)
```

### 资金流转示例

#### 场景1: 正常套利
```
1. Scanner 发现 Paradex 和 Extended 价差 0.3%
2. Executor 向 CapitalOrchestrator 申请:
   - Paradex: 套利层 100 USDT
   - Extended: 套利层 100 USDT
3. 资金总控检查:
   ✅ 套利层可用: 2000 USDT (20% * 10000)
   ✅ 每所申请 100 USDT < 可用额度
   ✅ 批准并占用
4. 下单成功，持仓等待价差收敛
5. 平仓后释放资金，记录 PnL
```

#### 场景2: 安全模式
```
1. Paradex 当日回撤达到 -5.2%
2. CapitalOrchestrator 自动触发安全模式
3. 新的套利信号被拒绝:
   ❌ "Paradex 处于安全模式，套利层已禁用"
4. 刷量引擎继续运行（风险可控）
5. 储备层可用于平仓/对冲
6. 等待回撤恢复至 < 5% 后自动解除
```

### 实时监控

#### 资金池快照
```python
snapshot = orchestrator.current_snapshot()

# 返回示例
{
    "paradex": {
        "meta": {
            "equity": 10000.0,
            "drawdown_pct": 0.03,  # 3%
            "safe_mode": 0,
            "total_volume": 150000.0,
            "total_fee": 37.5,
            "realized_pnl": 123.45
        },
        "wash": {
            "pool": 7000.0,
            "allocated": 150.0,
            "available": 6850.0
        },
        "arb": {
            "pool": 2000.0,
            "allocated": 500.0,
            "available": 1500.0
        },
        "reserve": {
            "pool": 1000.0,
            "allocated": 0.0,
            "available": 1000.0
        }
    }
}
```

#### Web 控制台可视化
- 实时显示各层资金水位
- 占用率柱状图
- 历史 PnL 曲线
- 安全模式告警

---

## 交易所集成状态

### 🟢 主力 DEX（开发中）

#### Paradex
- **类型**: Layer 2 DEX (Starknet)
- **官网**: https://paradex.trade
- **API 文档**: https://docs.paradex.trade/api/
- **状态**: 🚧 集成中
  - ✅ 行情获取 (REST + WebSocket)
  - 🚧 下单接口（80% 完成）
  - ⏸️ 提现接口（禁用）
- **认证方式**: JWT + STARK 签名
- **支持合约**: BTC-USD-PERP, ETH-USD-PERP 等永续合约
- **最小下单**: 10 USDT
- **费率**: Maker 0% / Taker 0.025%
- **限速**: 100 req/min (账户级)
- **特点**:
  - 零 Maker 费
  - 自托管（非托管）
  - 链上结算

#### Extended Exchange
- **类型**: Layer 2 DEX (Starknet)
- **官网**: https://extended.exchange
- **API 文档**: https://api.docs.extended.exchange/
- **状态**: 🚧 集成中
  - ✅ 行情获取 (REST + WebSocket)
  - 🚧 下单接口（80% 完成）
  - ⏸️ 提现接口（禁用）
- **认证方式**: API Key + STARK 签名
- **支持合约**: 加密货币 + TradFi 资产永续合约
- **最小下单**: 10 USDT
- **费率**: Maker 0% / Taker 0.025%
- **限速**: 自适应
- **特点**:
  - 统一保证金
  - TradFi 资产（股票、商品）
  - 最高 100x 杠杆

### 🟡 参考价格源（仅行情）

#### OKX
- **用途**: 提供参考价格，过滤异常波动
- **状态**: ✅ 已集成（仅行情）
- **不参与**: 套利下单（纯CEX，不在本项目DEX套利范围）
- **接口**: `exchanges/okx_client.py`

#### Binance
- **用途**: 提供参考价格，过滤异常波动
- **状态**: ✅ 已集成（仅行情）
- **不参与**: 套利下单
- **接口**: `exchanges/binance_client.py`

### ⏸️ 待启用 DEX

| 交易所 | 类型 | 状态 | 计划 |
|--------|------|------|------|
| EdgeX | DEX | ⏸️ 代码保留 | Paradex/Extended 测试完成后启用 |
| Backpack | DEX | ⏸️ 代码保留 | 同上 |
| Aster | DEX | ⏸️ 代码保留 | 同上 |
| GRVT | DEX | ⏸️ 代码保留 | 同上 |

---

## 目录结构

```
perp-tools/
├── src/perpbot/                      # 核心代码目录
│   ├── __init__.py
│   ├── models.py                     # 📦 数据模型（Order, Position, Quote等）
│   ├── cli.py                        # 🖥️ CLI 入口（cycle/serve命令）
│   │
│   ├── exchanges/                    # 🏦 交易所层
│   │   ├── base.py                   # 统一交易所接口（ExchangeBase抽象类）
│   │   ├── paradex_client.py         # Paradex DEX 客户端
│   │   ├── extended_client.py        # Extended DEX 客户端
│   │   ├── okx_client.py             # OKX 行情客户端
│   │   ├── binance_client.py         # Binance 行情客户端
│   │   ├── edgex_client.py           # EdgeX（待启用）
│   │   ├── backpack_client.py        # Backpack（待启用）
│   │   ├── aster_client.py           # Aster（待启用）
│   │   └── grvt_client.py            # GRVT（待启用）
│   │
│   ├── strategy/                     # 📈 策略层
│   │   └── take_profit.py            # 自动止盈策略
│   │
│   ├── arbitrage/                    # 🔄 套利模块
│   │   ├── scanner.py                # 套利扫描器（价差发现+评分）
│   │   └── arbitrage_executor.py     # 套利执行器（双边下单+对冲）
│   │
│   ├── capital_orchestrator.py       # 💰 资金总控（3层资金管理）
│   ├── risk_manager.py               # 🛡️ 风险管理器（账户级风控）
│   ├── position_guard.py             # 🔒 仓位守卫（单笔风险限制）
│   ├── hedge_volume_engine.py        # ⚡ 刷量引擎（对冲刷量）
│   │
│   └── monitoring/                   # 📊 监控模块
│       ├── alerts.py                 # 提醒系统（多条件+多渠道）
│       ├── web_console.py            # Web 控制台（FastAPI）
│       └── static/
│           └── index.html            # Web 前端界面
│
├── docs/                             # 📚 文档目录
│   ├── ARCHITECTURE.md               # 架构设计文档
│   ├── API_REFERENCE.md              # API 参考手册
│   ├── EXCHANGE_INTEGRATION.md       # 交易所集成指南
│   ├── SECURITY.md                   # 安全指南
│   ├── TRADING_GUIDE.md              # 交易指南
│   └── FAQ.md                        # 常见问题
│
├── config.example.yaml               # ⚙️ 配置模板
├── requirements.txt                  # 📦 Python 依赖
├── .env.example                      # 🔐 环境变量模板
├── README.md                         # 📖 本文档
├── BRANCH_ANALYSIS.md                # 分支分析文档
├── DELIVERY_SUMMARY.md               # 交付总结
└── perpbot-important-architecture.md # 重要架构说明
```

---

## 模块详解

### 1. 数据模型 (`models.py`)

#### 核心类

**Order（订单）**
```python
@dataclass
class Order:
    order_id: str           # 订单ID
    symbol: str             # 交易对（如 "BTC-USD-PERP"）
    side: str               # 方向："BUY" / "SELL"
    size: float             # 数量
    price: float            # 价格
    order_type: str         # 类型："LIMIT" / "MARKET"
    status: str             # 状态："PENDING" / "FILLED" / "CANCELLED"
    filled_size: float      # 已成交数量
    timestamp: float        # 时间戳
```

**Position（持仓）**
```python
@dataclass
class Position:
    symbol: str             # 交易对
    side: str               # 方向："LONG" / "SHORT"
    size: float             # 持仓数量
    entry_price: float      # 开仓均价
    current_price: float    # 当前价格
    unrealized_pnl: float   # 未实现盈亏
    leverage: float         # 杠杆倍数
```

**Quote（报价）**
```python
@dataclass
class Quote:
    exchange: str           # 交易所名称
    symbol: str             # 交易对
    bid: float              # 买一价
    ask: float              # 卖一价
    bid_size: float         # 买一量
    ask_size: float         # 卖一量
    timestamp: float        # 时间戳
```

### 2. 资金总控 (`capital_orchestrator.py`)

#### CapitalOrchestrator 类

**主要方法**:

```python
# 初始化
__init__(wu_size=10000, wash_budget_pct=0.7, arb_budget_pct=0.2, reserve_pct=0.1)

# 更新账户权益
update_equity(exchange: str, equity: float)

# 更新回撤状态
update_drawdown(exchange: str, drawdown_pct: float)

# 为策略预留资金
reserve_for_strategy(exchanges: List[str], amount: float, strategy: str) -> CapitalReservation

# 为特定资金池预留
reserve_for_wash(exchange: str, amount: float) -> bool
reserve_for_arb(exchange: str, amount: float) -> bool
reserve_for_pool(exchange: str, pool: str, amount: float) -> bool

# 释放资金占用
release(reservation: CapitalReservation)

# 记录刷量结果
record_volume_result(exchange: str, volume: float, fee: float, pnl: float)

# 获取当前快照
current_snapshot() -> Dict[str, Dict[str, Dict[str, float]]]
```

**使用示例**:
```python
# 初始化
orchestrator = CapitalOrchestrator(
    wu_size=10_000.0,
    wash_budget_pct=0.7,
    arb_budget_pct=0.2,
    reserve_pct=0.1
)

# 申请套利资金
reservation = orchestrator.reserve_for_strategy(
    exchanges=["paradex", "extended"],
    amount=100.0,
    strategy="arbitrage"
)

if reservation.approved:
    # 执行下单
    try:
        order_results = await execute_arbitrage(...)
    finally:
        # 释放资金
        orchestrator.release(reservation)
else:
    logger.warning(f"资金申请被拒: {reservation.reason}")
```

### 3. 交易所基类 (`exchanges/base.py`)

#### ExchangeBase 抽象类

**必须实现的方法**:
```python
# 连接
async def connect() -> bool

# 断开
async def disconnect()

# 下单
async def place_order(symbol: str, side: str, size: float, 
                      price: float = None, order_type: str = "LIMIT") -> Order

# 取消订单
async def cancel_order(order_id: str) -> bool

# 查询订单
async def get_order(order_id: str) -> Order

# 获取持仓
async def get_position(symbol: str) -> Position

# 获取余额
async def get_balance() -> Dict[str, float]

# 获取最新报价
async def get_quote(symbol: str) -> Quote

# 订阅行情
async def subscribe_orderbook(symbol: str)
```

### 4. Paradex 客户端 (`exchanges/paradex_client.py`)

**特殊实现**:
- STARK 密钥签名
- JWT Token 管理
- WebSocket 深度订阅
- Gas fee 预估

**配置要求**:
```bash
# .env
PARADEX_API_KEY=your_api_key
PARADEX_PRIVATE_KEY=your_stark_private_key
PARADEX_ACCOUNT=0x...
```

### 5. Extended 客户端 (`exchanges/extended_client.py`)

**特殊实现**:
- STARK 签名（Starknet 链上结算）
- Fee 参数必填
- Market order 也需要 price 参数
- 异步订单确认机制

**配置要求**:
```bash
# .env
EXTENDED_API_KEY=your_api_key
EXTENDED_STARK_KEY=your_stark_key
EXTENDED_VAULT_NUMBER=your_vault_number
```

### 6. 套利扫描器 (`arbitrage/scanner.py`)

**核心逻辑**:
```python
1. 获取所有交易所的报价
2. 计算跨所价差
3. 扣除交易成本（手续费 + 滑点 + Gas）
4. 评分排序（收益 + 流动性 + 可靠性）
5. 过滤低于阈值的机会
6. 返回优先级列表
```

**评分算法**:
```python
score = (
    profit_weight * profit_pct +
    liquidity_weight * liquidity_score +
    reliability_weight * exchange_reliability
)
```

### 7. 套利执行器 (`arbitrage/arbitrage_executor.py`)

**执行流程**:
```python
1. 资金预留（CapitalOrchestrator）
2. 风险检查（RiskManager）
3. 双边下单（并发）
4. 订单确认
5. 持仓监控
6. 自动平仓/对冲
7. 资金释放
8. 记录结果
```

**异常处理**:
- 单边成交：立即对冲或取消
- 价格滑点超阈值：拒绝下单
- 网络超时：重试 + 告警
- 余额不足：降级/跳过

### 8. 风险管理器 (`risk_manager.py`)

**风控规则**:

| 规则 | 默认值 | 说明 |
|------|--------|------|
| 单笔风险上限 | 5% | 单笔下单不超过账户权益的 5% |
| 最大回撤 | 10% | 触发暂停交易 |
| 每日亏损限制 | 5% | 绝对金额或百分比 |
| 连续失败次数 | 3 | 3 次连续失败后暂停 |
| 品种敞口上限 | 30% | 单个品种总敞口不超过 30% |
| 方向一致性 | 启用 | 禁止同品种同时做多做空（套利除外） |
| 快市冻结 | 0.5% / 1s | 价格 1 秒内变动超 0.5% 冻结下单 |

**人工覆盖**:
```python
# 风控暂停后，可通过配置恢复
manual_override_minutes: 30  # 人工确认后继续 30 分钟
manual_override_trades: 10   # 或允许 10 笔交易后重新评估
```

### 9. 仓位守卫 (`position_guard.py`)

**功能**:
- 单笔仓位大小限制
- 同品种仓位总量限制
- 仓位冷却时间（失败后）
- 仓位集中度检查

### 10. 刷量引擎 (`hedge_volume_engine.py`)

**工作原理**:
```python
1. 从 L1 刷量层申请 300-800 USDT 名义额度
2. 选择两个交易所（如 Paradex + Extended）
3. 并发开仓：
   - Paradex: 开多 0.001 BTC
   - Extended: 开空 0.001 BTC
4. 检查成交：
   - 都成交 → 持仓 10-60 秒 → 平仓
   - 单边成交 → 立即回滚
5. 记录结果：volume, fee, pnl
6. 释放资金
```

**风控**:
- 预估滑点 > 0.1% → 放弃
- 单所累计亏损 > 2% WU → 暂停该所
- Gas fee > 阈值 → 等待

### 11. 提醒系统 (`monitoring/alerts.py`)

**支持的条件类型**:
- **价格突破**: 价格突破指定阈值
- **区间提醒**: 价格进入/离开指定区间
- **百分比变化**: N 分钟内涨跌超过 X%
- **跨品种价差**: 如 BTC-ETH 比价异常
- **波动率**: 历史波动率超阈值

**支持的渠道**:
- Console（控制台）
- Telegram
- Lark（飞书）
- Webhook
- Audio（本地音频）

**自动动作**:
```yaml
alerts:
  - name: "BTC 突破 10 万"
    type: "price_breakout"
    symbol: "BTC-USD-PERP"
    threshold: 100000
    channels: ["telegram", "audio"]
    action: "start-trading"  # 自动启动套利

  - name: "ETH 价差过大"
    type: "price_spread"
    symbols: ["ETH-USD-PERP@paradex", "ETH-USD-PERP@extended"]
    threshold_pct: 0.5
    action: "auto-order"  # 自动下单
    order_size: 50.0
```

### 12. Web 控制台 (`monitoring/web_console.py`)

**功能模块**:

| 模块 | 端点 | 说明 |
|------|------|------|
| 概览 | `/api/overview` | 系统状态、资金快照 |
| 行情 | `/api/quotes` | BTC/ETH 跨所报价 |
| 套利 | `/api/arbitrage` | 当前套利机会（评分排序） |
| 持仓 | `/api/positions` | 所有持仓列表 |
| 资产 | `/api/equity_curve` | 权益曲线 |
| 提醒 | `/api/alert_history` | 提醒历史记录 |
| 控制 | `/api/control/start` | 启动套利 |
| 控制 | `/api/control/pause` | 暂停套利 |
| 控制 | `/api/control/threshold` | 调整利润阈值 |

**实时推送**:
- WebSocket: `/ws`
- 每秒推送最新状态
- 免刷新更新

---

## 快速开始

### 1. 环境要求

- Python 3.10+
- pip / poetry
- 稳定的网络连接

### 2. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/fordxx/perp-tools.git
cd perp-tools
git checkout claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置密钥

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入密钥
nano .env
```

**.env 内容**:
```bash
# Paradex
PARADEX_API_KEY=your_paradex_api_key
PARADEX_PRIVATE_KEY=your_stark_private_key
PARADEX_ACCOUNT=0x...

# Extended
EXTENDED_API_KEY=your_extended_api_key
EXTENDED_STARK_KEY=your_extended_stark_key
EXTENDED_VAULT_NUMBER=12345

# OKX (可选，仅行情)
OKX_API_KEY=your_okx_key
OKX_API_SECRET=your_okx_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet  # or "live"

# Binance (可选，仅行情)
BINANCE_API_KEY=your_binance_key
BINANCE_API_SECRET=your_binance_secret
BINANCE_ENV=testnet  # or "live"

# 主密钥（用于加密其他密钥）
MASTER_KEY=your_master_encryption_key
```

### 4. 配置参数

```bash
# 复制配置模板
cp config.example.yaml config.yaml

# 根据需求调整参数
nano config.yaml
```

**关键配置项**:
```yaml
# 资金管理
capital:
  wu_size: 10000.0            # 单所基准资金（USDT）
  wash_budget_pct: 0.7        # 刷量层 70%
  arb_budget_pct: 0.2         # 套利层 20%
  reserve_pct: 0.1            # 储备层 10%
  drawdown_limit_pct: 0.05    # 回撤 5% 触发安全模式

# 套利参数
arbitrage:
  min_profit_pct: 0.002       # 最小利润 0.2%
  max_position_size: 100.0    # 单边最大仓位 100 USDT
  execution_timeout: 30       # 执行超时 30 秒

# 风控
risk:
  max_drawdown_pct: 0.10      # 最大回撤 10%
  daily_loss_limit_pct: 0.05  # 每日亏损限制 5%
  max_consecutive_failures: 3 # 连续失败 3 次暂停
```

### 5. 运行

#### 方式 1: 单次循环（测试）
```bash
PYTHONPATH=src python -m perpbot.cli cycle --config config.yaml
```

**输出示例**:
```
[INFO] 初始化交易所: paradex, extended
[INFO] Paradex 连接成功
[INFO] Extended 连接成功
[INFO] 获取行情...
[INFO] BTC-USD-PERP 价差: Paradex $95123.45 vs Extended $95234.56 (0.12%)
[WARN] 价差低于阈值 0.2%，跳过
[INFO] 执行止盈检查...
[INFO] 循环完成
```

#### 方式 2: 启动 Web 控制台
```bash
PYTHONPATH=src python -m perpbot.cli serve --config config.yaml --port 8000
```

**访问**: http://localhost:8000

**功能**:
- 实时行情大屏
- 套利机会列表
- 一键启停交易
- 在线调整参数
- 资产曲线可视化

### 6. 小额测试流程

#### 阶段 1: 测试网验证
```bash
# 1. 在 .env 中设置测试网
PARADEX_ENV=testnet
EXTENDED_ENV=testnet

# 2. 申请测试网代币
# Paradex: https://testnet.paradex.trade/faucet
# Extended: https://testnet.extended.exchange/faucet

# 3. 运行测试
PYTHONPATH=src python -m perpbot.cli cycle --config config.yaml

# 4. 验证功能
- 行情获取 OK
- 下单成功 OK
- 余额更新 OK
- 平仓正常 OK
```

#### 阶段 2: 主网小额测试
```bash
# 1. 切换到主网
PARADEX_ENV=live
EXTENDED_ENV=live

# 2. 充值小额资金
- Paradex: 充值 100 USDC
- Extended: 充值 100 USDC

# 3. 调整配置
arbitrage:
  min_profit_pct: 0.003     # 提高阈值到 0.3%（降低频率）
  max_position_size: 10.0   # 限制单边仓位 10 USDT

# 4. 启动监控
PYTHONPATH=src python -m perpbot.cli serve

# 5. 手动触发 1-2 笔测试
在 Web 控制台中点击"执行套利"

# 6. 观察 24 小时
- 检查成交记录
- 监控资金变化
- 查看日志异常
```

#### 阶段 3: 逐步放大
```bash
# 确认无误后逐步增加资金
Day 1-3:   每所 100 USDC,  单笔 10 USDC
Day 4-7:   每所 500 USDC,  单笔 50 USDC
Day 8-14:  每所 1000 USDC, 单笔 100 USDC
Day 15+:   根据盈利情况决定
```

---

## 配置说明

### config.yaml 完整配置

```yaml
# ========================================
# 资金管理配置
# ========================================
capital:
  wu_size: 10000.0                 # 单所基准资金（1 WU = 10,000 USDT）
  wash_budget_pct: 0.7             # 刷量层 70%
  arb_budget_pct: 0.2              # 套利层 20%
  reserve_pct: 0.1                 # 储备层 10%
  drawdown_limit_pct: 0.05         # 回撤 5% 触发安全模式
  allow_borrow_from_reserve: true  # 允许从储备层借用

# ========================================
# 交易所配置
# ========================================
exchanges:
  paradex:
    enabled: true                   # 启用
    type: "dex"
    min_order_size: 10.0            # 最小下单 10 USDT
    max_leverage: 5                 # 最大杠杆 5x
    fee_rate: 0.00025               # 手续费 0.025%
  
  extended:
    enabled: true
    type: "dex"
    min_order_size: 10.0
    max_leverage: 10
    fee_rate: 0.00025
  
  okx:
    enabled: true
    type: "cex"
    usage: "price_reference"        # 仅用于价格参考
  
  binance:
    enabled: true
    type: "cex"
    usage: "price_reference"

# ========================================
# 套利配置
# ========================================
arbitrage:
  enabled: true
  min_profit_pct: 0.002             # 最小利润 0.2%
  high_vol_min_profit_pct: 0.005    # 高波动时提高到 0.5%
  low_vol_min_profit_pct: 0.001     # 低波动时降低到 0.1%
  max_position_size: 100.0          # 单边最大仓位 100 USDT
  max_slippage_pct: 0.001           # 最大滑点 0.1%
  execution_timeout: 30             # 执行超时 30 秒
  partial_fill_threshold: 0.9       # 部分成交 90% 视为成功
  hedge_on_partial: true            # 部分成交时对冲
  
  # 动态评分权重
  scoring:
    profit_weight: 0.5              # 利润权重 50%
    liquidity_weight: 0.3           # 流动性权重 30%
    reliability_weight: 0.2         # 可靠性权重 20%

# ========================================
# 风控配置
# ========================================
risk:
  max_drawdown_pct: 0.10            # 最大回撤 10%
  daily_loss_limit_pct: 0.05        # 每日亏损限制 5%
  daily_loss_limit: 500.0           # 或绝对金额 500 USDT
  max_consecutive_failures: 3       # 连续失败 3 次暂停
  max_symbol_exposure_pct: 0.30     # 单品种敞口 30%
  enforce_direction_consistency: true  # 同品种禁止双向持仓
  
  # 快市冻结
  fast_market_freeze:
    enabled: true
    threshold_pct: 0.005            # 0.5% 波动
    window_seconds: 1               # 1 秒内
    freeze_duration: 60             # 冻结 60 秒
  
  # 人工覆盖
  manual_override_minutes: 30       # 人工确认后恢复 30 分钟
  manual_override_trades: 10        # 或允许 10 笔交易

# ========================================
# 止盈策略
# ========================================
take_profit:
  enabled: true
  target_profit_pct: 0.01           # 目标利润 1%
  stop_loss_pct: 0.02               # 止损 -2%
  check_interval: 10                # 检查间隔 10 秒
  partial_close: true               # 允许部分平仓
  trailing_stop_pct: 0.005          # 移动止损 0.5%

# ========================================
# 刷量引擎
# ========================================
hedge_volume:
  enabled: true
  min_notional: 300.0               # 最小名义 300 USDT
  max_notional: 800.0               # 最大名义 800 USDT
  hold_duration_min: 10             # 最小持仓 10 秒
  hold_duration_max: 60             # 最大持仓 60 秒
  max_cumulative_loss_pct: 0.02     # 累计亏损 2% 暂停

# ========================================
# 监控与提醒
# ========================================
monitoring:
  loop_interval_seconds: 5          # 主循环间隔 5 秒
  alert_record_path: "alerts.csv"   # 提醒记录路径
  
alerts:
  - name: "BTC 突破 10 万"
    type: "price_breakout"
    symbol: "BTC-USD-PERP"
    exchange: "paradex"
    threshold: 100000
    direction: "above"
    channels: ["telegram", "audio"]
    action: "notify"
  
  - name: "ETH 价差异常"
    type: "price_spread"
    symbols: 
      - "ETH-USD-PERP@paradex"
      - "ETH-USD-PERP@extended"
    threshold_pct: 0.5
    channels: ["telegram", "lark"]
    action: "start-trading"

# ========================================
# 通知渠道
# ========================================
notifications:
  telegram:
    enabled: true
    bot_token: "your_bot_token"
    chat_id: "your_chat_id"
  
  lark:
    enabled: false
    webhook_url: "https://open.feishu.cn/..."
  
  webhook:
    enabled: false
    url: "https://your-webhook.com/endpoint"
    headers:
      Authorization: "Bearer your_token"
  
  audio:
    enabled: true
    sound_file: "alert.wav"
```

---

## 安全指南

### 1. API 密钥安全

#### ⚠️ 风险点
- 明文存储私钥 → 被盗用
- 权限过大 → 资金被提走
- IP 未限制 → 任何人可调用
- 无审计日志 → 异常难追踪

#### ✅ 最佳实践

##### (1) 加密存储
```python
from perpbot.security import SecureCredentialManager

# 首次运行（生成主密钥）
cred_manager = SecureCredentialManager()
# 输出: ⚠️ Generated MASTER_KEY: xxx...
# 请将 MASTER_KEY 保存到环境变量或 AWS Secrets Manager

# 加密存储凭据
cred_manager.encrypt_credential('PARADEX_PRIVATE_KEY', 'your_private_key')
cred_manager.encrypt_credential('EXTENDED_STARK_KEY', 'your_stark_key')

# 运行时解密
private_key = cred_manager.get_credential('PARADEX_PRIVATE_KEY')
```

##### (2) 权限最小化
在交易所后台创建 API 密钥时：
- ✅ **Read** (查询余额、持仓、订单)
- ✅ **Trade** (下单、撤单)
- ❌ **Withdraw** (提现) - **必须禁用**
- ❌ **Transfer** (划转) - **必须禁用**

##### (3) IP 白名单
在交易所后台设置 API 密钥的 IP 白名单：
```
允许的 IP:
- 你的服务器 IP: 123.45.67.89
- 备用服务器 IP: 123.45.67.90

拒绝所有其他 IP
```

##### (4) Subkey（子密钥）
Paradex 和 Extended 支持 Subkey：
- 主密钥：存储在冷钱包，仅用于创建 Subkey
- Subkey：用于日常交易，可随时撤销
- 好处：即使 Subkey 泄露，主密钥仍然安全

##### (5) 审计日志
```python
from perpbot.security import SecurityAuditLogger

logger = SecurityAuditLogger("security_audit.log")

# 记录所有 API 调用
logger.log_api_call(
    exchange="paradex",
    endpoint="/orders",
    params={"symbol": "BTC-USD-PERP", "side": "BUY"}
)

# 记录订单
logger.log_order(
    exchange="paradex",
    order_id="order_123",
    details={"size": 0.001, "price": 95000}
)

# ⚠️ 记录异常提现尝试（应该被阻止）
logger.log_withdrawal_attempt(
    exchange="paradex",
    amount=1000.0,
    address="0x..."
)
```

### 2. 多重签名（可选）

对于大额资金，建议使用 Gnosis Safe 等多签钱包：

```python
from perpbot.security import MultiSigWallet

# 3/5 多签钱包
wallet = MultiSigWallet(
    safe_address="0x...",
    owners=["0xOwner1", "0xOwner2", "0xOwner3", "0xOwner4", "0xOwner5"],
    threshold=3  # 需要 3 个签名
)

# 提议交易（需要其他 2 个所有者批准）
await wallet.propose_transaction(
    to="0xParadexContract",
    data=order_data,
    value=0
)
```

### 3. 网络安全

#### VPN / VPS
- 使用固定 IP 的 VPS 运行机器人
- 启用防火墙，只开放必要端口
- 定期更新系统补丁

#### HTTPS
- Web 控制台使用 HTTPS
- 配置 SSL 证书（Let's Encrypt 免费）
```bash
# 使用 Caddy 自动配置 HTTPS
caddy reverse-proxy --from perpbot.yourdomain.com --to localhost:8000
```

### 4. 异常检测

#### 自动告警
```yaml
# config.yaml
alerts:
  - name: "异常大额下单"
    type: "order_size"
    threshold: 1000.0  # 单笔超过 1000 USDT 告警
    channels: ["telegram", "audio"]
  
  - name: "API 调用频率异常"
    type: "rate_limit"
    threshold: 200  # 每分钟超过 200 次调用
    channels: ["telegram"]
  
  - name: "账户余额异常下降"
    type: "balance_drop"
    threshold_pct: 0.10  # 余额下降 10%
    channels: ["telegram", "lark", "audio"]
```

---

## API 文档

### Web 控制台 API

#### 基础信息
- **Base URL**: `http://localhost:8000`
- **协议**: HTTP / WebSocket
- **认证**: 暂无（后续可添加 JWT）

#### REST 端点

##### 1. 获取系统概览
```http
GET /api/overview

Response:
{
  "status": "running",
  "uptime": 3600,
  "capital_snapshot": {
    "paradex": {
      "meta": {
        "equity": 10000.0,
        "drawdown_pct": 0.03,
        "safe_mode": 0
      },
      "wash": {"pool": 7000.0, "allocated": 150.0, "available": 6850.0},
      "arb": {"pool": 2000.0, "allocated": 500.0, "available": 1500.0},
      "reserve": {"pool": 1000.0, "allocated": 0.0, "available": 1000.0}
    }
  },
  "total_trades": 123,
  "total_pnl": 456.78
}
```

##### 2. 获取最新报价
```http
GET /api/quotes?symbols=BTC-USD-PERP,ETH-USD-PERP

Response:
[
  {
    "symbol": "BTC-USD-PERP",
    "quotes": [
      {
        "exchange": "paradex",
        "bid": 95123.45,
        "ask": 95134.56,
        "spread": 11.11,
        "timestamp": 1702800000.0
      },
      {
        "exchange": "extended",
        "bid": 95234.56,
        "ask": 95245.67,
        "spread": 11.11,
        "timestamp": 1702800000.0
      }
    ]
  }
]
```

##### 3. 获取套利机会
```http
GET /api/arbitrage?limit=10

Response:
[
  {
    "symbol": "BTC-USD-PERP",
    "buy_exchange": "paradex",
    "sell_exchange": "extended",
    "buy_price": 95123.45,
    "sell_price": 95234.56,
    "spread_pct": 0.12,
    "net_profit_pct": 0.06,  # 扣除成本后
    "confidence": 0.85,
    "score": 8.5,
    "timestamp": 1702800000.0
  }
]
```

##### 4. 获取持仓
```http
GET /api/positions

Response:
[
  {
    "exchange": "paradex",
    "symbol": "BTC-USD-PERP",
    "side": "LONG",
    "size": 0.001,
    "entry_price": 95000.0,
    "current_price": 95234.0,
    "unrealized_pnl": 0.234,
    "leverage": 3
  }
]
```

##### 5. 启动套利
```http
POST /api/control/start

Response:
{
  "status": "success",
  "message": "套利已启动"
}
```

##### 6. 暂停套利
```http
POST /api/control/pause

Response:
{
  "status": "success",
  "message": "套利已暂停"
}
```

##### 7. 调整利润阈值
```http
POST /api/control/threshold
Content-Type: application/json

{
  "min_profit_pct": 0.003
}

Response:
{
  "status": "success",
  "new_threshold": 0.003
}
```

#### WebSocket 端点

```javascript
// 连接
const ws = new WebSocket('ws://localhost:8000/ws');

// 接收实时更新
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('实时数据:', data);
  // {
  //   "type": "quote_update",
  //   "data": {...}
  // }
  // {
  //   "type": "arbitrage_opportunity",
  //   "data": {...}
  // }
  // {
  //   "type": "position_update",
  //   "data": {...}
  // }
};
```

---

## 测试流程

### 1. 单元测试

```bash
# 安装测试依赖
pip install pytest pytest-asyncio pytest-cov

# 运行所有测试
pytest tests/

# 运行特定模块测试
pytest tests/test_capital_orchestrator.py

# 查看覆盖率
pytest --cov=perpbot tests/
```

### 2. 集成测试

```bash
# 测试交易所连接
PYTHONPATH=src python -m tests.integration.test_exchange_connectivity

# 测试下单流程
PYTHONPATH=src python -m tests.integration.test_order_flow

# 测试资金调度
PYTHONPATH=src python -m tests.integration.test_capital_flow
```

### 3. 模拟测试

```bash
# 使用模拟交易所
PYTHONPATH=src python -m perpbot.cli cycle --config config.test.yaml --mock
```

### 4. 测试网测试

参见 [快速开始 - 小额测试流程](#6-小额测试流程)

---

## 常见问题

### Q1: 下单失败，提示 "资金不足"
**A**: 检查以下几点：
1. 实际余额是否充足？
```python
await client.get_balance()
```
2. 资金是否被其他订单占用？
```python
orchestrator.current_snapshot()
# 查看 "allocated" 字段
```
3. 是否触发了安全模式？
```python
# 检查 safe_mode 字段
if safe_mode == 1:
    # 仅允许刷量层和储备层
```

### Q2: 套利机会很多，但从不执行
**A**: 可能原因：
1. 利润阈值设置过高
```yaml
# config.yaml
arbitrage:
  min_profit_pct: 0.002  # 降低到 0.2%
```
2. 风控拒绝
```bash
# 查看日志
tail -f perpbot.log | grep "RISK"
```
3. 资金不足
```bash
# 检查资金池
curl http://localhost:8000/api/overview
```

### Q3: WebSocket 连接频繁断开
**A**: 解决方法：
1. 增加重连机制（已内置）
2. 检查网络稳定性
3. 使用专用 VPS
4. 启用心跳保活
```python
# exchanges/base.py
async def _websocket_keepalive(self):
    while True:
        await self.ws.ping()
        await asyncio.sleep(30)
```

### Q4: STARK 签名失败
**A**: 检查：
1. 私钥格式是否正确？
```python
# 应该是 0x 开头的 64 字符十六进制
PARADEX_PRIVATE_KEY=0x1234...abcd
```
2. 账户地址是否匹配？
```python
# 从私钥派生公钥/地址
from starknet_py.net.account.account import Account
account = Account.from_key(private_key)
print(account.address)
```

### Q5: Gas fee 过高怎么办？
**A**: 策略：
1. 监控 Gas 价格
```python
# hedge_volume_engine.py
if gas_price > max_gas_price:
    logger.info("Gas fee 过高，跳过")
    return
```
2. 选择低 Gas 时段（凌晨）
3. 使用 Layer 2（Paradex/Extended 已经是 L2）

### Q6: 如何查看详细日志？
**A**: 
```bash
# 设置日志级别为 DEBUG
export LOG_LEVEL=DEBUG

# 运行
PYTHONPATH=src python -m perpbot.cli serve

# 查看日志文件
tail -f perpbot.log

# 查看特定模块日志
tail -f perpbot.log | grep "arbitrage"
```

### Q7: 如何备份配置和数据？
**A**:
```bash
# 备份配置
cp config.yaml config.yaml.backup_$(date +%Y%m%d)

# 备份密钥（加密后）
cp .env.encrypted .env.encrypted.backup_$(date +%Y%m%d)

# 备份交易记录
cp alerts.csv alerts.csv.backup_$(date +%Y%m%d)
cp trades.db trades.db.backup_$(date +%Y%m%d)

# 定期备份（cron）
0 0 * * * /path/to/backup.sh
```

### Q8: 如何紧急停止所有交易？
**A**:
```bash
# 方法 1: Web 控制台
访问 http://localhost:8000 点击 "暂停套利"

# 方法 2: API
curl -X POST http://localhost:8000/api/control/pause

# 方法 3: 杀进程
pkill -f perpbot

# 方法 4: 紧急平仓
PYTHONPATH=src python -m perpbot.cli emergency_close_all
```

---

## 更新日志

### 2024-12-XX: 三层资金管理重构
- ✅ 将原 5 层简化为 3 层（刷量/套利/储备）
- ✅ 优化资金调度逻辑
- ✅ 更新配置文件说明
- ✅ 同步 README 文档

### 2024-12-XX: Paradex 集成
- ✅ 完成 Paradex REST API 封装
- ✅ 完成 WebSocket 行情订阅
- 🚧 下单接口测试中
- ⏸️ 待测试网验证

### 2024-12-XX: Extended 集成
- ✅ 完成 Extended REST API 封装
- ✅ 完成 WebSocket 行情订阅
- 🚧 下单接口测试中
- ⏸️ 待测试网验证

### 2024-12-XX: 文档完善
- ✅ 更新主 README.md
- ✅ 添加模块详解
- ✅ 添加 API 文档
- ✅ 添加测试流程
- ✅ 添加常见问题

### 待办事项
- [ ] Paradex 主网小额测试
- [ ] Extended 主网小额测试
- [ ] 补充单元测试
- [ ] 添加性能监控
- [ ] 支持更多交易对
- [ ] 优化套利算法
- [ ] 添加机器学习预测模块

---

## 贡献指南

欢迎提交 Issue 和 Pull Request！

### 开发流程
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 代码规范
- 遵循 PEP 8
- 添加类型注解
- 编写单元测试
- 更新文档

---

## 许可证

MIT License

---

## 联系方式

- **GitHub**: https://github.com/fordxx/perp-tools
- **Issues**: https://github.com/fordxx/perp-tools/issues
- **Discussions**: https://github.com/fordxx/perp-tools/discussions

---

## 免责声明

本项目仅供学习和研究使用。加密货币交易存在高风险，请谨慎投资。作者不对任何交易损失负责。

**风险提示**:
- 加密货币市场高度波动
- 自动交易可能产生意外损失
- 请务必在测试网充分验证
- 主网交易前请小额测试
- 不要投入无法承受损失的资金

---

## 鸣谢

- Anthropic Claude (代码辅助)
- Paradex Team
- Extended Exchange Team
- Python 社区

---

**最后更新**: 2024-12-08  
**文档版本**: v1.0  
**分支**: `claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF`
