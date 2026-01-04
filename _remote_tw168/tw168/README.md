# TW168 - TradingView 自动交易系统

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

基于 FastAPI 的 TradingView Webhook 自动交易服务，支持 OKX 和 Lighter (DEX) 双交易所。

## 📋 目录

- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [TradingView 信号](#tradingview-信号)
- [交易策略](#交易策略)
- [文档导航](#文档导航)
- [部署指南](#部署指南)

## 🚀 核心特性

### 交易功能
- ✅ **双信号确认机制** - ZONE + DIV 两步确认，降低误触发
- ✅ **智能止损计算** - 支持 lookback 和 pivot 两种方法
- ✅ **四级止盈阶梯** - 1.5R / 2.0R / 2.5R / 3.5R 分批止盈
- ✅ **移动止盈保护** - 自动跟踪价格，锁定利润
- ✅ **风险一致性** - 基于固定风险金额的仓位计算
- ✅ **双交易所支持** - OKX (CEX) + Lighter (DEX)

### 高级功能
- 🎯 **RSI 智能过滤** - 基于机器学习的 RSI 阈值
- 📊 **实时 K 线缓存** - WebSocket 订阅，降低延迟
- 🔄 **双限价入场** - 梯度建仓，提高成交率
- 📝 **信号审计日志** - 完整记录所有交易决策
- 🔔 **Telegram 通知** - 实时推送交易状态
- 🛡️ **完善的风控** - 冷却时间、去重、白名单等

## 🏗️ 系统架构

```
TradingView
    │
    ├─► ZONE 信号 (设置市场状态)
    │   └─► 存储到内存 (TTL: 15分钟)
    │
    └─► DIV 信号 (触发交易)
        │
        ├─► Webhook 验证
        ├─► 风控检查
        ├─► RSI 过滤 (可选)
        ├─► 止损计算
        ├─► 止盈计算
        │
        ├─► OKX 交易所
        │   ├─► Market 订单
        │   └─► 附加止损单
        │
        └─► Lighter DEX
            ├─► 双限价入场
            └─► 多级止盈单
```

## ⚡ 快速开始

### 环境要求
- Python 3.11+
- Docker (可选)

### 本地运行

```bash
# 1. 克隆项目
git clone <repository>
cd tw168

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥

# 5. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 6. 健康检查
curl http://127.0.0.1:8000/health
```

### Docker 运行

```bash
# 构建并启动
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

## ⚙️ 配置说明

### 核心配置 (.env)

```bash
# Webhook 密钥
TV_WEBHOOK_SECRET=your_secret_here

# 交易所选择
EXCHANGE=okx  # 或 lighter

# 交易开关
TRADING_ENABLED=false  # false=模拟交易, true=实盘交易

# 交易对白名单
SYMBOL_ALLOWLIST=ETH-USDT-SWAP,BTC-USDT-SWAP

# 方向控制
ENABLE_LONG=true
ENABLE_SHORT=true
```

### OKX 配置

```bash
OKX_BASE_URL=https://www.okx.com
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_API_PASSPHRASE=your_passphrase
OKX_TD_MODE=cross  # cross=全仓, isolated=逐仓
```

### 风险管理

```bash
# 每笔交易风险金额 (推荐)
RISK_PER_TRADE_USDT=100

# 或使用固定数量 (不推荐)
ORDER_SZ=1

# 冷却时间 (秒)
COOLDOWN_SECONDS=120

# ZONE 信号有效期 (秒)
ZONE_TTL_SECONDS=900
```

### 止损配置

```bash
# 止损方法: lookback 或 pivot
STOP_METHOD=lookback

# Lookback 方法参数
STOP_LOOKBACK_BARS=50  # 回看 K 线数量
ATR_LEN=14             # ATR 周期
ATR_BUFFER_MULT=0.45   # ATR 缓冲倍数
MIN_BUFFER_BPS=3.5     # 最小缓冲 (基点)

# Pivot 方法参数
PIVOT_LEN=3            # 枢轴周期
```

### 止盈配置

```bash
# 启用止盈
TP_ENABLED=true

# 四级止盈阶梯 (总和应为 1.0)
TP1_R=1.5              # 1.5倍风险距离
TP1_PCT=0.70           # 平仓 70%

TP2_R=2.0
TP2_PCT=0.15           # 平仓 15%

TP3_R=2.5
TP3_PCT=0.10           # 平仓 10%

TP4_R=3.5
TP4_PCT=0.05           # 平仓 5%

# 移动止盈
TRAIL_START_R=2.0      # 达到 2R 后启动
TRAIL_BACK_R=0.75      # 回撤 0.75R 触发
```

## 📡 TradingView 信号

### ZONE 信号 (设置市场状态)

TradingView 告警 JSON 格式：

```json
{
  "secret": "your_secret_here",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m",
  "t": "{{time}}",
  "close": "{{close}}"
}
```

**zone 取值：**
- `OVERSOLD` - 超卖区域，准备做多
- `OVERBOUGHT` - 超买区域，准备做空
- `NEUTRAL` - 中性，不交易

### DIV 信号 (触发交易)

```json
{
  "secret": "your_secret_here",
  "type": "DIV",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m",
  "t": "{{time}}",
  "close": "{{close}}"
}
```

**交易逻辑：**
- 最新 ZONE = `OVERSOLD` → 开多单
- 最新 ZONE = `OVERBOUGHT` → 开空单

### 强制方向 (跳过 ZONE 检查)

```json
{
  "secret": "your_secret_here",
  "type": "DIV",
  "instId": "ETH-USDT-SWAP",
  "tf": "15m",
  "side": "buy",
  "close": "{{close}}"
}
```

## 📊 交易策略

### 止损计算方法

#### 1. Lookback 方法 (推荐)

基于最近 N 根 K 线的极值点 + ATR 缓冲：

```
做多止损 = min(最近50根K线低点) - ATR缓冲
做空止损 = max(最近50根K线高点) + ATR缓冲
```

**优点：** 自适应波动，计算简单
**适用：** 趋势跟踪策略

#### 2. Pivot 方法

基于价格结构的局部高低点：

```
做多止损 = 最近Pivot Low - ATR缓冲
做空止损 = 最近Pivot High + ATR缓冲
```

**优点：** 尊重价格结构，止损精确
**适用：** 震荡市场

### 止盈执行流程

```
假设：
- 入场价: 1000 USDT
- 止损价: 950 USDT
- R值: 50 USDT

止盈阶梯：
┌─────────┬──────────────┬──────────┬───────────┐
│ 阶段    │ 触发价格     │ 平仓动作 │ 剩余仓位  │
├─────────┼──────────────┼──────────┼───────────┤
│ 开仓    │ 1000         │ 做多 1.0 │ 1.00      │
│ TP1     │ 1075 (1.5R)  │ 平 70%   │ 0.30      │
│ TP2     │ 1100 (2.0R)  │ 平 15%   │ 0.15      │
│         │              │ +启动移动│           │
│ TP3     │ 1125 (2.5R)  │ 平 10%   │ 0.05      │
│ TP4     │ 1175 (3.5R)  │ 平 5%    │ 0.00      │
└─────────┴──────────────┴──────────┴───────────┘
```

## 📚 文档导航

### 核心文档
- [DESIGN.md](DESIGN.md) - 完整系统设计文档
- [CHANGELOG.md](CHANGELOG.md) - 版本更新日志
- [API.md](docs/API.md) - API 接口文档

### 部署运维
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - 部署指南
- [MONITORING.md](docs/MONITORING.md) - 监控指南
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - 故障排查

### 开发文档
- [DEVELOPMENT.md](docs/DEVELOPMENT.md) - 开发指南
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - 架构说明
- [TESTING.md](docs/TESTING.md) - 测试指南

### 特性文档
- [RSI_FILTER.md](docs/RSI_FILTER.md) - RSI 过滤器说明
- [TWO_LIMIT_ENTRY.md](docs/TWO_LIMIT_ENTRY.md) - 双限价入场
- [LIGHTER_DEX.md](docs/LIGHTER_DEX.md) - Lighter DEX 集成

## 🚀 部署指南

### 生产环境部署 (推荐)

```bash
# 1. SSH 登录服务器
ssh ubuntu@your-server-ip

# 2. 克隆项目
git clone <repository>
cd tw168

# 3. 配置环境
cp .env.example .env
nano .env  # 编辑配置

# 4. 使用 Docker 部署
docker compose up -d --build

# 5. 查看日志
docker compose logs -f

# 6. 验证服务
curl http://localhost:8000/health
```

### 使用部署脚本

```bash
# rsync 部署 (推荐)
./deploy_remote_rsync.sh

# 直接 SSH 部署
./deploy_updates.sh
```

### Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🛠️ 工具脚本

### 环境配置快捷工具

```bash
# 使用菜单式配置
python3 scripts/envmenu.py

# 或使用命令行参数
python3 scripts/envctl.py --tf 15m --w --hs
python3 scripts/envctl.py --disable-short
python3 scripts/envctl.py --no-patterns
```

### 监控脚本

```bash
# 启动监控
./monitor.sh

# 自动监控
./auto_monitor.sh

# 连续监控
./continuous_monitor.sh
```

### 测试脚本

```bash
# 测试完整交易流程
python3 test_full_flow.py

# 测试 Lighter 适配器
python3 test_lighter_adapter.py

# 测试 K 线缓存
python3 test_lighter_candles.py
```

## 📊 监控与日志

### 查看实时日志

```bash
# Docker 日志
docker compose logs -f

# 本地日志
tail -f tw168.log

# 查看错误
grep "ERROR" tw168.log | tail -20
```

### 健康检查

```bash
# 基础健康检查
curl http://localhost:8000/health

# 详细状态
curl http://localhost:8000/status
```

### Telegram 通知配置

参考 [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) 配置实时通知。

## 🔒 安全建议

1. **API 密钥安全**
   - 永远不要将 `.env` 提交到 Git
   - 使用只读 API 密钥测试
   - 限制 API 密钥的 IP 白名单

2. **Webhook 安全**
   - 使用强随机密钥
   - 定期轮换密钥
   - 启用 HTTPS

3. **风险控制**
   - 先在测试网测试
   - 使用 `TRADING_ENABLED=false` 模拟
   - 设置合理的 `RISK_PER_TRADE_USDT`
   - 启用 `SYMBOL_ALLOWLIST` 限制交易对

## ⚠️ 免责声明

本软件仅供学习和研究使用。加密货币交易存在高风险，可能导致资金损失。使用本软件进行实盘交易的所有风险由用户自行承担。

## 📝 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

- Issues: [GitHub Issues](https://github.com/your-repo/issues)
- Discussions: [GitHub Discussions](https://github.com/your-repo/discussions)

---

**最后更新:** 2025-01-01
**版本:** v2.0
**当前分支:** `claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF`
