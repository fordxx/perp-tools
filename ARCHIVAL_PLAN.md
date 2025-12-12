# 📦 文件归档计划

**日期**: 2024-12-12  
**版本**: v2.1  

## 🔍 归档分析

### 老旧测试文件（需要归档）

这些文件是在统一框架 `test_exchanges.py` 之前创建的，现在已被统一框架取代：

**单个交易所测试脚本** (13 个)：
- test_okx.py
- test_extended.py
- test_paradex.py
- test_hyperliquid.py
- test_bitget.py
- test_backpack.py
- test_edgex.py
- test_grvt.py
- test_lighter.py
- test_aster.py
- test_close_position.py
- test_position_aggregator.py
- test_exchange_integration.py

**旧的多交易所框架** (2 个)：
- test_all_exchanges.py（被 test_exchanges.py 替代）
- test_live_exchanges_simple.py（被 test_exchanges.py 替代）

**WebSocket 和高级功能测试** (5 个)：
- test_websocket_feeds.py
- test_ws_simple.py
- test_paradex_websocket.py
- test_paradex_limit_order.py
- test_tp_sl_complete.py

**其他测试** (4 个)：
- test_live_exchange_functions.py
- test_remaining_features.py
- validate_perpbot_v2.py
- test_exchange_interaction.py

---

### 老旧文档文件（需要归档）

**Testnet 相关文档** (被主网框架替代)：
- QUICK_START_TESTNET.md
- TESTNET_CONNECTION_GUIDE.md
- TESTNET_DOCS_INDEX.md
- TESTNET_READY_REPORT.md

**过时的测试计划** (已完成或被统一框架替代)：
- EXTENDED_TEST_PLAN.md
- LIGHTER_TEST_PLAN.md
- MANUAL_TESTING_GUIDE.md
- EXCHANGE_TESTING_STATUS.md
- EXCHANGE_MOCK_MODE_SUMMARY.md
- UNIT_TESTING_SUMMARY.md
- PERFORMANCE_TESTING_SUMMARY.md
- PARADEX_TEST_SUMMARY.md

---

### 需要保留的文件

**核心测试框架**:
- ✅ test_exchanges.py（新的统一框架）

**当前有效的文档**:
- ✅ FRAMEWORK_README.md
- ✅ QUICK_TEST_GUIDE.md
- ✅ EXCHANGE_TEST_GUIDE.md
- ✅ EXCHANGE_TEST_DEMO.md
- ✅ COMMAND_CHEATSHEET.md
- ✅ PROJECT_COMPLETION_SUMMARY.md
- ✅ FINAL_PROJECT_REPORT.md
- ✅ EXCHANGE_TESTING_README.md
- ✅ EXCHANGES_CONFIG_GUIDE.md
- ✅ CREDENTIALS_SETUP_GUIDE.md
- ✅ CREDENTIALS_QUICK_START.md

---

## 🚀 执行计划

### 第1步：移动旧测试文件到 archive/old_tests/
```
test_okx.py
test_extended.py
test_paradex.py
test_hyperliquid.py
test_bitget.py
test_backpack.py
test_edgex.py
test_grvt.py
test_lighter.py
test_aster.py
test_all_exchanges.py
test_live_exchanges_simple.py
test_websocket_feeds.py
test_ws_simple.py
test_paradex_websocket.py
test_paradex_limit_order.py
test_tp_sl_complete.py
test_live_exchange_functions.py
test_remaining_features.py
test_close_position.py
test_position_aggregator.py
test_exchange_integration.py
validate_perpbot_v2.py
```

### 第2步：移动旧文档文件到 archive/old_docs/
```
QUICK_START_TESTNET.md
TESTNET_CONNECTION_GUIDE.md
TESTNET_DOCS_INDEX.md
TESTNET_READY_REPORT.md
EXTENDED_TEST_PLAN.md
LIGHTER_TEST_PLAN.md
MANUAL_TESTING_GUIDE.md
EXCHANGE_TESTING_STATUS.md
EXCHANGE_MOCK_MODE_SUMMARY.md
UNIT_TESTING_SUMMARY.md
PERFORMANCE_TESTING_SUMMARY.md
PARADEX_TEST_SUMMARY.md
```

### 第3步：创建索引文件 archive/README.md
- 说明哪些文件被归档
- 何时归档的
- 为什么被替代
- 如何使用新的框架

### 第4步：更新主 README.md
- 更新指向新框架的链接
- 删除对旧文件的引用
- 更新项目状态

### 第5步：创建 TAG
```bash
git tag -a v2.1-unified-framework -m "Add unified exchange framework and credentials setup"
```

### 第6步：推送 GitHub
```bash
git add .
git commit -m "chore: archive old tests and docs, add credentials setup tools"
git push origin main
git push origin v2.1-unified-framework
```

---

## 📊 统计信息

**要归档的文件**:
- 测试文件: 23 个
- 文档文件: 12 个
- 总计: 35 个旧文件

**保留的核心文件**:
- 测试框架: 1 个 (test_exchanges.py)
- 设置脚本: 1 个 (setup_credentials.sh)
- 核心文档: 11 个

**新增文件**:
- CREDENTIALS_QUICK_START.md
- CREDENTIALS_SETUP_GUIDE.md
- setup_credentials.sh

---

## ✅ 完成标记

- [ ] 移动旧测试文件
- [ ] 移动旧文档文件
- [ ] 创建归档索引
- [ ] 更新 README.md
- [ ] 创建 TAG
- [ ] 推送 GitHub

