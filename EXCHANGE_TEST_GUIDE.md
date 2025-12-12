# 🚀 PerpBot 统一交易所测试框架 - 使用指南

**最新更新**: 2025-12-12  
**版本**: 生产级 v2.0  
**支持交易所**: 12+ 个（可扩展）  
**测试模式**: 主网小额 + 可选交互式选择

---

## ⚡ 快速开始

### 默认：交互式选择
```bash
python test_exchanges.py
```

输出示例：
```
======================================================================
📋 Available Exchanges (按编号选择)
======================================================================
   1. okx             | ✅ 已配置      | DEMO   | ...
   2. binance         | ❌ 缺凭证      | 主网   | ...
   3. bitget          | ❌ 缺凭证      | 主网   | ...
   4. bybit           | ❌ 缺凭证      | 主网   | ...
   5. hyperliquid     | ✅ 已配置      | 主网   | ...
   6. paradex         | ✅ 已配置      | 主网   | ...
   7. extended        | ✅ 已配置      | 主网   | ...
   ...

输入交易所编号进行选择:
  例1: 1      → 只测试第1个交易所
  例2: 1 3 5  → 测试第1、3、5个交易所
  例3: 1-5    → 测试第1到5个交易所
  例4: all    → 测试所有交易所
  例5: cex    → 测试所有 CEX
  例6: dex    → 测试所有 DEX
  例7: q      → 退出

请选择 (或输入 q 退出): 
```

---

## 📋 使用方法

### 1️⃣ **交互式选择** (推荐)
```bash
# 默认进入交互模式，按提示输入编号
python test_exchanges.py

# 输入示例
请选择: 1 3 5      # 测试第 1、3、5 个交易所
请选择: 1-5        # 测试第 1-5 个交易所
请选择: all        # 测试所有
请选择: cex        # 只测 CEX
请选择: dex        # 只测 DEX
请选择: q          # 退出
```

### 2️⃣ **列表模式**
```bash
# 查看所有支持的交易所及其编号
python test_exchanges.py --list

# 输出：
#   1. okx
#   2. binance
#   3. bitget
#   4. bybit
#   5. hyperliquid
#   ...
```

### 3️⃣ **快速选择模式**
```bash
# 按名称指定交易所 (空格分隔)
python test_exchanges.py okx binance hyperliquid

# 快捷方式：所有 CEX
python test_exchanges.py --cex

# 快捷方式：所有 DEX
python test_exchanges.py --dex

# 快捷方式：所有交易所
python test_exchanges.py --all
```

### 4️⃣ **直接编号选择** (新增！)
```bash
# 使用 --select 进入编号选择模式
python test_exchanges.py --select

# 然后按提示输入编号
请选择: 2 5 8      # 测试第 2、5、8 个
```

---

## 🔧 高级选项

### 自定义交易对
```bash
# 不使用默认的 BTC/USDT，改用 ETH/USDT
python test_exchanges.py okx --symbol ETH/USDT

# 在交互模式中
请选择: 1 3
# → 自动使用 BTC/USDT
# 或添加 --symbol
python test_exchanges.py --symbol SOL/USDT
```

### 详细日志
```bash
# 显示所有调试信息
python test_exchanges.py okx --verbose

# 输出：
# 23:45:12 | okx             | DEBUG   | Connecting to OKX...
# 23:45:13 | okx             | INFO    | ✅ Connected (45ms)
```

### 输出 JSON 报告
```bash
# 将测试结果保存为 JSON
python test_exchanges.py okx binance --json-report report.json

# 生成的 report.json 包含：
# {
#   "test_time": "2025-12-12T23:45:12",
#   "duration_seconds": 5.23,
#   "total_exchanges": 2,
#   "passed_exchanges": 2,
#   "failed_exchanges": 0,
#   "metrics": [...]
# }
```

### 包含交易测试 (谨慎！)
```bash
# 执行小额实际交易测试
python test_exchanges.py okx --trading

# ⚠️ 警告：这会执行真实的买卖订单
# 仅在充分理解风险的情况下使用
```

---

## 📊 完整命令示例

### 场景 1: 快速验证 2 个交易所
```bash
# 方式 A：命令行指定
python test_exchanges.py okx hyperliquid

# 方式 B：交互选择
python test_exchanges.py
# → 请选择: 1 5  (即编号 1 和 5)

# 方式 C：直接编号
python test_exchanges.py --select
# → 请选择: 1 5
```

### 场景 2: 测试所有 CEX
```bash
# 快捷方式
python test_exchanges.py --cex

# 或手动指定
python test_exchanges.py okx binance bitget bybit
```

### 场景 3: 测试所有 DEX
```bash
# 快捷方式
python test_exchanges.py --dex

# 或手动指定
python test_exchanges.py hyperliquid paradex extended lighter edgex backpack grvt aster
```

### 场景 4: 批量测试 + 报告
```bash
# 测试所有交易所并生成报告
python test_exchanges.py --all --verbose --json-report full_report.json

# 生成的报告可用于：
# - 分析延迟
# - 对比成功率
# - 识别问题交易所
```

### 场景 5: 定时测试脚本
```bash
#!/bin/bash
# 每小时自动测试所有 CEX
while true; do
    echo "Running hourly exchange tests..."
    python test_exchanges.py --cex --json-report report_$(date +%Y%m%d_%H%M%S).json
    sleep 3600
done
```

---

## 🎯 支持的交易所列表

### CEX (中心化) - 4 个
1. **OKX** - Demo Trading 模式 (安全)
2. **Binance** - 主网小额测试
3. **BITGET** - 主网小额测试
4. **Bybit** - 主网小额测试

### DEX (去中心化) - 8+ 个
5. **Hyperliquid** - 主网 (可选凭证)
6. **Paradex** - Starknet DEX
7. **Extended** - Starknet DEX
8. **Lighter** - Ethereum L2 DEX
9. **EdgeX** - 多链 DEX
10. **Backpack** - Solana DEX
11. **GRVT** - Ethereum L2 DEX
12. **Aster** - Solana DEX

---

## 📝 输入格式详解

### 有效的输入示例

| 输入 | 含义 | 结果 |
|------|------|------|
| `1` | 第 1 个 | okx |
| `1 3` | 第 1 和 3 个 | okx, bitget |
| `1 3 5` | 第 1、3、5 个 | okx, bitget, hyperliquid |
| `1-5` | 第 1 到 5 个 | okx, binance, bitget, bybit, hyperliquid |
| `1,3,5` | 第 1、3、5 个 | okx, bitget, hyperliquid |
| `all` | 所有交易所 | 12 个全部 |
| `cex` | 仅 CEX | okx, binance, bitget, bybit |
| `dex` | 仅 DEX | hyperliquid, paradex, extended... |
| `q` | 退出 | 程序终止 |

### 无效的输入示例

| 输入 | 问题 |
|------|------|
| `0` | 编号从 1 开始 |
| `13` | 超出范围 (只有 12 个) |
| `abc` | 无效格式 |
| `1-3-5` | 多个范围符 |

---

## ✅ 测试覆盖范围

每个交易所测试包括：

```
1️⃣ 连接测试
   ✅ 验证 API 连接
   ⏱️ 测量连接延迟

2️⃣ 价格查询
   ✅ 获取 Bid/Ask 价格
   ✅ 验证数据有效性

3️⃣ 订单簿深度
   ✅ 获取深度订单簿
   ✅ 验证买卖档位

4️⃣ 账户余额
   ✅ 查询账户资产
   ✅ 显示前 3 项

5️⃣ 持仓信息
   ✅ 查询开放持仓
   ✅ 统计持仓数量

6️⃣ 性能指标 (可选 --trading)
   ✅ 小额下单/平仓
   ✅ 实际交易验证
```

---

## 📊 输出示例

### 正常输出
```
======================================================================
Testing OKX
======================================================================
1️⃣ Testing connection...
   ✅ Connected (45ms)
2️⃣ Testing price (BTC/USDT)...
   ✅ Price: 99000.50-99001.50 (120ms)
3️⃣ Testing orderbook (BTC/USDT)...
   ✅ Orderbook: 5 bids, 5 asks (95ms)
4️⃣ Testing account balances...
   ✅ Found 3 balances (180ms)
   - USDT: 1000.50 free
   - BTC: 0.01 free
   - ETH: 1.00 free
5️⃣ Testing positions...
   ✅ Found 2 positions (150ms)
✅ OKX test completed
```

### 失败输出
```
======================================================================
Testing BINANCE
======================================================================
1️⃣ Testing connection...
   ❌ Connection failed: Invalid API Key
⚠️ Missing env vars: BINANCE_API_SECRET
```

### 汇总报告
```
======================================================================
📊 TEST SUMMARY
======================================================================
Total: 3 exchanges
✅ Passed: 2
❌ Failed: 1
⏱️ Duration: 2.3s

Exchange        Connection  Price       Orderbook   Balance     Error
---
okx             ✅          ✅          ✅          ✅          
binance         ❌          -           -           -           Invalid API Key
hyperliquid     ✅          ✅          ✅          ✅          
```

---

## 🔐 安全建议

1. **使用只读 API Key**
   - 推荐仅开启 "读" 权限
   - 避免交易权限

2. **小额资金**
   - 首次测试：1-5 USDT
   - 生产测试：10-20 USDT

3. **IP 白名单**
   - 为 API Key 配置白名单
   - 限制请求来源

4. **定期更换**
   - 每月更换 API Key
   - 定期审计日志

5. **环保变量**
   - 不在代码中硬编码凭证
   - 使用 `.env` 文件管理
   - 确保 `.env` 在 `.gitignore`

---

## 🚨 常见问题

### Q: 如何选择 1、3、5 个交易所？
```bash
请选择: 1 3 5
# 或者
请选择: 1,3,5
```

### Q: 如何只测 CEX？
```bash
python test_exchanges.py --cex
# 或在交互模式中输入
请选择: cex
```

### Q: 如何退出交互模式？
```bash
请选择: q
```

### Q: JSON 报告在哪里？
```bash
python test_exchanges.py --all --json-report report.json
# 报告保存到当前目录的 report.json
```

### Q: 如何只测特定交易对？
```bash
python test_exchanges.py okx --symbol ETH/USDT
```

---

## 📞 支持

- **文档**: [EXCHANGES_CONFIG_GUIDE.md](EXCHANGES_CONFIG_GUIDE.md)
- **源代码**: [test_exchanges.py](test_exchanges.py)
- **配置**: [.env.example](.env.example)

---

**提示**: 首次使用建议运行 `python test_exchanges.py --list` 查看所有可用交易所！
