# 🔄 PerpBot v2.2 功能升级卡片

## 📋 概览

从 **v2.1** 升级到 **v2.2**，新增完整的交易功能（原来单个交易所脚本有的功能）。

## ✨ 新增功能速查

### 交互式菜单 (推荐)

```bash
python test_exchanges.py okx
```

**菜单选项:**
```
1️⃣  查询价格
2️⃣  查询订单簿
3️⃣  查询余额
4️⃣  查询持仓
5️⃣  下限价单 (买) ✨ 新增
6️⃣  下市价单 (买) ✨ 新增
7️⃣  撤销订单 ✨ 新增
8️⃣  平仓 ✨ 新增
9️⃣  切换交易对
0️⃣  返回
```

### 自动化模式

```bash
# 查询功能（原有）
python test_exchanges.py extended --auto-test

# 完整交易测试（新增）
python test_exchanges.py hyperliquid --auto-test --trading --trading-size 0.001
```

## 🎯 三种使用方式

| 方式 | 命令 | 适用场景 |
|:---|:---|:---|
| **交互式菜单** | `python test_exchanges.py okx` | 实时探索、手动测试 |
| **自动化查询** | `python test_exchanges.py okx --auto-test` | 批量验证、集成测试 |
| **自动化交易** | `python test_exchanges.py okx --auto-test --trading` | 功能验证、压力测试 |

## 🔍 详细命令示例

### 1. 交互式（推荐用法）

```bash
# 基础
python test_exchanges.py okx

# 指定交易对
python test_exchanges.py extended --symbol SUI/USD

# 启用详细日志
python test_exchanges.py hyperliquid --verbose
```

### 2. 自动化查询模式

```bash
# 单个交易所
python test_exchanges.py okx --auto-test

# 多个交易所
python test_exchanges.py okx extended paradex --auto-test

# 快速选择
python test_exchanges.py --cex --auto-test    # CEX
python test_exchanges.py --dex --auto-test    # DEX
python test_exchanges.py --all --auto-test    # 全部
```

### 3. 自动化交易测试（谨慎使用）

```bash
# 基础交易测试
python test_exchanges.py extended --auto-test --trading

# 自定义下单大小
python test_exchanges.py extended --auto-test --trading --trading-size 0.0001

# 指定交易对
python test_exchanges.py hyperliquid --auto-test --trading --symbol SOL/USD --trading-size 0.001

# 完整参数
python test_exchanges.py hyperliquid \
    --auto-test \
    --trading \
    --trading-size 0.001 \
    --symbol SOL/USD \
    --verbose \
    --json-report report.json
```

## 📊 交易测试流程

```
下单 (限价) 
   ↓
等待 0.5秒
   ↓
撤单 ✅
   ↓
下单 (市价) ✅
   ↓
等待 1秒
   ↓
平仓 ✅
```

## 🛡️ 安全参数

| 参数 | 默认值 | 建议值 | 说明 |
|:---|:---:|:---:|:---|
| `--trading-size` | 0.001 | 0.0001-0.001 | 下单大小 |
| 限价偏差 | 0.01 | 0.01-0.05 | 偏离价格的比例 |

## 📁 新增文件

- ✨ **test_exchanges.py** - 增强版（681 → 950+ 行）
- ✨ **ENHANCED_TEST_GUIDE.md** - 完整功能指南
- ✨ **demo_test_exchanges.sh** - 演示脚本

## 📚 文档导航

| 用途 | 文档 | 耗时 |
|:---|:---|:---|
| **新功能** | ENHANCED_TEST_GUIDE.md | 20 min |
| 快速开始 | QUICK_TEST_GUIDE.md | 5 min |
| 命令速查 | COMMAND_CHEATSHEET.md | 随时 |
| 完整学习 | EXCHANGE_TEST_GUIDE.md | 30 min |
| 详细演示 | EXCHANGE_TEST_DEMO.md | 60 min |
| 凭证配置 | CREDENTIALS_SETUP_GUIDE.md | 20 min |

## 🚀 快速开始

```bash
# 第 1 步: 查看交易所列表
python test_exchanges.py --list

# 第 2 步: 进入交互式菜单
python test_exchanges.py okx

# 第 3 步: 按菜单操作
请选择操作 (0-9): 1
# (查询价格，查看订单簿等)

请选择操作 (0-9): 5
# (下限价单，如果配置正确)

请选择操作 (0-9): 0
# (退出)
```

## ❓ 常见问题

**Q: 如何在菜单中下限价单？**
```
菜单选择: 5
输入下单数量: 0.001
输入限价偏差: 0.01
```

**Q: 如何运行完整的交易测试？**
```bash
python test_exchanges.py hyperliquid --auto-test --trading --trading-size 0.001
```

**Q: 交互式模式和自动化模式的区别？**
- **交互式**: 手动选择每个操作，实时看结果
- **自动化**: 自动运行预设的测试流程，生成报告

**Q: 如何导出测试结果？**
```bash
python test_exchanges.py okx --auto-test --json-report report.json
```

## ✅ 检查清单

```bash
# 验证安装
python test_exchanges.py --list          # ✅ 应该看到 13 个交易所

# 验证基础功能（无交易）
python test_exchanges.py okx --auto-test # ✅ 应该快速完成

# 验证交互式菜单
python test_exchanges.py extended        # ✅ 应该进入菜单

# 验证交易功能（谨慎！）
python test_exchanges.py hyperliquid \
    --auto-test \
    --trading \
    --trading-size 0.0001               # ⚠️ 这会执行真实交易
```

---

**版本**: v2.2  
**发布日期**: 2024-12-13  
**状态**: 生产级
