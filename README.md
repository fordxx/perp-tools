# PerpBot - 多交易所模块化自动套利机器人

本项目提供一个可扩展的自动交易与套利框架，覆盖 EdgeX、Backpack、Paradex、Aster、GRVT、Extended、OKX、Binance 等多家交易所。框架支持真实 REST/WebSocket 连接、自动止盈、跨所套利、报警通知以及简洁的 Web 控制台，方便快速落地多交易所策略。

## 功能亮点

- **模块化交易所层**：为所有交易所提供统一接口，方便按需接入。
- **自动止盈策略**：开仓后按配置的收益阈值自动平仓。
- **套利扫描与执行**：跨所发现价差，叠加风控后触发双边下单并自动对冲。
- **动态利润门槛**：结合近期价差波动动态调整最小收益，并基于收益、流动性与交易所可靠性评分排序。
- **并发行情获取**：共享 WebSocket 价格缓存，REST 作为回退，并按交易所限流保护。
- **交易记录与分析钩子**：每次套利尝试都会落盘（CSV/SQLite），便于回溯和统计。
- **智能提醒**：支持突破、区间、百分比、价差、波动率等条件，可推送到 Telegram/Lark/Webhook/控制台/音频，支持自动启动交易或自动下单，并完整记录历史。
- **FastAPI Web 控制台**：实时展示 BTC/ETH 跨所报价、套利机会（含优先级评分与置信度）、仓位、资产曲线、提醒历史，可一键启停套利或在线调整利润阈值，WebSocket 实时推送免刷新。
- **配置驱动**：通过 `config.example.yaml` 快速调整策略与风控参数。

## 目录结构

- `src/perpbot/models.py` —— 订单、仓位、报价、提醒、全局状态等共享模型。
- `src/perpbot/exchanges/base.py` —— 统一的交易所接口及各交易所真实客户端实现。
- `src/perpbot/strategy/take_profit.py` —— 止盈交易循环与持仓生命周期管理。
- `src/perpbot/arbitrage/scanner.py` —— 考虑深度与成本的跨所套利信号生成器。
- `src/perpbot/arbitrage/arbitrage_executor.py` —— 双边套利执行与对冲保护。
- `src/perpbot/position_guard.py` —— 单笔仓位风险限制与冷却。
- `src/perpbot/risk_manager.py` —— 账户级风控：单笔上限、回撤、日亏、敞口、方向一致性、连续失败、快市冻结等。
- `src/perpbot/monitoring/alerts.py` —— 规则化提醒与可选的自动下单。
- `src/perpbot/monitoring/web_console.py` —— FastAPI Web 控制台与后台交易服务。
- `src/perpbot/monitoring/static/index.html` —— 轻量化实时控制面板。
- `src/perpbot/cli.py` —— CLI 入口，可跑单次交易循环或启动控制台服务。
- `src/perpbot/capital_orchestrator.py` —— 资金分层调度与安全模式切换的总控模块。

## 资金调度与分层设计

- **类结构**：`CapitalOrchestrator` 内部包含 `ExchangeCapitalProfile`（按交易所维度记录五层资金池、安全模式与回撤状态）和 `CapitalLayerState`（每层的目标权重、最大占用、可用/占用金额）。
- **核心状态**：
  - `wu_size`（单所基准资金，默认 1 WU = 10,000 USDT）
  - `layer_targets` / `layer_max_usage`（L1-L5 目标比例、最大占用比例）
  - `safe_layers`（触发单所回撤≥5%时只允许的层级，默认 L1+L4）
  - `exchange_profiles`（每所的资金池快照、当日回撤、是否安全模式）
- **工作流程**：
  1. 策略/执行器在下单前调用 `reserve_for_strategy(exchanges, amount, strategy)`，根据策略映射优先分配 L1-L4（不足时可从 L5 借用）。
  2. 若资金不足或交易所处于安全模式，会返回拒绝理由，执行器直接跳过下单。
  3. 下单完成后调用 `release(reservation)` 归还占用，保持实时可用额度。
  4. 当监测到单所回撤超过 `capital_drawdown_limit_pct` 时，`update_drawdown` 会将该所切换至安全模式，只允许“刷量对冲 + 费率层”并可自动降仓/熔断。
  5. `current_snapshot` 提供 Web/监控端的分层水位，用于可视化 L1-L5 的占用与剩余额度。

- **对接方式**：`ArbitrageExecutor` 已在下单前向 `CapitalOrchestrator` 申请额度，`cli.py` 与 Web `TradingService` 默认加载配置中的五层比例（L1 20%、L2 30%、L3 25%、L4 10%、L5 15%）并为每个交易所初始化 1 WU 资金池，未来可扩展为实时余额/回撤驱动的动态调整。

## 快速开始

### 项目状态

仓库内置完整的模拟与真实连接框架：CLI、监控 API、套利检测、提醒、止盈循环都可端到端运行。Binance USDT-M 与 OKX SWAP 提供真实 REST/WebSocket 连接（有密钥则自动启用，否则退回模拟）。

> 行情与套利范围：Binance/OKX 只用于行情参考与异常波动过滤，不参与套利下单；套利信号与执行严格使用各交易所自己的实时盘口与深度，不会以 CEX 价格作为锚定价。

1. 安装依赖（推荐 Python 3.10+）：

   ```bash
   pip install -r requirements.txt
   ```

2. 查看并调整 `config.example.yaml`（需要可复制为 `config.yaml`）。

3. 运行单次交易/监控循环，查看行情、成本校正后的套利边际以及自动止盈行为（需设置 `PYTHONPATH=src` 以便加载包）：

   ```bash
   PYTHONPATH=src python -m perpbot.cli cycle --config config.example.yaml
   ```

4. 启动 Web 控制台（默认端口 8000）：

   ```bash
   PYTHONPATH=src python -m perpbot.cli serve --config config.example.yaml --port 8000
   ```

   打开 `http://localhost:8000/` 可查看实时 BTC/ETH 行情、套利价差、持仓与资产曲线，可一键开/停套利并在线调整利润阈值。API 接口位于 `/api/*`（`/api/overview`、`/api/control/start`、`/api/control/pause`、`/api/control/threshold`、`/api/quotes`、`/api/arbitrage`、`/api/positions`）。

### 风控与执行配置

`config.example.yaml` 提供 `max_risk_pct`、`assumed_equity`、`risk_cooldown_seconds` 用于限制单笔风险（默认账户 5%）、在无余额时假设的权益以及失败后的冷却。还包含 `max_drawdown_pct`、`daily_loss_limit_pct`（默认单日亏损 8% 即停止）、`max_consecutive_failures`（连续 3 次失败停机）、`max_symbol_exposure_pct`、`enforce_direction_consistency`、冻结阈值（默认 1 秒内 0.5% 变动）等设置。`loop_interval_seconds` 控制后台循环频率，`arbitrage_min_profit_pct` 可在 Web 控制台实时调节；动态利润门槛由 `high_vol_min_profit_pct` 与 `low_vol_min_profit_pct` 配合波动率调整。执行端覆盖滑点上限、部分成交对冲与超时、交易所熔断、余额集中度提醒、以及优先级/置信度评分过滤。

### 提醒与通知

在 `alerts` 中定义提醒规则，可选择价格突破、区间、百分比变化（带回溯窗口）、跨品种价差、波动率等条件。每条提醒可配置 `channels`（console、telegram、lark、webhook、audio）、`action`（`notify`、`start-trading` 或 `auto-order`）及自动下单尺寸。全局通知凭据在 `notifications` 下，所有触发都会写入 `alert_record_path`（CSV 或 SQLite）便于后续统计。

### 环境与凭据

在根目录创建 `.env` 并填入所需密钥。缺失密钥时自动使用模拟连接。

```env
# Binance USDT-M 期货
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_ENV=testnet  # 或 "live"

# OKX 永续合约
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet  # 或 "live"
```

### 说明

- Binance 与 OKX 客户端采用官方 REST + WebSocket，内置异常处理与日志；无密钥则退回模拟模式。
- 策略与信号逻辑保持简化，便于二次扩展到生产级策略。
