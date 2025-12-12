# 📦 归档文件说明

**日期**: 2024-12-12  
**版本**: v2.1  

本目录包含已弃用的测试文件和文档，这些文件已被新的统一框架替代。

---

## 📂 old_tests/ - 已归档的测试文件

### 单个交易所测试脚本 (13 个)
这些文件是针对单个交易所的测试脚本，现已被统一框架 `test_exchanges.py` 替代。

```
test_okx.py                    → 被 test_exchanges.py 替代
test_extended.py               → 被 test_exchanges.py 替代
test_paradex.py                → 被 test_exchanges.py 替代
test_hyperliquid.py            → 被 test_exchanges.py 替代
test_bitget.py                 → 被 test_exchanges.py 替代
test_backpack.py               → 被 test_exchanges.py 替代
test_edgex.py                  → 被 test_exchanges.py 替代
test_grvt.py                   → 被 test_exchanges.py 替代
test_lighter.py                → 被 test_exchanges.py 替代
test_aster.py                  → 被 test_exchanges.py 替代
test_close_position.py         → 已过时
test_position_aggregator.py    → 已过时
test_exchange_integration.py   → 被 test_exchanges.py 替代
```

### 旧的多交易所框架 (2 个)
```
test_all_exchanges.py          → 被 test_exchanges.py 替代（更优）
test_live_exchanges_simple.py  → 被 test_exchanges.py 替代（更优）
```

### WebSocket 和高级功能测试 (5 个)
这些文件包含 WebSocket 连接和高级交易功能的测试，现已整合到主框架或作为参考。

```
test_websocket_feeds.py        → 参考实现
test_ws_simple.py              → 参考实现
test_paradex_websocket.py      → 参考实现
test_paradex_limit_order.py    → 参考实现
test_tp_sl_complete.py         → 参考实现
```

### 其他测试 (2 个)
```
test_live_exchange_functions.py → 功能已集成
test_remaining_features.py      → 已过时
validate_perpbot_v2.py          → 已过时
```

---

## 📂 old_docs/ - 已归档的文档

### Testnet 相关文档 (已被主网框架替代)
```
QUICK_START_TESTNET.md         → 使用 QUICK_TEST_GUIDE.md 替代
TESTNET_CONNECTION_GUIDE.md    → 使用 EXCHANGE_TEST_GUIDE.md 替代
TESTNET_DOCS_INDEX.md          → 整合到主文档中
TESTNET_READY_REPORT.md        → 已过时
```

**原因**: 项目现使用主网进行小额测试，不再需要 Testnet。

### 过时的测试计划 (已完成或被统一框架替代)
```
EXTENDED_TEST_PLAN.md          → 已完成，功能已集成
LIGHTER_TEST_PLAN.md           → 已完成，功能已集成
MANUAL_TESTING_GUIDE.md        → 已过时，使用自动化框架
EXCHANGE_TESTING_STATUS.md     → 已过时，使用 --list 命令查看
EXCHANGE_MOCK_MODE_SUMMARY.md  → 已过时，使用主网框架
UNIT_TESTING_SUMMARY.md        → 已过时，测试已集成
PERFORMANCE_TESTING_SUMMARY.md → 已过时，可通过 --verbose 查看
PARADEX_TEST_SUMMARY.md        → 已过时，使用统一框架
```

---

## ✅ 新的统一框架

### 核心文件
- **test_exchanges.py** - 支持 13+ 个交易所的统一测试框架
- **setup_credentials.sh** - 交互式凭证配置脚本

### 核心文档
| 文档 | 用途 |
|------|------|
| FRAMEWORK_README.md | 框架概览 |
| QUICK_TEST_GUIDE.md | 5 分钟快速开始 |
| EXCHANGE_TEST_GUIDE.md | 完整使用指南 |
| EXCHANGE_TEST_DEMO.md | 详细演示和场景 |
| COMMAND_CHEATSHEET.md | 命令速查表 |
| CREDENTIALS_QUICK_START.md | 凭证配置快速开始 |
| CREDENTIALS_SETUP_GUIDE.md | 凭证详细指南 |
| EXCHANGES_CONFIG_GUIDE.md | 交易所配置详解 |
| PROJECT_COMPLETION_SUMMARY.md | 项目总结 |
| FINAL_PROJECT_REPORT.md | 最终报告 |
| EXCHANGE_TESTING_README.md | 测试框架 README |

---

## 🚀 迁移指南

### 从旧的单个交易所测试迁移到新框架

**旧方式**:
```bash
python test_okx.py
python test_binance.py
python test_hyperliquid.py
```

**新方式** (推荐):
```bash
# 交互式选择
python test_exchanges.py
# 输入: 1 2 5

# 或直接指定
python test_exchanges.py okx binance hyperliquid

# 或快捷方式
python test_exchanges.py --cex  # 所有 CEX
python test_exchanges.py --dex  # 所有 DEX
```

### 使用新框架的优势

✅ **单一脚本** - 不再需要维护多个脚本  
✅ **统一接口** - 所有交易所使用一致的 API  
✅ **交互式选择** - 灵活的选择方式  
✅ **配置工具** - 统一的凭证管理  
✅ **详细文档** - 完整的使用指南  
✅ **更快速** - 执行更高效  
✅ **更可靠** - 更好的错误处理  

---

## 📊 版本演进

```
v1.0 - 多个单交易所脚本
  ├─ test_okx.py, test_binance.py, ...
  └─ 过时（旧框架）

v2.0 - 统一框架初版
  ├─ test_exchanges.py（12 个交易所）
  └─ 核心文档

v2.1 - 添加凭证管理 & 归档旧文件（当前版本）
  ├─ test_exchanges.py（13 个交易所）
  ├─ setup_credentials.sh（交互式配置）
  ├─ CREDENTIALS_*.md（详细指南）
  └─ archive/（旧文件归档）
```

---

## 🔍 何时查看归档文件

✅ **参考 WebSocket 实现** - 查看 `test_paradex_websocket.py`  
✅ **了解历史** - 查看 `EXCHANGE_TESTING_STATUS.md`  
✅ **研究单交易所实现** - 查看对应的 `test_*.py`  
✅ **了解项目演进** - 查看此目录  

---

## ⚠️ 注意事项

- 这些归档文件仅供参考
- **不要再使用**这些旧的单个测试脚本
- 使用新的统一框架: `test_exchanges.py`
- 所有功能都已在新框架中实现
- 有任何问题，查看新的文档文件

---

## 📚 快速导航

需要帮助？按推荐顺序读：

1. **[../QUICK_TEST_GUIDE.md](../QUICK_TEST_GUIDE.md)** - 5 分钟快速开始
2. **[../EXCHANGE_TEST_GUIDE.md](../EXCHANGE_TEST_GUIDE.md)** - 完整指南
3. **[../CREDENTIALS_QUICK_START.md](../CREDENTIALS_QUICK_START.md)** - 凭证配置
4. **[../COMMAND_CHEATSHEET.md](../COMMAND_CHEATSHEET.md)** - 命令速查

---

**状态**: ✅ 已归档  
**更新日期**: 2024-12-12  
**版本**: v2.1
