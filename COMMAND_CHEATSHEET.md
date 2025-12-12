# 🚀 快速参考卡 - 命令速查表

## 常用命令（复制即用）

### 查看列表
```bash
python test_exchanges.py --list
```

### 交互式选择（推荐）
```bash
python test_exchanges.py
# 输入: 5 6 7  → hyperliquid, paradex, extended
# 输入: all    → 所有交易所
# 输入: cex    → 仅 CEX
# 输入: dex    → 仅 DEX
# 输入: q      → 退出
```

### 快捷方式
```bash
# 所有交易所
python test_exchanges.py --all

# 仅 CEX
python test_exchanges.py --cex

# 仅 DEX
python test_exchanges.py --dex

# 特定交易所
python test_exchanges.py hyperliquid paradex extended
python test_exchanges.py okx binance
```

### 详细输出
```bash
python test_exchanges.py --verbose
python test_exchanges.py --all --verbose
```

### 生成报告
```bash
python test_exchanges.py --all --json-report report.json
```

### 自定义交易对
```bash
python test_exchanges.py okx --symbol ETH/USDT
python test_exchanges.py --cex --symbol SOL/USDT
```

---

## 配置凭证

### 添加 OKX
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_API_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

### 添加 Binance
```bash
export BINANCE_API_KEY="your_key"
export BINANCE_API_SECRET="your_secret"

python test_exchanges.py binance
```

### 编辑 .env 文件
```bash
nano .env
# 添加凭证后保存
python test_exchanges.py okx
```

---

## 输入格式

| 输入 | 意思 | 例子 |
|------|------|------|
| `1` | 单个 | 选第 1 个 (okx) |
| `1 3 5` | 多个 | 选第 1、3、5 个 |
| `1-5` | 范围 | 选第 1-5 个 |
| `all` | 全部 | 选全部 12 个 |
| `cex` | 仅 CEX | 选第 1-4 个 |
| `dex` | 仅 DEX | 选第 5-12 个 |
| `q` | 退出 | 结束程序 |

---

## 交易所编号

```
CEX (中心化):
  1. okx
  2. binance
  3. bitget
  4. bybit

DEX (去中心化):
  5. hyperliquid     ✅ 已配置
  6. paradex         ✅ 已配置
  7. extended        ✅ 已配置
  8. lighter
  9. edgex
  10. backpack
  11. grvt
  12. aster
```

---

## 实际例子

```bash
# 快速验证
python test_exchanges.py hyperliquid

# 选择第 2、3、5 个
python test_exchanges.py
# 输入: 2 3 5

# 测试所有 CEX
python test_exchanges.py --cex

# 完整测试 + 报告
python test_exchanges.py --all --verbose --json-report full.json

# 监控脚本
while true; do
    python test_exchanges.py --cex --json-report log_$(date +%s).json
    sleep 300
done
```

---

## 文档速链

| 文档 | 用途 |
|------|------|
| [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) | 5 分钟快速开始 |
| [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md) | 完整使用指南 |
| [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md) | 详细演示和场景 |
| [PROJECT_COMPLETION_SUMMARY.md](PROJECT_COMPLETION_SUMMARY.md) | 项目完成总结 |

---

**💡 提示：** 首次使用推荐按顺序读：快速指南 → 完整指南 → 演示文档
