# DEVELOPING_GUIDE.md
# perp-tools 开发指南（企业级 · AI 友好版）
本文件是 **perp-tools** 的官方开发规范，用于指导未来所有开发者（包括 AI 代理、未来你自己、外包工程师）在一致的架构下进行扩展、维护与部署。

本开发指南遵循以下目标：

- 能让任何新开发者 **10 分钟内理解整个系统结构**
- 清晰定义每个模块的 **边界、输入、输出、责任**
- 降低系统复杂度，让套利逻辑保持简洁且高性能
- 让未来的 AI（Claude / ChatGPT / o1 等）能无障碍继续开发
- 标准化报价、下单、风控、日志、部署、回测流程

---

# 目录

1. [系统概览](#系统概览)
2. [目录结构](#目录结构)
3. [核心架构](#核心架构)
    - Global Quote Engine（统一报价引擎）
    - Multi-Exchange Adapters（多交易所适配器）
    - Execution Engine（执行引擎）
    - Risk Engine（风险控制）
    - Hedge Executor / Strategy Layer（策略层）
4. [交易所接口规范](#交易所接口规范)
5. [Global Quote Engine 规范](#global-quote-engine-规范)
6. [Execution Engine 规范](#execution-engine-规范)
7. [延迟、滑点与费率模型](#延迟滑点与费率模型)
8. [日志规范](#日志规范)
9. [如何新增交易所](#如何新增交易所)
10. [测试规范](#测试规范)
11. [部署规范](#部署规范)
12. [AI 协作规范（关键）](#ai-协作规范关键)
13. [未来功能规划](#未来功能规划)

---

# 系统概览
perp-tools 是一个高性能、多交易所衍生品套利框架，特点：

✔ 多交易所实时比较价差  
✔ 支持 OKX + Extended（x10）+ 更多  
✔ 统一报价模型（Global Quote Engine）  
✔ 统一下单与风控规范  
✔ 高频交易友好的低延迟架构  
✔ 接口语义稳定，模块可热插拔  
✔ 自动化回测环境与仿真执行  

---

# 目录结构

```
perp-tools/
│
├── src/
│   ├── perpbot/
│   │   ├── exchanges/          # 多交易所适配器
│   │   │   ├── okx/
│   │   │   ├── extended/
│   │   │   └── ...更多未来交易所
│   │   ├── models/             # 统一数据模型（报价/订单/持仓）
│   │   ├── execution/          # 统一 Execution Engine
│   │   ├── risk/               # 风控模块（仓位、限额、风险比率）
│   │   ├── quote/              # Global Quote Engine
│   │   ├── strategies/         # 策略层（套利、对冲、价差）
│   │   ├── utils/              # 公共工具
│   │   └── config/             # 配置项
│   │
│   ├── tests/
│   │   ├── integration/        # 集成测试（针对真交易所）
│   │   └── unit/               # 单测
│
├── test_extended.py            # 单交易所诊断工具
├── test_okx.py                 # 单交易所诊断工具
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEVELOPING_GUIDE.md    # 本文件
│   └── EXCHANGE_ADAPTER.md
│
└── README.md
```

---

# 核心架构

```
               +---------------------------+
               |   Strategy Layer          |
               | (Arbitrage, Hedge, MM)    |
               +-------------+-------------+
                             |
                Uses Quotes & Positions
                             |
+---------------------------v-----------------------------+
|               Global Quote Engine                       |
|  Unifies OKX / Extended / Binance / ... price stream    |
+---------------------------+-----------------------------+
                            |
                          Normalized
                            |
+---------------------------v-----------------------------+
|                  Execution Engine                       |
|   Unified order model → adapter → exchange              |
+-----------+----------------------------+----------------+
            |                            |
+-----------v-----------+     +-----------v-----------+
|     OKX Adapter       |     |   Extended Adapter    |
+-----------------------+     +-----------------------+
```

---

# Multi-Exchange Adapter 规范

所有交易所都必须实现 ExchangeClient 规范：

```
connect()
disconnect()

get_current_price(symbol)
get_orderbook(symbol, depth)
get_account_positions()
get_account_balances()

place_open_order(request)
place_close_order(position)
cancel_order(order_id)
```

必须返回：

- 标准化的 PriceQuote
- 标准化的 OrderRequest
- 标准化的 OrderResult
- 标准化的 Position

适配器层必须 **保证输入输出格式完全一致**，否则 Quote Engine 与策略会出错。

---

# Global Quote Engine 规范

统一报价引擎负责：

✔ 合并所有交易所最新报价  
✔ 对齐精度（tick size, qty precision）  
✔ 返回多交易所价差矩阵  
✔ 持续缓存订单簿快照  
✔ 处理延迟、断流、数据异常  
✔ 生成套利信号（也可在策略层实现）

输出格式：

```
{
  "SUI/USD": {
      "okx": {bid, ask, ts},
      "extended": {bid, ask, ts},
      "binance": {...}
  }
}
```

若交易所延迟 > 800ms → 标记 stale  
若订单簿 depth < 1 → 标记 illiquid  

---

# Execution Engine 规范

Execution Engine 负责：

✔ 所有订单精度校验  
✔ 根据不同交易所的限制匹配价格 / 数量  
✔ 模拟 MARKET → 使用 IOC LIMIT  
✔ 计算 fee / slippage / execution cost  
✔ 秒级撤单、超时撤单  
✔ 自动平仓系统  

订单生命周期：

```
OrderRequest
 → adapter.place_order()
 → ExecutionOrderResult
 → 状态监控（Stream/REST）
```

订单必须是 **幂等的**：重复提交不能重复下单。

---

# 延迟、滑点与费率模型

ExecutionCostEngine 提供：

- spread_cost
- fee_cost
- maker / taker 判断
- slippage 模拟（订单簿吃单）
- 延迟成本（latency * volatility）
- funding / rebate

推荐模型（简化版）：

```
effective_cost = fee + slippage + spread
```

---

# 日志规范

使用统一 logger：

```
from perpbot.utils.log import get_logger
log = get_logger("perpbot.okx")
```

日志级别：

- INFO：常规事件（连接、下单、取消）
- WARNING：recoverable 错误（延迟、无订单簿）
- ERROR：订单失败、API 错误
- DEBUG：开发阶段数据流详细信息

必须包含：

```
timestamp
exchange
symbol
action
latency (ms)
payload
response
```

---

# 如何新增交易所

只需创建：

```
src/perpbot/exchanges/<name>/client.py
```

继承：

```
class <Name>Client(ExchangeClient)
```

实现关键函数：

- connect()
- fetch_bbo_prices()
- get_order_price()
- place_open_order()
- cancel_order()

然后注册：

```
GlobalQuoteEngine.register(exchange_client)
```

---

# 测试规范

## 单元测试（必须）

位置：

```
tests/unit/
```

单测必须覆盖：

- decimal rounding
- price normalization
- fee/slippage model
- order serialization

## 集成测试

```
tests/integration/
```

在真交易所验证：

- 连接
- 下单
- 撤单
- 成交事件
- 持仓同步

辅助脚本：

- test_extended.py
- test_okx.py

---

# 部署规范

推荐：

### 选项 1：AWS Lightsail（最稳）

- 固定公网 IP
- 成本低
- 可持续运行

### 选项 2：本地 + VSC Remote

开发便利，但不适合长期跑套利。

### Supervisor / pm2 管理进程  
### Redis / SQLite 用于本地缓存  

---

# AI 协作规范（关键）

为了保证 Claude / ChatGPT 能继续扩展系统：

## 1. AI 必须遵守以下规则：

- 不得重构接口的“签名”
- 若需要新增字段，必须保持向后兼容
- 任何新模块必须写入：

```
docs/DEVELOPING_GUIDE.md
docs/ARCHITECTURE.md
```

## 2. 所有重要改动必须写入 CHANGELOG

格式：

```
## 2025-12-11
- [Changed] 更新 ExtendedClient 消息签名格式
- [Added] 新增 ExecutionCostEngine 支持多交易所费率
```

## 3. AI 开发协议（RAG 友好）：

任何 AI 需要了解项目上下文：

```
请加载 docs/DEVELOPING_GUIDE.md 和 docs/ARCHITECTURE.md 后继续回答。
```

---

# 未来功能规划

- 多交易所同步订单簿 → 实时深度预测
- 净风险暴露模型（Net Exposure Model）
- 自动资金迁移（OKX → Extended）
- 全自动多腿套利
- 机器学习预测成交概率（Fill Probability Model）
- 热插拔策略引擎（Strategy Plugins）
- 更智能的风控（动态限价、限流、黑名单）

---

# 结语

本文件定义了一个 **长期可维护、高性能、AI 可协作** 的量化交易系统架构。  
只要遵守本规范，整个系统将保持：

- 稳定
- 高速
- 可扩展
- 易于多 AI 协作

未来每一次新增/修改模块，都必须同步更新本文件。

