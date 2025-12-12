# 🚀 PerpBot 统一交易所测试框架

> 支持 12+ 个交易所的生产级多交易所测试工具

## ⚡ 快速开始（30 秒）

```bash
# 1. 查看支持的交易所
python test_exchanges.py --list

# 2. 运行测试
python test_exchanges.py
# 输入: 5 6 7
# → 完成！

# 3. 查看结果
# ✅ 3 个交易所测试通过
```

## 📚 文档导航

**首选文档**（按推荐顺序）：

1. **🚀 [快速入门](QUICK_TEST_GUIDE.md)** (5 分钟)
   - 最快速的使用方法
   - 基本命令示例

2. **📖 [完整指南](EXCHANGE_TEST_GUIDE.md)** (30 分钟)
   - 所有功能详解
   - 高级选项说明

3. **🎬 [详细演示](EXCHANGE_TEST_DEMO.md)** (60 分钟)
   - 多种使用场景
   - 常见问题解答

4. **⚡ [命令速查](COMMAND_CHEATSHEET.md)** (随时查看)
   - 快速参考
   - 复制即用命令

5. **📊 [项目总结](FINAL_PROJECT_REPORT.md)** (技术深度)
   - 完整的项目报告
   - 技术细节和架构

## 🎯 常见任务

### 测试特定交易所
```bash
python test_exchanges.py hyperliquid paradex extended
```

### 测试所有 CEX（中心化）
```bash
python test_exchanges.py --cex
```

### 测试所有 DEX（去中心化）
```bash
python test_exchanges.py --dex
```

### 交互式选择（推荐）
```bash
python test_exchanges.py
# 输入: 1-5      # 选第 1-5 个
# 输入: all      # 选全部
# 输入: q        # 退出
```

### 详细输出 + JSON 报告
```bash
python test_exchanges.py --all --verbose --json-report report.json
```

## 🌍 支持的交易所

| 编号 | CEX / DEX | 交易所 | 状态 |
|------|-----------|--------|------|
| 1-4 | CEX | OKX, Binance, Bitget, Bybit | ❌ 需凭证 |
| 5 | DEX | Hyperliquid | ✅ 已配置 |
| 6 | DEX | Paradex | ✅ 已配置 |
| 7 | DEX | Extended | ✅ 已配置 |
| 8-12 | DEX | Lighter, EdgeX, Backpack, GRVT, Aster | ❌ 需凭证 |

## 🔧 配置凭证

### 添加 OKX
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_API_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

### 编辑 .env 文件
```bash
nano .env
# 添加凭证后保存
python test_exchanges.py okx
```

## 💡 你可能想要...

- **快速测试** → 运行 `python test_exchanges.py --list`
- **学习如何使用** → 读 [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md)
- **查看所有命令** → 查 [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md)
- **看具体例子** → 看 [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md)
- **了解项目** → 读 [FINAL_PROJECT_REPORT.md](FINAL_PROJECT_REPORT.md)
- **配置交易所** → 看 [EXCHANGES_CONFIG_GUIDE.md](EXCHANGES_CONFIG_GUIDE.md)

## ✨ 核心特性

✅ **统一接口** - 所有交易所一致的 API  
✅ **交互式选择** - 灵活的数字/范围/快捷方式输入  
✅ **无需 Testnet** - 直接主网小额测试  
✅ **完整诊断** - 连接、价格、订单簿、余额、持仓  
✅ **JSON 报告** - 机读格式的完整报告  
✅ **零重复** - 单一框架支持所有交易所  
✅ **文档完整** - 6 份详细指南  
✅ **生产级** - 完整的错误处理和验证  

## 📊 项目统计

```
支持交易所:  12 个 (4 CEX + 8 DEX)
文档:        6 份
核心代码:    681 行
代码质量:    无重复、模块化、可扩展
生产就绪:    ✅ 100%
```

## 🚀 下一步

1. 运行 `python test_exchanges.py --list` 查看所有交易所
2. 读 [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) 了解基本用法
3. 配置你需要的交易所凭证
4. 运行测试并查看结果

## 📞 获取帮助

| 问题 | 查看 |
|------|------|
| 怎么快速开始？ | [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md) |
| 所有命令是什么？ | [COMMAND_CHEATSHEET.md](COMMAND_CHEATSHEET.md) |
| 具体怎么用？ | [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md) |
| 有什么例子吗？ | [EXCHANGE_TEST_DEMO.md](EXCHANGE_TEST_DEMO.md) |
| 项目细节？ | [FINAL_PROJECT_REPORT.md](FINAL_PROJECT_REPORT.md) |

## 🎓 学习路径

```
新手 → [QUICK_TEST_GUIDE.md] → [EXCHANGE_TEST_GUIDE.md]
         ↓
    [COMMAND_CHEATSHEET.md] (随时查看)
         ↓
    [EXCHANGE_TEST_DEMO.md] (看具体例子)
         ↓
    [FINAL_PROJECT_REPORT.md] (深度学习)
```

---

**状态**: ✅ 生产级完成  
**版本**: 2.0  
**最后更新**: 2024-12-12  

**Ready?** Run: `python test_exchanges.py` 🚀
