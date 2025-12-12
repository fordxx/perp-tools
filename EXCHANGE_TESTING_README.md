# 🚀 统一交易所测试框架 - README

## 概述

**PerpBot Unified Exchange Testing Framework** 是一个生产级的多交易所测试工具，支持 12+ 个交易所（4 CEX + 8 DEX），提供：

✅ **统一接口** - 所有交易所使用一致的 API  
✅ **交互式选择** - 灵活选择要测试的交易所  
✅ **无需 Testnet** - 直接主网进行小额测试  
✅ **完整诊断** - 详细的连接、价格、订单簿、余额、持仓检查  
✅ **JSON 报告** - 机读格式的完整测试报告  
✅ **零重复** - 统一框架，不再维护多个测试脚本  

---

## ⚡ 快速开始

### 1️⃣ 查看支持的交易所
```bash
python test_exchanges.py --list
```

### 2️⃣ 运行测试
```bash
# 交互式选择（推荐）
python test_exchanges.py

# 直接指定
python test_exchanges.py hyperliquid paradex extended

# 快捷方式
python test_exchanges.py --cex      # 所有 CEX
python test_exchanges.py --dex      # 所有 DEX
python test_exchanges.py --all      # 全部
```

### 3️⃣ 查看结果
```
✅ hyperliquid test completed
✅ paradex test completed
✅ extended test completed

📊 TEST SUMMARY
Total: 3 exchanges
✅ Passed: 3
❌ Failed: 0
⏱️ Duration: 2.3s
```

---

## 📋 支持的交易所

### CEX (中心化) - 4 个
```
1. OKX       - Demo Trading (安全测试)
2. Binance   - 世界最大现货交易所
3. Bitget    - 创新交易所
4. Bybit     - 衍生品交易所
```

### DEX (去中心化) - 8 个
```
5. Hyperliquid   ✅ 已配置
6. Paradex       ✅ 已配置
7. Extended      ✅ 已配置
8. Lighter       - Ethereum L2
9. EdgeX         - 多链 DEX
10. Backpack     - Solana DEX
11. GRVT         - Ethereum L2 DEX
12. Aster        - Solana DEX
```

---

## 🎯 使用示例

### 基本用法
```bash
# 交互式（最简单）
python test_exchanges.py

# 输入示例：
请选择 (或输入 q 退出): 5 6 7
# → 测试 hyperliquid, paradex, extended
```

### 命令行用法
```bash
# 按名称指定
python test_exchanges.py okx binance hyperliquid

# 按编号范围
python test_exchanges.py --select 1-5

# 快捷方式
python test_exchanges.py --cex   # 仅 CEX
python test_exchanges.py --dex   # 仅 DEX
```

### 高级用法
```bash
# 自定义交易对
python test_exchanges.py okx --symbol ETH/USDT

# 详细日志
python test_exchanges.py --verbose

# 导出报告
python test_exchanges.py --all --json-report report.json

# 实际交易测试（谨慎）
python test_exchanges.py okx --trading
```

---

## 📊 测试项目

每个交易所包括以下测试：

```
1️⃣ 连接测试    - 验证 API 连接，测量延迟
2️⃣ 价格查询    - 获取 Bid/Ask 价格
3️⃣ 订单簿      - 查询深度订单簿
4️⃣ 账户余额    - 查询账户资产
5️⃣ 持仓信息    - 查询开放持仓
```

### 示例输出
```
✅ Connected (45ms)
✅ Price: 99000.50-99001.50 (120ms)
✅ Orderbook: 5 bids, 5 asks (95ms)
✅ Found 3 balances (180ms)
✅ Found 2 positions (150ms)
```

---

## 🔧 配置凭证

### 方式 1: 编辑 .env 文件
```bash
nano .env
```

添加凭证：
```env
# OKX
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_API_PASSPHRASE=your_passphrase

# Binance
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

### 方式 2: 使用环境变量
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_API_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

### 方式 3: 一行命令
```bash
OKX_API_KEY="key" OKX_API_SECRET="secret" python test_exchanges.py okx
```

---

## 📚 完整文档

| 文档 | 内容 |
|------|------|
| [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) | 5 分钟快速开始 |
| [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md) | 完整使用指南 |
| [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md) | 详细演示和场景 |
| [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md) | 命令速查表 |
| [PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md) | 项目完成总结 |
| [EXCHANGES_CONFIG_GUIDE.md](EXCHANGES_CONFIG_GUIDE.md) | 配置详解 |

---

## 💡 常见用法

```bash
# 列表所有交易所
python test_exchanges.py --list

# 快速验证 3 个已配置的交易所
python test_exchanges.py hyperliquid paradex extended

# 配置新凭证后测试
export BINANCE_API_KEY="..." BINANCE_API_SECRET="..."
python test_exchanges.py binance

# 完整测试 + 报告
python test_exchanges.py --all --verbose --json-report report.json

# 定时监控（每 5 分钟一次）
while true; do
    python test_exchanges.py --cex --json-report log_$(date +%s).json
    sleep 300
done
```

---

## 🔐 安全建议

- ✅ 使用 `.env` 文件存储凭证（不要提交到 Git）
- ✅ 使用只读 API Key
- ✅ 设置 IP 白名单
- ✅ 使用小额资金测试（1-5 USDT）
- ✅ 定期轮换凭证

---

## 📊 项目架构

```
test_exchanges.py (主文件)
├── ExchangeConfig (配置)
│   └── 12 个交易所定义
├── TestMetrics (指标)
│   └── 5 项测试结果
├── UnifiedExchangeTester (测试类)
│   ├── test_connection()
│   ├── test_price()
│   ├── test_orderbook()
│   ├── test_balance()
│   └── test_positions()
└── interactive_select_exchanges() (交互模式)
    └── 灵活的输入格式支持
```

---

## ✨ 功能亮点

### 1. 交互式选择
支持多种输入格式：
- 单个：`1`
- 多个：`1 3 5`
- 范围：`1-5`
- 混合：`1 3-5 8`
- 快捷：`all`, `cex`, `dex`

### 2. 零重复代码
- 统一框架支持 12+ 交易所
- 一次配置，处处使用
- 易于扩展新交易所

### 3. 详细诊断
- 连接验证
- 延迟测量
- 错误日志
- 配置检查

### 4. JSON 报告
- 机读格式
- 完整的测试指标
- 易于自动化分析

---

## 🐛 故障排查

### 缺少模块
```
Failed to import: No module named 'httpx'
```

**解决：** `pip install -r requirements.txt`

### 缺少凭证
```
⚠️ Missing env vars: OKX_API_KEY
```

**解决：** 添加凭证到 `.env` 文件

### 连接超时
```
Connection timeout
```

**解决：** 检查网络、API 端点、IP 白名单

---

## 🎓 学习路径

1. **新手** → 读 [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md)
2. **中级** → 读 [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md)
3. **高级** → 读 [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md)
4. **参考** → 用 [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md)

---

## 🚀 下一步

1. ✅ 运行 `python test_exchanges.py --list` 查看所有交易所
2. ✅ 运行 `python test_exchanges.py hyperliquid` 测试已配置的交易所
3. ✅ 编辑 `.env` 添加新凭证
4. ✅ 运行 `python test_exchanges.py okx` 测试新交易所

---

## 📞 支持

- **快速问题** → 查 [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md)
- **详细问题** → 查 [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md)
- **复杂场景** → 查 [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md)

---

**状态**: ✅ 生产级  
**版本**: 2.0  
**支持交易所**: 12+  
**最后更新**: 2024-12-12

---

### 快速链接
- [test_exchanges.py](test_exchanges.py) - 核心脚本
- [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) - 5 分钟快速开始
- [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md) - 命令速查
- [.env.example](.env.example) - 凭证配置示例

**Ready to test?** Run: `python test_exchanges.py`
