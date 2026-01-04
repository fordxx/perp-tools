# TW168 文档索引

本文档提供 TW168 项目所有文档的完整索引和导航。

**最后更新:** 2025-01-01
**文档版本:** 2.0

---

## 📚 核心文档 (根目录)

### [README.md](README.md)
**项目主文档** - 项目概览、快速开始、核心特性

**适合人群:** 所有用户
**内容:**
- 核心特性介绍
- 快速开始指南
- 配置说明
- TradingView 信号格式
- 交易策略说明

### [DESIGN.md](DESIGN.md)
**系统设计文档** - 完整的系统设计和实现细节

**适合人群:** 开发者、高级用户
**内容:**
- 系统概述
- 信号接收流程
- 止损止盈计算
- 仓位管理
- 风控机制
- 完整交易流程

### [CHANGELOG.md](CHANGELOG.md)
**版本更新日志** - 所有版本的变更记录

**适合人群:** 所有用户
**内容:**
- 版本历史
- 新增功能
- Bug 修复
- 破坏性变更
- 迁移指南

---

## 📖 docs/ 目录

### 核心文档

#### [docs/README.md](docs/README.md)
**文档导航** - docs 目录结构说明和导航

#### [docs/API.md](docs/API.md)
**API 接口文档** - 所有 HTTP API 端点的详细说明

**适合人群:** 集成开发者、运维人员
**内容:**
- Webhook 端点详解
- 请求/响应格式
- 错误码参考
- TradingView Alert 配置
- 示例代码 (Python/cURL/JavaScript)

#### [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
**部署指南** - 从开发到生产的完整部署流程

**适合人群:** 运维人员、DevOps
**内容:**
- 环境要求
- 本地开发部署
- Docker 部署
- 生产环境部署
- Nginx 反向代理配置
- 升级和回滚指南
- 备份与恢复

#### [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
**故障排查指南** - 常见问题诊断和解决方案

**适合人群:** 所有用户、运维人员
**内容:**
- 快速诊断步骤
- 服务问题排查
- Webhook 问题排查
- 交易问题排查
- API 问题排查
- 性能问题优化
- 日志分析方法

---

### 特性文档 (docs/features/)

#### Lighter DEX 相关

- **[LIGHTER_ASYNC_README.md](docs/features/LIGHTER_ASYNC_README.md)** - Lighter 异步客户端概述
- **[LIGHTER_ASYNC_IMPLEMENTATION.md](docs/features/LIGHTER_ASYNC_IMPLEMENTATION.md)** - 异步实现详解
- **[LIGHTER_ASYNC_ADAPTER.md](docs/features/LIGHTER_ASYNC_ADAPTER.md)** - 适配器设计
- **[LIGHTER_ASYNC_QUICK_REF.md](docs/features/LIGHTER_ASYNC_QUICK_REF.md)** - 快速参考
- **[LIGHTER_ASYNC_STATUS.md](docs/features/LIGHTER_ASYNC_STATUS.md)** - 实现状态
- **[LIGHTER_WEBSOCKET.md](docs/features/LIGHTER_WEBSOCKET.md)** - WebSocket 集成
- **[LIGHTER_CANDLES_READY.md](docs/features/LIGHTER_CANDLES_READY.md)** - K 线缓存就绪
- **[LIGHTER_TESTS_PASSED.md](docs/features/LIGHTER_TESTS_PASSED.md)** - 测试报告
- **[LIGHTER_TRADING_TEST_GUIDE.md](docs/features/LIGHTER_TRADING_TEST_GUIDE.md)** - 交易测试指南
- **[LIGHTER_API_DIAGNOSIS.md](docs/features/LIGHTER_API_DIAGNOSIS.md)** - API 诊断

#### 止盈止损策略

- **[LADDER_ORDERS.md](docs/features/LADDER_ORDERS.md)** - 阶梯止盈原理
- **[LADDER_OPTIMIZATION_PROPOSALS.md](docs/features/LADDER_OPTIMIZATION_PROPOSALS.md)** - 优化建议
- **[LADDER_IMPLEMENTATION_PLAN.md](docs/features/LADDER_IMPLEMENTATION_PLAN.md)** - 实现计划
- **[LADDER_CONFIG_D.md](docs/features/LADDER_CONFIG_D.md)** - 配置方案 D
- **[SL_CONFIG_PRESETS.md](docs/features/SL_CONFIG_PRESETS.md)** - 止损配置预设

#### RSI 和技术分析

- **[RSI_DIVERGENCE_SL_ANALYSIS.md](docs/features/RSI_DIVERGENCE_SL_ANALYSIS.md)** - RSI 背离和止损分析

---

### 使用指南 (docs/guides/)

#### [QUICK_REFERENCE.md](docs/guides/QUICK_REFERENCE.md)
**快速参考** - 常用命令和配置速查

**内容:**
- 常用命令
- 配置速查表
- 快速修复方法

#### [MONITOR_GUIDE.md](docs/guides/MONITOR_GUIDE.md)
**监控指南** - 系统监控和日志管理

**内容:**
- 监控脚本使用
- 关键指标说明
- 日志管理
- 告警配置

#### [ASYNC_REFACTOR_GUIDE.md](docs/guides/ASYNC_REFACTOR_GUIDE.md)
**异步重构指南** - Lighter 异步重构详解

**内容:**
- 异步重构原因
- 迁移步骤
- 性能对比

#### [DEPLOYMENT_CHECKLIST.md](docs/guides/DEPLOYMENT_CHECKLIST.md)
**部署检查清单** - 部署前后检查项

**内容:**
- 部署前检查
- 部署后验证
- 常见问题

#### [MONITORING_LOG.md](docs/guides/MONITORING_LOG.md)
**监控日志** - 监控实施记录

---

### 历史文档 (docs/archive/)

历史文档包含过往的 Bug 修复、测试报告、实现记录等，主要用于参考和归档。

#### Bug 修复记录
- BUG_FIXES.md - 早期 Bug 修复汇总
- BUG_FIX_20251228.md - 2024-12-28 Bug 修复
- CRITICAL_FIXES.md - 关键修复记录
- CRITICAL_FIXES_20251229.md - 2024-12-29 关键修复
- HANGING_ORDERS_RESOLVED.md - 订单挂起问题解决
- PENDING_ORDERS_ISSUE.md - 待处理订单问题
- WEBSOCKET_HEARTBEAT_FIX.md - WebSocket 心跳修复

#### 测试和实现记录
- FULL_SIMULATION_SUCCESS.md - 完整模拟测试成功
- FULL_TRADING_TEST_REPORT.md - 完整交易测试报告
- LIGHTER_TESTS_PASSED.md - Lighter 测试通过
- TEST_RESULT_SOLUTION_C.md - 方案 C 测试结果
- TRADING_TEST_BLOCKED.md - 交易测试阻塞

#### 部署和配置
- DEPLOYMENT_SUCCESS.md - 部署成功记录
- CLEANUP_SOLUTION.md - 清理方案
- SOLUTION_C_IMPLEMENTED.md - 方案 C 实现完成
- PROJECT_HANDOFF_LADDER_CLEANUP.md - 项目交接清理

#### 功能集成
- WEBSOCKET_INTEGRATION_COMPLETE.md - WebSocket 集成完成
- WEBSOCKET_QUICK_START.md - WebSocket 快速开始
- WEBSOCKET_TEST_CONFIG.md - WebSocket 测试配置

#### 配置和优化
- OPTIMIZATION_SUMMARY.md - 优化总结
- MEDIUM_PRIORITY_OPTIMIZATIONS.md - 中优先级优化
- RISK_BY_TIMEFRAME.md - 按时间周期的风险
- SYSTEM_STATUS.md - 系统状态记录

#### 设置指南
- TELEGRAM_SETUP.md - Telegram 通知设置
- TRADINGVIEW_WEBHOOK.md - TradingView Webhook 设置

---

## 🗂️ 文档分类导航

### 按用户类型

#### 新手用户
1. [README.md](README.md) - 了解项目
2. [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - 快速部署
3. [docs/API.md](docs/API.md) - 配置 Webhook
4. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - 遇到问题时查阅

#### 高级用户
1. [DESIGN.md](DESIGN.md) - 深入理解系统
2. [docs/features/](docs/features/) - 了解高级功能
3. [docs/guides/MONITOR_GUIDE.md](docs/guides/MONITOR_GUIDE.md) - 监控系统

#### 开发者
1. [DESIGN.md](DESIGN.md) - 系统架构
2. [docs/API.md](docs/API.md) - API 详解
3. [docs/features/LIGHTER_ASYNC_*.md](docs/features/) - 异步实现
4. [CHANGELOG.md](CHANGELOG.md) - 版本变更

#### 运维人员
1. [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - 部署指南
2. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - 故障排查
3. [docs/guides/MONITOR_GUIDE.md](docs/guides/MONITOR_GUIDE.md) - 监控指南
4. [docs/guides/DEPLOYMENT_CHECKLIST.md](docs/guides/DEPLOYMENT_CHECKLIST.md) - 检查清单

### 按主题

#### 部署相关
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- [docs/guides/DEPLOYMENT_CHECKLIST.md](docs/guides/DEPLOYMENT_CHECKLIST.md)
- [docs/archive/DEPLOYMENT_SUCCESS.md](docs/archive/DEPLOYMENT_SUCCESS.md)

#### 交易策略
- [DESIGN.md](DESIGN.md) - 止损止盈计算
- [docs/features/LADDER_*.md](docs/features/) - 阶梯止盈
- [docs/features/SL_CONFIG_PRESETS.md](docs/features/SL_CONFIG_PRESETS.md)
- [docs/features/RSI_DIVERGENCE_SL_ANALYSIS.md](docs/features/RSI_DIVERGENCE_SL_ANALYSIS.md)

#### Lighter DEX
- [docs/features/LIGHTER_ASYNC_README.md](docs/features/LIGHTER_ASYNC_README.md)
- [docs/features/LIGHTER_WEBSOCKET.md](docs/features/LIGHTER_WEBSOCKET.md)
- [docs/features/LIGHTER_TRADING_TEST_GUIDE.md](docs/features/LIGHTER_TRADING_TEST_GUIDE.md)

#### 监控运维
- [docs/guides/MONITOR_GUIDE.md](docs/guides/MONITOR_GUIDE.md)
- [docs/guides/MONITORING_LOG.md](docs/guides/MONITORING_LOG.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

#### 故障排查
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- [docs/archive/BUG_FIXES.md](docs/archive/BUG_FIXES.md)
- [docs/archive/WEBSOCKET_HEARTBEAT_FIX.md](docs/archive/WEBSOCKET_HEARTBEAT_FIX.md)

---

## 📊 文档统计

### 按类型统计

| 类型 | 数量 | 位置 |
|------|------|------|
| 核心文档 | 3 | 根目录 |
| API 和部署 | 3 | docs/ |
| 特性文档 | 15 | docs/features/ |
| 使用指南 | 5 | docs/guides/ |
| 历史归档 | 19 | docs/archive/ |
| **总计** | **45** | - |

### 文档状态

| 状态 | 说明 | 示例 |
|------|------|------|
| ✅ 最新 | 当前版本维护 | README.md, API.md |
| 📚 稳定 | 内容完整，偶尔更新 | DESIGN.md, DEPLOYMENT.md |
| 📦 归档 | 历史参考，不再更新 | docs/archive/* |

---

## 🔍 快速查找

### 常见问题查找

| 问题 | 文档 |
|------|------|
| 如何开始使用？ | [README.md](README.md) |
| 如何部署？ | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| API 怎么调用？ | [docs/API.md](docs/API.md) |
| 服务启动失败 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Webhook 无响应 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 订单未执行 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 如何配置止损？ | [DESIGN.md](DESIGN.md) |
| 如何使用 Lighter？ | [docs/features/LIGHTER_ASYNC_README.md](docs/features/LIGHTER_ASYNC_README.md) |
| 版本更新了什么？ | [CHANGELOG.md](CHANGELOG.md) |

### 关键词索引

- **部署:** DEPLOYMENT.md, DEPLOYMENT_CHECKLIST.md
- **API:** API.md, DESIGN.md
- **Webhook:** API.md, TRADINGVIEW_WEBHOOK.md
- **止损:** DESIGN.md, SL_CONFIG_PRESETS.md
- **止盈:** DESIGN.md, LADDER_*.md
- **Lighter:** LIGHTER_*.md
- **监控:** MONITOR_GUIDE.md, MONITORING_LOG.md
- **故障:** TROUBLESHOOTING.md, BUG_*.md
- **配置:** README.md, DESIGN.md, QUICK_REFERENCE.md

---

## 📝 文档贡献

### 更新文档

如需更新文档，请遵循以下规范：

1. **Markdown 格式**
   - 使用标准 Markdown 语法
   - 中英文之间加空格
   - 代码块指定语言

2. **文档结构**
   - 清晰的标题层级
   - 添加目录 (长文档)
   - 包含示例代码
   - 添加相关链接

3. **文档位置**
   - 核心文档 → 根目录
   - API/部署 → docs/
   - 功能文档 → docs/features/
   - 使用指南 → docs/guides/
   - 历史文档 → docs/archive/

4. **版本控制**
   - 更新 CHANGELOG.md
   - 更新文档中的"最后更新"日期
   - 重要变更在文档顶部说明

---

## 🔗 相关资源

- **GitHub Repository:** [项目地址]
- **Issue Tracker:** [问题追踪]
- **Discussions:** [讨论区]
- **Telegram Group:** [社区群组]

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
**文档索引版本:** 2.0
