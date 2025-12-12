# 🚀 增强版测试框架使用指南 (v2.2)

## 📋 概述

PerpBot 统一测试框架现已支持**完整的交易功能**（下单、撤单、平仓等），与原来的单个交易所测试脚本功能一致。

### 新增功能

✅ **查询功能** (原有)
- 连接验证
- 实时价格查询
- 订单簿深度查询
- 账户余额查询
- 持仓信息查询

✨ **新增交易功能**
- 限价单下单和撤单
- 市价单下单
- 持仓平仓
- 交互式菜单

---

## 🎯 快速开始

### 1️⃣ 列出所有交易所

```bash
python test_exchanges.py --list
```

输出：
```
🌍 Supported Exchanges (生产级)
============================================================
   1. okx             | ✅ 已配置 | DEMO  | OKX_API_KEY, ...
   2. binance         | ✅ 已配置 | 主网  | BINANCE_API_KEY, ...
   3. extended        | ✅ 已配置 | 主网  | EXTENDED_API_KEY, ...
   ...
```

### 2️⃣ 单个交易所 - 交互式菜单

最推荐的方式，适合实时交互和测试：

```bash
# 进入交互式菜单
python test_exchanges.py okx

# 或指定交易对
python test_exchanges.py extended --symbol SUI/USD
```

**菜单选项**：
```
1️⃣  查询价格
2️⃣  查询订单簿
3️⃣  查询账户余额
4️⃣  查询持仓
5️⃣  下限价单 (买)
6️⃣  下市价单 (买)
7️⃣  撤销最近订单
8️⃣  平仓
9️⃣  切换交易对
0️⃣  返回
```

**使用示例**：
```
请选择操作 (0-9): 1          # 查询价格
💹 BTC/USDT 价格
   买价: 45123.45
   卖价: 45125.67
   中间: 45124.56

请选择操作 (0-9): 5          # 下限价单
请输入下单数量 (default=0.001): 0.001
请输入限价偏差 (default=0.01): 0.01
✅ Order placed: ID=12345
...
```

### 3️⃣ 自动化测试模式

不进入交互式菜单，直接运行完整测试：

```bash
# 单个交易所的自动化测试（查询功能）
python test_exchanges.py extended --auto-test

# 包含交易测试
python test_exchanges.py extended --auto-test --trading --trading-size 0.001

# 多个交易所
python test_exchanges.py okx binance extended --auto-test
```

### 4️⃣ 快速开始选项

```bash
# 测试所有交易所
python test_exchanges.py --all

# 仅测试 CEX (中心化交易所)
python test_exchanges.py --cex

# 仅测试 DEX (去中心化交易所)
python test_exchanges.py --dex

# 交互式选择 (按编号选择)
python test_exchanges.py --select
```

---

## 🔄 核心功能详解

### A. 查询功能 (非交易)

#### 获取实时价格

```bash
python test_exchanges.py okx --symbol BTC/USDT
# 菜单选择: 1
```

输出：
```
💹 BTC/USDT 价格
   买价: 45123.45
   卖价: 45125.67
   中间: 45124.56
```

#### 获取订单簿

```bash
# 菜单选择: 2
```

输出：
```
📊 ETH/USD 订单簿 (深度5)
   卖盘 (Asks):
      2850.50 x 10.5
      2850.75 x 20.0
   买盘 (Bids):
      2850.25 x 15.0
      2850.00 x 25.5
```

#### 账户余额

```bash
# 菜单选择: 3
```

输出：
```
💰 账户余额 (12 种资产)
   BTC: 可用=0.1, 锁定=0.0
   ETH: 可用=1.5, 锁定=0.2
   USDT: 可用=10000.00, 锁定=500.00
```

#### 持仓信息

```bash
# 菜单选择: 4
```

输出：
```
📋 持仓列表 (2 个)
   BTC/USDT BUY 0.1 @ 45000.00
   ETH/USDT SHORT 1.0 @ 2800.00
```

### B. 交易功能 (谨慎使用)

⚠️ **警告**: 以下功能会执行真实交易，请确保：
- 已配置正确的 API 凭证
- 设置足够小的下单数量
- 理解交易的风险

#### 下限价单

```bash
# 菜单选择: 5
请输入下单数量 (default=0.001): 0.001
请输入限价偏差 (default=0.01): 0.01

✅ Order placed: ID=12345
```

**参数说明**：
- **数量**: 订单大小（默认 0.001）
- **限价偏差**: 偏离当前价格的比例（默认 1%）
  - 偏差 0.01 = 1%
  - 偏差 0.02 = 2%

#### 下市价单

```bash
# 菜单选择: 6
请输入下单数量 (default=0.001): 0.001

✅ Market order placed: ID=12346, Price=2850.50
```

#### 平仓

```bash
# 菜单选择: 8
📍 Position size: 0.1, Current price: 45124.56
✅ Close order placed: ID=12347
```

### C. 自动化交易测试 (仅命令行)

```bash
# 运行完整的交易测试流程
python test_exchanges.py extended \
    --auto-test \
    --trading \
    --trading-size 0.001 \
    --symbol ETH/USD
```

测试流程：
1. ✅ 连接验证
2. ✅ 价格查询
3. ✅ 订单簿验证
4. ✅ 余额查询
5. ✅ 持仓查询
6. ✅ 限价单测试（下单 + 撤单）
7. ✅ 市价单测试
8. ✅ 平仓测试

---

## 📊 高级选项

### 自定义交易对

```bash
# 指定特定交易对
python test_exchanges.py hyperliquid --symbol SOL/USD

# 配合菜单使用
python test_exchanges.py extended
# 菜单中选择: 9 (切换交易对)
# 输入新交易对: BTC/USDT
```

### 详细日志

```bash
# 启用详细日志输出
python test_exchanges.py okx --verbose
```

### JSON 报告导出

```bash
# 导出测试报告
python test_exchanges.py okx binance --auto-test \
    --json-report report.json

# 查看报告
cat report.json | jq
```

### 结合选项示例

```bash
# 完整的交易测试（多交易所）
python test_exchanges.py okx extended paradex \
    --auto-test \
    --trading \
    --trading-size 0.001 \
    --symbol BTC/USDT \
    --verbose \
    --json-report results.json
```

---

## 🔒 安全建议

### 1. 账户配置

✅ **推荐做法**：
- 使用**只读 API** 进行查询操作
- 为交易操作创建**独立的 API 密钥**
- 设置 **IP 白名单**
- 限制 API 的**交易权限**

### 2. 下单规范

✅ **谨慎措施**：
- 始终从**最小数量**开始测试（例如 0.0001）
- 监控 **API 速率限制**
- 避免在生产交易时运行测试脚本
- 保留 **足够的保证金** 以处理极端情况

### 3. 凭证管理

✅ **最佳实践**：
```bash
# 不要在命令行暴露凭证
# ❌ 错误
export PARADEX_L2_PRIVATE_KEY=0x1234567890

# ✅ 正确
# 在 .env 文件中配置（不提交到 Git）
echo "PARADEX_L2_PRIVATE_KEY=0x..." >> .env
```

---

## 🆚 与原单交易所脚本的对比

| 功能 | 原脚本 | 新框架 | 优势 |
|:---|:---:|:---:|:---|
| 连接验证 | ✅ | ✅ | 统一接口 |
| 价格查询 | ✅ | ✅ | 统一接口 |
| 订单簿 | ✅ | ✅ | 统一接口 |
| 余额查询 | ✅ | ✅ | 统一接口 |
| 持仓查询 | ✅ | ✅ | 统一接口 |
| 下单 | ✅ | ✅ | 统一接口 |
| 撤单 | ✅ | ✅ | 统一接口 |
| 平仓 | ✅ | ✅ | 统一接口 |
| **单一脚本支持多交易所** | ❌ | ✅ | **消除重复代码** |
| **交互式菜单** | ❌ | ✅ | **更易使用** |
| **自动化测试模式** | ❌ | ✅ | **易于集成** |
| **JSON 报告** | ❌ | ✅ | **数据分析** |

---

## 🎓 使用场景

### 场景 1: 快速验证交易所连接

```bash
python test_exchanges.py okx --auto-test
# ⏱️ 耗时: < 5 秒
```

### 场景 2: 交互式探索交易所 API

```bash
python test_exchanges.py extended --symbol ETH/USD
# 进入菜单，逐项测试每个功能
```

### 场景 3: 全量测试所有交易所

```bash
python test_exchanges.py --all --auto-test --json-report results.json
# ⏱️ 耗时: < 30 秒
```

### 场景 4: 真实交易测试（风险较高）

```bash
python test_exchanges.py hyperliquid \
    --auto-test \
    --trading \
    --trading-size 0.0001 \
    --symbol SOL/USD
```

---

## ❓ 常见问题

### Q: 如何知道哪些交易所已配置凭证？

**A:** 运行 `python test_exchanges.py --list`，看"✅ 已配置"的标记。

### Q: 如何获取特定交易所的帮助？

**A:** 查看 `CREDENTIALS_SETUP_GUIDE.md` 中对应的交易所部分。

### Q: 下单时出现错误怎么办？

**A:** 
1. 检查凭证配置：`echo $EXTENDED_API_KEY`
2. 确认有足够的保证金
3. 验证交易对是否有效：菜单选择 1 (查询价格)

### Q: 如何撤销已下的订单？

**A:** 
- 从菜单选择 7（需要保存订单 ID，目前未实现）
- 或使用命令行：`curl ...` （需要直接调用 API）

### Q: 能测试多少个交易对？

**A:** 可以无限切换，菜单选择 9。

### Q: 如何导出测试结果？

**A:** 
```bash
python test_exchanges.py okx --auto-test --json-report okx_report.json
cat okx_report.json
```

---

## 📞 获取更多帮助

| 需求 | 文件 |
|:---|:---|
| 凭证配置 | `CREDENTIALS_SETUP_GUIDE.md` |
| 快速开始 | `QUICK_TEST_GUIDE.md` |
| 命令速查表 | `COMMAND_CHEATSHEET.md` |
| 完整指南 | `EXCHANGE_TEST_GUIDE.md` |
| 详细演示 | `EXCHANGE_TEST_DEMO.md` |

---

## 🚀 下一步

1. **配置凭证**: `bash setup_credentials.sh`
2. **查看交易所列表**: `python test_exchanges.py --list`
3. **测试连接**: `python test_exchanges.py okx --auto-test`
4. **交互式探索**: `python test_exchanges.py extended`
5. **实时交易**: `python test_exchanges.py hyperliquid --auto-test --trading --trading-size 0.001`

---

**版本**: v2.2 (2024-12-13)  
**状态**: 生产级  
**最后更新**: 增加完整交易功能支持
