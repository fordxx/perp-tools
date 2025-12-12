# 📦 过时文件归档候选清单

**扫描日期**: 2025-12-12  
**扫描范围**: /home/fordxx/perp-tools (全项目)  
**V2 架构版本**: Event-Driven (capital_orchestrator.py → src/perpbot/capital/ 迁移完成)

---

## 🚨 高优先级归档 (立即归档)

### 1. **根目录的单体文件** (与 src/perpbot/ 重复/过时)

| 文件 | 大小 | 原因 | 迁移目标 |
|------|------|------|---------|
| `execution_engine.py` | 107 行 | V1 单体，已在 `src/perpbot/execution/execution_engine_v2.py` 中重写 | 已有替代 ✅ |
| `execution_engine_v2.py` | ~200 行 | 根目录残留，应在 `src/perpbot/execution/` | 已有正式位置 ✅ |
| `quote_engine_v2.py` | ~250 行 | 根目录残留，应在 `src/perpbot/` | 已有正式位置 ✅ |
| `console_updater.py` | 80 行 | V1 console，已在 `src/perpbot/console/` 中整合 | 已有替代 ✅ |
| `main.py` | 229 行 | 旧入口，应使用 `src/perpbot/cli.py` | 已有标准入口 ✅ |
| `execution_result.py` | 未检查 | 模型残留 | models/ 中已有 |
| `fallback_policy.py` | 未检查 | 风险管理残留 | risk_manager.py 中已有 |
| `maker_tracker_adapter.py` | ~56 行 | 执行成本残留 | execution_cost_engine.py 中已有 |
| `retry_policy.py` | 未检查 | 重试逻辑残留 | 已在各客户端中集成 |
| `quote_cache.py` | 72 行 | 缓存残留，已在 monitoring/ 中 | quote_types.py 中已有 |
| `quote_noise_filter.py` | 未检查 | 过滤器残留，已在 scanner/ 中 | 已有正式位置 |
| `quote_normalizer.py` | 未检查 | 规范化残留 | exchanges/pricing.py |
| `quote_quality.py` | 未检查 | 质量检查残留 | monitoring/ 中已有 |
| `quote_types.py` | 未检查 | 类型定义残留 | models/ 中已有 |
| `validate_perpbot_v2.py` | 未检查 | V2 验证工具，但仅用于一次验证 | 可保留或归档 |
| `hedge_volume_engine.py` | 未检查 | 对冲体积残留 | strategy/ 中已有 |
| `execution_cost_engine.py` | 未检查 | 执行成本残留 | execution/ 中已有 |
| `unified_hedge_scheduler.py` | 未检查 | 对冲调度残留 | strategy/ 中已有 |
| `position_guard.py` | 未检查 | 持仓卫士残留 | risk_manager.py 中已有 |

**建议**: 整体迁移到 `archive/root_legacy/` 下

### 2. **根目录的过时配置目录**

| 目录 | 说明 | 迁移目标 |
|------|------|---------|
| `capital/` | V1 资金管理，已整合到 `src/perpbot/capital/` | 归档 |
| `models/` | V1 模型定义，已整合到 `src/perpbot/models/` | 归档 |
| `positions/` | V1 持仓管理，已整合到 `src/perpbot/positions/` | 归档 |
| `risk/` | V1 风险管理，已整合到 `src/perpbot/risk_manager.py` | 归档 |

**建议**: 整体迁移到 `archive/root_legacy_dirs/`

### 3. **文件系统污染**

| 文件 | 原因 | 处理 |
|------|------|------|
| `tatus` (120 行) | Git status 输出被误存为文件 | 🗑️ 删除 |
| `validation_output.txt` | 验证脚本的旧输出 | 🗑️ 删除或归档 |
| `__pycache__/` (多个) | Python 缓存目录 | 🗑️ 自动清理 |

---

## ⚠️ 中优先级归档 (有条件保留)

### 4. **过时模型定义**

| 文件 | 位置 | 原因 | 处理 |
|------|------|------|------|
| `src/perpbot/models_old.py` | 250 行 | V1 模型，新版本在 `models.py` | 归档 (keep for reference) |
| `src/perpbot/core_capital_orchestrator.py` | 533 行 | V1 资金管理，已在 `src/perpbot/capital_orchestrator.py` 中重写 | 归档 (keep for reference) |
| `src/perpbot/config_enhanced.py` | 363 行 | V1 配置增强，已在 `src/perpbot/config.py` 中集成 | 归档 (keep for reference) |

**建议**: 迁移到 `archive/src_perpbot_old/`，保留作为历史参考

### 5. **过时虚拟环境**

| 目录 | 用途 | 状态 | 处理 |
|------|------|------|------|
| `venv_aster/` | Aster 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_backpack/` | Backpack 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_binance/` | Binance 交易所专用环境 | ⚠️ 未实现客户端 | 归档或删除 |
| `venv_bybit/` | Bybit 交易所专用环境 | ⚠️ 未实现客户端 | 归档或删除 |
| `venv_edgex/` | EdgeX 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_extended/` | Extended 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_grvt/` | GRVT 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_okx/` | OKX 交易所专用环境 | ✅ 可用 | 保留 (必要) |
| `venv_paradex/` | Paradex 交易所专用环境 | ✅ 可用 | 保留 (必要) |

**建议**: 删除 `venv_binance/` 和 `venv_bybit/` (未实现客户端)

### 6. **过时测试文件**

| 文件 | 用途 | 备注 | 处理 |
|------|------|------|------|
| `test_all_exchanges.py` | 通用交易所测试框架 | ✅ 仍有用 | 保留 |
| `test_aster.py` | Aster 测试 | ✅ 仍有用 | 保留 |
| `test_backpack.py` | Backpack 测试 | ✅ 仍有用 | 保留 |
| `test_binance.py` | Binance 测试 | ⚠️ 无对应客户端 | 归档 |
| `test_bybit.py` | Bybit 测试 | ⚠️ 无对应客户端 | 归档 |
| `test_edgex.py` | EdgeX 测试 | ✅ 仍有用 | 保留 |
| `test_extended.py` | Extended 测试 | ✅ 仍有用 | 保留 |
| `test_grvt.py` | GRVT 测试 | ✅ 仍有用 | 保留 |
| `test_lighter.py` | Lighter 测试 | ✅ 仍有用 | 保留 |
| `test_okx.py` | OKX 测试 | ✅ 仍有用 | 保留 |
| `test_paradex.py` | Paradex 测试 | ✅ 仍有用 | 保留 |
| `test_ws_simple.py` | Paradex WebSocket 简化测试 | ⚠️ 已由 test_paradex_ws_tp_sl.py 替代 | 归档 |
| `test_position_aggregator.py` | 持仓聚合器测试 | ✅ 仍有用 | 保留 |
| `test_remaining_features.py` | 剩余功能测试 | ⚠️ 杂项，内容不明 | 检查后决定 |

---

## 📊 低优先级归档 (参考历史)

### 7. **验证和测试报告**

| 文件 | 类型 | 版本 | 处理 |
|------|------|------|------|
| `VALIDATION_REPORT.md` | 验证报告 | 92.0/100 (旧) | 归档 (保留 VALIDATION_FINAL_REPORT.md) |
| `VALIDATION_QUICKSTART.md` | 快速开始 | 旧版 | 归档 |
| `VALIDATION_FINAL_REPORT.md` | 最终报告 | 99.0/100 | **保留** ✅ |
| `validation_output.txt` | 脚本输出 | 临时 | 删除 |

### 8. **过时的演示代码**

| 文件 | 位置 | 用途 | 处理 |
|------|------|------|------|
| `demos/capital_orchestrator_demo.py` | src/perpbot/demos/ | V1 演示 | 检查是否需更新或归档 |
| `demos/connection_demo.py` | src/perpbot/demos/ | 连接演示 | 检查是否需更新或归档 |
| `demos/execution_demo.py` | src/perpbot/demos/ | 执行演示 | 检查是否需更新或归档 |
| `demos/fee_comparison_demo.py` | src/perpbot/demos/ | 费用演示 | 检查是否需更新或归档 |
| `demos/hedge_volume_demo.py` | src/perpbot/demos/ | 对冲体积演示 | 检查是否需更新或归档 |
| `demos/scoring_demo.py` | src/perpbot/demos/ | 评分演示 | 检查是否需更新或归档 |

### 9. **已归档文件 (当前 archive/)**

| 文件 | 状态 | 说明 |
|------|------|------|
| `archive/BRANCH_ANALYSIS.md` | ✅ | 分支策略分析 |
| `archive/DELIVERY_SUMMARY.md` | ✅ | 交付总结 |
| `archive/DOCUMENTATION_INDEX.md` | ✅ | 文档索引 v1.0 |
| `archive/MERGE_SUMMARY.md` | ✅ | 合并总结 |
| `archive/PARADEX_DEPENDENCIES.md` | ✅ | Paradex 依赖分析 |
| `archive/README_COMPLETE.md` | ✅ | 完整 README v1.0 |
| `archive/perpbot-important-architecture.md` | ✅ | 重要架构决策 v1.0 |
| `archive/test_okx_demo.py` | ✅ | OKX 演示测试 |
| `archive/test_paradex_websocket.py` | ✅ | Paradex WebSocket 旧测试 |

---

## 🎯 建议的归档方案

### 方案 A: 激进清理 (推荐)

```
archive/
├── root_legacy/                    # 根目录单体文件
│   ├── execution_engine.py
│   ├── execution_engine_v2.py
│   ├── quote_engine_v2.py
│   ├── console_updater.py
│   ├── main.py
│   ├── execution_result.py
│   ├── fallback_policy.py
│   ├── maker_tracker_adapter.py
│   ├── retry_policy.py
│   ├── quote_cache.py
│   ├── quote_noise_filter.py
│   ├── quote_normalizer.py
│   ├── quote_quality.py
│   ├── quote_types.py
│   ├── hedge_volume_engine.py
│   ├── execution_cost_engine.py
│   ├── unified_hedge_scheduler.py
│   └── position_guard.py
│
├── root_legacy_dirs/               # 根目录旧目录
│   ├── capital/
│   ├── models/
│   ├── positions/
│   └── risk/
│
├── src_perpbot_old/                # src/perpbot 中的旧文件
│   ├── models_old.py
│   ├── core_capital_orchestrator.py
│   └── config_enhanced.py
│
├── test_exchanges_unimplemented/   # 未实现的交易所测试
│   ├── test_binance.py
│   └── test_bybit.py
│
├── old_validation_reports/         # 旧验证报告
│   ├── VALIDATION_REPORT.md
│   └── VALIDATION_QUICKSTART.md
│
└── ... (现有 archive 内容保留)
```

**删除**: `tatus`, `validation_output.txt`, `.pycache/`  
**删除 venv**: `venv_binance/`, `venv_bybit/`

---

### 方案 B: 保守清理

仅删除明确损坏或无用的文件:
- `tatus` (git 输出污染)
- `validation_output.txt` (临时脚本输出)
- `test_binance.py`, `test_bybit.py` (无对应客户端)

保留其他文件供参考。

---

## 📈 项目文件统计

| 类别 | 文件数 | 状态 |
|------|--------|------|
| 主要代码 (`src/perpbot/`) | ~80+ | ✅ V2 Event-Driven |
| 测试文件 (根目录 `test_*.py`) | 12 | ⚠️ 3 个无对应客户端 |
| 根目录单体文件 | 19 | 🚨 应迁移到 `src/` 或 `archive/` |
| 根目录旧目录 | 4 | 🚨 应迁移到 `archive/` |
| 文档 (根目录) | 7 | ✅ V2 Event-Driven (已更新) |
| Archive 文件 | 9 | ✅ 合理保留 |
| 虚拟环境 | 9 | ⚠️ 2 个无对应实现 |
| 供应商代码 (`vendor/`) | 1 (x10/) | ✅ 保留 |

**总计**: ~150+ 个追踪的项目项

---

## 🔧 执行清理步骤

### 第 1 步: 验证迁移完成

```bash
# 确认新位置存在这些文件
ls src/perpbot/execution/execution_engine_v2.py
ls src/perpbot/capital/
ls src/perpbot/models/
ls src/perpbot/positions/
ls src/perpbot/risk_manager.py
```

### 第 2 步: 备份根目录单体文件

```bash
mkdir -p archive/root_legacy
mv execution_engine.py archive/root_legacy/
mv execution_engine_v2.py archive/root_legacy/
mv quote_engine_v2.py archive/root_legacy/
# ... (其他 19 个文件)
```

### 第 3 步: 备份根目录旧目录

```bash
mkdir -p archive/root_legacy_dirs
mv capital/ archive/root_legacy_dirs/
mv models/ archive/root_legacy_dirs/
mv positions/ archive/root_legacy_dirs/
mv risk/ archive/root_legacy_dirs/
```

### 第 4 步: 清理污染文件

```bash
rm -f tatus validation_output.txt
rm -rf __pycache__ src/__pycache__ src/perpbot/__pycache__
```

### 第 5 步: 删除未实现的虚拟环境

```bash
rm -rf venv_binance/ venv_bybit/
```

### 第 6 步: 更新 .gitignore (如果需要)

```bash
# 添加到 .gitignore
archive/root_legacy/
archive/root_legacy_dirs/
```

---

## 📝 清理后预期结构

```
perp-tools/
├── src/                           # ✅ 标准源代码
│   └── perpbot/                   # V2 Event-Driven
│       ├── capital/               # 资金系统
│       ├── execution/             # 执行系统
│       ├── models/                # 数据模型
│       ├── positions/             # 持仓管理
│       ├── risk_manager.py        # 风险管理 (统一)
│       ├── cli.py                 # 标准入口 ✅
│       └── ... (其他模块)
│
├── docs/                          # 📖 文档
├── archive/                       # 📦 历史存档
│   ├── root_legacy/               # 根目录旧单体文件
│   ├── root_legacy_dirs/          # 根目录旧目录
│   ├── src_perpbot_old/           # 旧模型和配置
│   ├── test_exchanges_unimplemented/
│   ├── old_validation_reports/
│   └── ... (原有)
│
├── test_*.py                      # ✅ 保留 (有效测试)
├── config.example.yaml            # ✅ 配置模板
├── requirements.txt               # ✅ 依赖
├── README.md                      # ✅ V2 Event-Driven 版本
├── ARCHITECTURE.md                # ✅ V2 架构文档
├── SECURITY.md                    # ✅ 安全指南
├── DEVELOPING_GUIDE.md            # ✅ 开发指南
└── ... (其他文档)
```

---

## ✅ 验证清单

- [ ] 所有 `src/perpbot/` 中的文件都已验证
- [ ] 所有归档候选文件都有备份目的地
- [ ] `.gitignore` 已确认包含 `archive/`
- [ ] 没有硬链接依赖于旧位置
- [ ] 测试仍能通过: `python test_all_exchanges.py`
- [ ] CLI 仍能工作: `python -m src.perpbot.cli --help` (或通过 `src/perpbot/cli.py`)

