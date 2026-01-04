# Changelog

本文档记录 TW168 项目的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划中
- [ ] 持久化 TradePlan 到数据库
- [ ] 添加最大持仓数限制
- [ ] WebSocket 实时价格推送
- [ ] 完善监控告警系统
- [ ] 性能统计和回测模块

---

## [2.0.0] - 2025-01-01

### 🎉 重大更新

#### 新增功能
- **双交易所支持** - 同时支持 OKX (CEX) 和 Lighter (DEX)
- **双限价入场模式** - 支持梯度建仓，提高成交率
- **信号审计日志** - 完整记录所有信号和交易决策到 JSONL 文件
- **实时 K 线缓存** - WebSocket 订阅 OKX 和 Extended K 线数据
- **RSI 智能过滤** - 基于 K-means 聚类的动态 RSI 阈值
- **风险一致性** - 基于固定风险金额的仓位计算 (RISK_PER_TRADE_USDT)

#### Lighter DEX 集成
- 实现 Lighter V2 协议适配器
- 支持双限价入场订单
- 支持多级止盈止损订单
- WebSocket 订阅 Extended 市场数据
- 自动刷新订单价格 (防止过期)

#### 性能优化
- K 线数据 WebSocket 缓存，降低 API 调用
- 支持最多 200 个 OKX 交易对同时订阅
- 支持最多 50 个 Extended 市场同时订阅
- 闲置市场自动取消订阅 (600 秒无活动)

#### 增强功能
- 支持按时间周期和交易对自定义 RSI 阈值
- 支持 Paper Trade 模式 (按时间周期)
- 改进的 Telegram 通知功能
- 更完善的错误处理和日志记录

### 🔧 配置变更

#### 新增配置项
```bash
# 交易所选择
EXCHANGE=okx  # okx 或 lighter

# 双限价入场
ENTRY_TWO_LIMIT_ENABLED=false
ENTRY_TWO_LIMIT_REF_BAR=1m
ENTRY_TWO_LIMIT_L1_R=0.25
ENTRY_TWO_LIMIT_L2_R=0.65
ENTRY_TWO_LIMIT_L1_PCT=0.70
ENTRY_TWO_LIMIT_L2_PCT=0.30
ENTRY_TWO_LIMIT_TIMEOUT_CANDLES=1.0
ENTRY_TWO_LIMIT_TIMEOUT_CANDLES_BY_TF=
ENTRY_TWO_LIMIT_POLL_SECONDS=2.0

# RSI 过滤
RSI_ALLOW_NO_ZONE=true
RSI_FILTER_ENABLED=false
RSI_THRESHOLD_MODE=kmeans  # kmeans 或 percentile
RSI_SMOOTH=true
RSI_SMOOTH_PERIOD=4
RSI_MA_TYPE=ema
RSI_PCT_LOW=25
RSI_PCT_HIGH=75
RSI_PCT_BY_TF=
RSI_PCT_BY_SYMBOL=
RSI_MAX_DATA=3000
RSI_MAX_DATA_BY_TF=
RSI_MAX_DATA_BY_SYMBOL=

# K 线缓存
CANDLE_WS_ENABLED=true
CANDLE_WS_OKX_ENABLED=true
CANDLE_WS_EXTENDED_ENABLED=true
CANDLE_WS_TFS=1h
CANDLE_CACHE_TTL_SECONDS=30
CANDLE_CACHE_MAX_BARS=4000
CANDLE_WS_OKX_MAX_SUBS=200
CANDLE_WS_EXTENDED_MAX_SUBS=50
CANDLE_WS_EXTENDED_IDLE_SECONDS=600
CANDLE_WS_SYMBOL_TFS=
CANDLE_WS_SYMBOL_TFS_FILE=
CANDLE_WS_SYMBOL_TFS_STRICT=false

# Extended 订单刷新
EXTENDED_REFRESH_SECONDS=300
EXTENDED_REFRESH_ENABLED=true
EXTENDED_REFRESH_SL_ENABLED=true
EXTENDED_REFRESH_TP_ENABLED=true
EXTENDED_ORDER_EXPIRE_HOURS=168

# Paradex/Lighter
PARADEX_ENV=prod
PARADEX_L2_PRIVATE_KEY=
PARADEX_ACCOUNT_ADDRESS=

# 信号审计
SIGNAL_AUDIT_ENABLED=true
SIGNAL_AUDIT_DIR=/app/logs

# Paper Trade 模式
PAPER_TRADE_TFS=
```

### 🐛 Bug 修复
- 修复 clOrdId 包含下划线导致的 OKX 51000 错误
- 修复 ZONE 信号过期时间检查逻辑
- 修复多周期 (1H, 4H) ZONE 信号失效问题
- 修复 WebSocket 心跳超时导致的连接断开
- 修复 Extended 订单过期问题

### 📝 文档更新
- 全新的 README.md，更清晰的结构
- 创建 CHANGELOG.md 版本更新日志
- 更新 DESIGN.md 为最新架构
- 添加详细的 API 文档
- 添加部署和运维文档

---

## [1.1.0] - 2024-12-20

### 新增
- **ZONE 过期逻辑优化**
  - ZONE_TTL_SECONDS: 900秒 → 43200秒 (12小时)
  - 移除严格的过期时间检查
  - 现在只要设置了 ZONE 就一直有效，直到被新的 ZONE 覆盖

### 改进
- **多周期支持增强**
  - 1H、4H 等大周期现在可以正常工作
  - ZONE 信号可以持续多个小时
  - 只看最新一次 ZONE 状态，不管多久之前设置的

### 文档
- 添加 TradingView 配置建议
- 添加工作流程说明
- 更新配置变更说明

---

## [1.0.0] - 2024-12-20

### 🎉 首次发布

#### 核心功能
- **双信号确认机制** - ZONE + DIV 两步确认
- **智能止损计算**
  - Lookback 方法 (回看 N 根 K 线)
  - Pivot 方法 (基于价格结构)
  - ATR 自适应缓冲
- **四级止盈阶梯**
  - TP1: 1.5R (70%)
  - TP2: 2.0R (15%)
  - TP3: 2.5R (10%)
  - TP4: 3.5R (5%)
- **移动止盈** - 启动于 2.0R，回撤 0.75R 触发
- **形态过滤** (可选)
  - W 底形态识别
  - 头肩顶形态识别

#### OKX 集成
- 支持 OKX V5 API
- 双向持仓模式 (long_short_mode)
- Market 订单 + 附加止损单
- TradeManager 后台管理止盈

#### 风控机制
- 交易冷却时间 (120 秒)
- 信号去重 (30 分钟)
- 方向控制开关 (ENABLE_LONG/ENABLE_SHORT)
- 交易对白名单
- ZONE 信号 TTL (15 分钟)
- 实盘/模拟交易开关

#### 基础设施
- FastAPI Web 服务
- Docker 支持
- 环境变量配置
- 日志记录
- 健康检查端点

---

## [0.9.0] - 2024-12-14 (测试版)

### 新增
- 初始项目结构
- Webhook 接收端点
- 基础订单执行逻辑
- 止损计算原型

### 已知问题
- clOrdId 格式包含下划线会报错
- ZONE 过期逻辑过于严格
- 缺少完善的错误处理

---

## 版本说明

### 版本号规则
- **主版本号 (Major)**: 不兼容的 API 修改
- **次版本号 (Minor)**: 向下兼容的功能性新增
- **修订号 (Patch)**: 向下兼容的问题修正

### 标签含义
- `新增` - 新功能
- `改进` - 对现有功能的改进
- `修复` - Bug 修复
- `变更` - 破坏性变更
- `废弃` - 即将移除的功能
- `移除` - 已移除的功能
- `安全` - 安全相关修复

---

## 迁移指南

### 从 1.x 升级到 2.0

#### 配置文件变更
需要在 `.env` 中添加以下新配置：

```bash
# 1. 选择交易所
EXCHANGE=okx  # 保持现有行为

# 2. 信号审计 (推荐启用)
SIGNAL_AUDIT_ENABLED=true
SIGNAL_AUDIT_DIR=/app/logs

# 3. RSI 过滤 (可选)
RSI_ALLOW_NO_ZONE=true
RSI_FILTER_ENABLED=false

# 4. K 线缓存 (推荐启用)
CANDLE_WS_ENABLED=true
CANDLE_WS_OKX_ENABLED=true
```

#### API 变更
- Webhook 响应格式保持兼容
- 新增 `/status` 端点查看系统状态
- 新增 `/candles/{symbol}` 端点查看缓存的 K 线

#### 数据库变更
- 无需数据库迁移 (仍使用内存存储)
- TradePlan 数据结构兼容

### 从 0.9 升级到 1.0

#### 重大变更
- clOrdId 格式变更 (移除下划线)
- ZONE TTL 默认值变更
- 配置项名称规范化

#### 需要手动修改
1. 更新 TradingView Webhook URL
2. 重新生成 TV_WEBHOOK_SECRET
3. 检查所有配置项名称

---

## 致谢

感谢所有贡献者和测试者的反馈！

---

**维护者:** TW168 Team
**最后更新:** 2025-01-01
**文档版本:** 2.0.0
