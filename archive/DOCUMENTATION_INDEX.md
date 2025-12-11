# PerpBot 文档索引

> **分支**: `claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF`  
> **最后更新**: 2024-12-08

---

## 📚 完整文档列表

### 1. [README.md](README.md) - 项目总览 ⭐
**48 KB | 必读**

**内容**:
- 项目概述与核心特性
- **三层资金管理系统详解**（刷量 70% + 套利 20% + 储备 10%）
- 交易所集成状态（Paradex, Extended, OKX, Binance）
- 完整目录结构说明
- 所有模块的详细功能说明
- 快速开始指南
- 配置文件完整说明
- 小额测试流程
- 常见问题解答

**适合**:
- ✅ 新用户了解项目
- ✅ 快速上手部署
- ✅ 查找配置说明
- ✅ 排查常见问题

### 2. [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构 🏗️
**56 KB | 开发者必读**

**内容**:
- 完整的系统架构图
- 五层架构设计（表示层、应用层、业务层、资金层、交易所层）
- 核心模块详解（资金管理、交易所、策略、风控、监控）
- 数据流与执行流程图
- 资金管理架构深度解析
- 完整的订单生命周期
- 多层风控体系
- 监控与告警机制
- 技术选型说明
- 扩展性设计指南

**适合**:
- ✅ 理解系统设计
- ✅ 二次开发
- ✅ 问题调试
- ✅ 性能优化

### 3. [SECURITY.md](SECURITY.md) - 安全指南 🔒
**21 KB | 生产部署必读**

**内容**:
- 威胁模型分析
- API 密钥管理最佳实践
- 加密存储方案（Fernet / AWS Secrets Manager / Vault）
- Subkey（子密钥）详细说明
- 网络安全配置（防火墙、SSH、HTTPS、VPN）
- 权限最小化策略
- 审计日志实现
- 应急响应流程
- 安全检查清单

**适合**:
- ✅ 生产环境部署前检查
- ✅ 密钥管理
- ✅ 安全加固
- ✅ 应急处理

---

## 🎯 快速参考

### 三层资金管理（核心）

```
┌─────────────────────────────────────┐
│  L1: 刷量层 (70%)                   │
│  用途: 对冲刷量、高频交易            │
│  风险: 低                            │
│  策略: wash_trade, hft              │
├─────────────────────────────────────┤
│  L2: 套利层 (20%)                   │
│  用途: 跨所套利、中频策略            │
│  风险: 中                            │
│  策略: arbitrage, flash, stat       │
├─────────────────────────────────────┤
│  L3: 储备层 (10%)                   │
│  用途: 应急补仓、资金费率套利        │
│  风险: 动态                          │
│  策略: funding, emergency           │
└─────────────────────────────────────┘

⚠️ 回撤 >= 5% 触发安全模式:
  ✅ 刷量层继续
  ❌ 套利层禁用
  ✅ 储备层应急
```

### 交易所状态

| 交易所 | 状态 | 行情 | 下单 | 用途 |
|--------|------|------|------|------|
| **Paradex** | 🚧 开发中 | ✅ | 🚧 80% | 主力 DEX |
| **Extended** | 🚧 开发中 | ✅ | 🚧 80% | 主力 DEX |
| OKX | 🟡 仅行情 | ✅ | ❌ | 参考价格 |
| Binance | 🟡 仅行情 | ✅ | ❌ | 参考价格 |
| 其他 | ⏸️ 待启用 | ❌ | ❌ | 保留代码 |

### 关键命令

```bash
# 安装依赖
pip install -r requirements.txt

# 单次测试运行
PYTHONPATH=src python -m perpbot.cli cycle --config config.yaml

# 启动 Web 控制台
PYTHONPATH=src python -m perpbot.cli serve --config config.yaml --port 8000

# 访问控制台
http://localhost:8000

# 紧急停止
pkill -f perpbot
```

### 环境变量（关键）

```bash
# Paradex
PARADEX_API_KEY=your_api_key
PARADEX_PRIVATE_KEY=0x...  # STARK 私钥
PARADEX_ACCOUNT=0x...

# Extended
EXTENDED_API_KEY=your_api_key
EXTENDED_STARK_KEY=0x...
EXTENDED_VAULT_NUMBER=12345

# 主密钥（加密用）
MASTER_KEY=your_master_encryption_key
```

### 关键配置

```yaml
# config.yaml 核心配置
capital:
  wu_size: 10000.0            # 单所基准资金
  wash_budget_pct: 0.7        # 刷量层 70%
  arb_budget_pct: 0.2         # 套利层 20%
  reserve_pct: 0.1            # 储备层 10%
  drawdown_limit_pct: 0.05    # 5% 触发安全模式

arbitrage:
  min_profit_pct: 0.002       # 最小利润 0.2%
  max_position_size: 100.0    # 单边最大 100 USDT

risk:
  max_drawdown_pct: 0.10      # 最大回撤 10%
  daily_loss_limit_pct: 0.05  # 每日亏损 5%
  max_consecutive_failures: 3 # 连续失败 3 次暂停
```

---

## 📖 使用场景指南

### 场景 1: 初次部署
**阅读顺序**:
1. README.md - "快速开始" 章节
2. SECURITY.md - "部署前检查清单"
3. README.md - "小额测试流程"

### 场景 2: 理解架构
**阅读顺序**:
1. README.md - "系统架构" 章节
2. ARCHITECTURE.md - 完整阅读
3. README.md - "模块详解"

### 场景 3: 二次开发
**阅读顺序**:
1. ARCHITECTURE.md - "核心模块" + "扩展性设计"
2. README.md - "目录结构" + "模块详解"
3. README.md - "API 文档"

### 场景 4: 生产部署
**阅读顺序**:
1. SECURITY.md - 完整阅读
2. README.md - "安全指南" + "配置说明"
3. SECURITY.md - "安全检查清单"

### 场景 5: 问题排查
**阅读顺序**:
1. README.md - "常见问题"
2. ARCHITECTURE.md - "数据流" + "执行流程"
3. README.md - "测试流程"

---

## 🔍 关键概念速查

### 资金管理相关

| 概念 | 说明 | 位置 |
|------|------|------|
| WU (Work Unit) | 工作单位，默认 1 WU = 10,000 USDT | README.md, ARCHITECTURE.md |
| 三层资金池 | 刷量/套利/储备 | README.md §资金管理系统 |
| 安全模式 | 回撤 >= 5% 触发，禁用套利层 | README.md, ARCHITECTURE.md |
| 跨层借用 | 不足时从储备层临时借用 | README.md §资金管理系统 |
| CapitalOrchestrator | 资金总控类 | README.md §模块详解 |

### 交易所相关

| 概念 | 说明 | 位置 |
|------|------|------|
| ExchangeBase | 统一交易所接口 | ARCHITECTURE.md §核心模块 |
| Paradex | Starknet DEX，零 Maker 费 | README.md §交易所集成状态 |
| Extended | Starknet DEX，统一保证金 | README.md §交易所集成状态 |
| STARK 签名 | DEX 订单签名方式 | ARCHITECTURE.md, SECURITY.md |
| Subkey | 子密钥，可撤销 | SECURITY.md §API密钥管理 |

### 风控相关

| 概念 | 说明 | 位置 |
|------|------|------|
| 单笔风险上限 | 默认 5% 账户权益 | README.md §配置说明 |
| 最大回撤 | 默认 10% | README.md §配置说明 |
| 连续失败保护 | 3 次暂停 | ARCHITECTURE.md §风控体系 |
| 快市冻结 | 1秒内 0.5% 波动冻结 | README.md §风控配置 |
| 人工覆盖 | 风控暂停后人工确认恢复 | README.md §风控配置 |

### 策略相关

| 概念 | 说明 | 位置 |
|------|------|------|
| 套利扫描器 | Scanner，价差发现 | ARCHITECTURE.md §核心模块 |
| 套利执行器 | Executor，双边下单 | ARCHITECTURE.md §核心模块 |
| 止盈策略 | TakeProfit，自动平仓 | README.md §模块详解 |
| 刷量引擎 | HedgeVolume，对冲刷量 | README.md §模块详解 |
| 评分算法 | 利润+流动性+可靠性 | ARCHITECTURE.md §策略层 |

---

## 🛠️ 开发者速查

### 添加新交易所

1. 创建客户端类 `exchanges/new_exchange_client.py`
2. 继承 `ExchangeBase`
3. 实现所有抽象方法
4. 在 `config.yaml` 中注册
5. 参考: ARCHITECTURE.md §扩展性设计

### 添加新策略

1. 创建策略类 `strategy/my_strategy.py`
2. 实现 `analyze()` 和 `execute()` 方法
3. 注册到 `TradingService`
4. 参考: ARCHITECTURE.md §扩展性设计

### 添加新风控规则

1. 扩展 `RiskManager` 类
2. 重写 `check()` 方法
3. 添加自定义检查逻辑
4. 参考: ARCHITECTURE.md §风控体系

### 调试技巧

```bash
# 启用 DEBUG 日志
export LOG_LEVEL=DEBUG

# 查看特定模块日志
tail -f perpbot.log | grep "arbitrage"

# 查看资金池状态
curl http://localhost:8000/api/overview | jq '.capital_snapshot'

# 查看当前套利机会
curl http://localhost:8000/api/arbitrage | jq '.'
```

---

## 📊 数据流速查

```
行情获取:
  WebSocket (实时) → Cache → Strategy

套利执行:
  Scanner → 评分 → Executor → 资金预留 → 风控检查 
  → 并发下单 → 成交确认 → 记录 → 释放资金

资金流转:
  Total Pool → [Wash 70% | Arb 20% | Reserve 10%]
  → 策略申请 → 占用 → 执行 → 释放
  
  回撤 >= 5% → 安全模式 → 仅 Wash + Reserve
```

---

## 🚨 紧急情况速查

### 怀疑密钥泄露
```bash
1. pkill -f perpbot  # 停止服务
2. 前往交易所撤销 API 密钥
3. 转移资金到冷钱包
4. 分析日志: grep "SUSPICIOUS" security_audit.log
5. 轮换所有密钥
```

### 检测到异常交易
```bash
1. curl -X POST http://localhost:8000/api/control/pause
2. PYTHONPATH=src python -m perpbot.cli emergency_close_all
3. 检查订单历史
4. 联系交易所
```

### 系统故障
```bash
1. 检查日志: tail -100 perpbot.log
2. 检查进程: ps aux | grep perpbot
3. 检查网络: ping api.paradex.trade
4. 重启服务: systemctl restart perpbot
```

---

## 📝 更新记录

### v1.0 (2024-12-08)
- ✅ 完整的 README.md（48 KB）
- ✅ 系统架构文档（56 KB）
- ✅ 安全指南（21 KB）
- ✅ 文档索引（本文档）

### 待办事项
- [ ] API 参考手册（详细的每个方法说明）
- [ ] 交易所集成指南（Paradex 和 Extended 完整接入文档）
- [ ] 常见问题扩展（100+ 问题）
- [ ] 性能优化指南
- [ ] 故障排查手册

---

## 💡 文档反馈

如有文档问题或建议，请:
1. 提交 Issue: https://github.com/fordxx/perp-tools/issues
2. 发起 Discussion: https://github.com/fordxx/perp-tools/discussions
3. 提交 Pull Request 改进文档

---

## 📄 文档协议

本文档采用 MIT License，与主项目保持一致。

---

**最后更新**: 2024-12-08  
**文档版本**: v1.0  
**总大小**: 125 KB (3 个文档)  
**预计阅读时间**: 
- README.md: 60 分钟
- ARCHITECTURE.md: 90 分钟
- SECURITY.md: 45 分钟
- 总计: **3 小时**
