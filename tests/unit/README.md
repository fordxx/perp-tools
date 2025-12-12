# PerpBot V2 Unit Tests

完整的单元测试套件，覆盖核心模块的功能验证。

---

## 📁 目录结构

```
tests/unit/
├── README.md                      # 本文档
├── __init__.py
├── test_event_bus.py              # EventBus 事件总线测试
├── test_risk_manager.py           # RiskManager 风控管理器测试
├── test_scanner_config.py         # ScannerConfig 扫描器配置测试
├── test_exposure_model.py         # ExposureModel 风险敞口模型测试
├── test_spread_calculator.py      # SpreadCalculator 价差计算器测试
└── run_all_tests.py               # 批量运行脚本
```

---

## 🎯 测试覆盖

### 1. EventBus (test_event_bus.py)
- ✅ 订阅和发布基本功能
- ✅ 多个订阅者
- ✅ 事件类型过滤
- ✅ 取消订阅
- ✅ 处理器异常隔离

**测试用例**: 6个

### 2. RiskManager (test_risk_manager.py)
- ✅ 风控管理器初始化
- ✅ 仓位大小限制
- ✅ 日内亏损限制
- ✅ 最大回撤限制
- ✅ 并发风控检查
- ✅ 动态更新限制

**测试用例**: 6个

### 3. ScannerConfig (test_scanner_config.py)
- ✅ 默认配置
- ✅ 自定义配置
- ✅ 交易所验证
- ✅ 交易对验证
- ✅ 利润阈值配置
- ✅ 更新间隔配置
- ✅ 仓位大小限制
- ✅ 配置复制
- ✅ 边界情况测试

**测试用例**: 13个

### 4. ExposureModel (test_exposure_model.py)
- ✅ 多头持仓
- ✅ 空头持仓
- ✅ 零持仓
- ✅ 名义价值计算
- ✅ 盈亏计算（多/空）
- ✅ 单个持仓风险敞口
- ✅ 同一交易对多个持仓
- ✅ 跨交易对风险敞口
- ✅ 对冲持仓

**测试用例**: 12个

### 5. SpreadCalculator (test_spread_calculator.py)
- ✅ 基本价差计算
- ✅ 零价差
- ✅ 负价差
- ✅ 大价差
- ✅ 小价差
- ✅ 小数精度
- ✅ 不同价格水平
- ✅ 极端价格
- ✅ 盈利性判断
- ✅ 考虑手续费的净利润

**测试用例**: 14个

---

## 🚀 快速开始

### 运行所有测试

```bash
# 方法1: 使用批量运行脚本
cd tests/unit
python run_all_tests.py

# 方法2: 使用 unittest discovery
python -m unittest discover tests/unit

# 方法3: 使用 pytest (如果已安装)
pytest tests/unit/
```

### 运行单个测试文件

```bash
# EventBus 测试
python tests/unit/test_event_bus.py

# RiskManager 测试
python tests/unit/test_risk_manager.py

# ScannerConfig 测试
python tests/unit/test_scanner_config.py

# ExposureModel 测试
python tests/unit/test_exposure_model.py

# SpreadCalculator 测试
python tests/unit/test_spread_calculator.py
```

### 运行单个测试用例

```bash
# 使用 unittest
python -m unittest tests.unit.test_event_bus.TestEventBus.test_subscribe_and_publish

# 使用 pytest
pytest tests/unit/test_event_bus.py::TestEventBus::test_subscribe_and_publish
```

---

## 📊 测试统计

### 覆盖率概览

| Module | Test File | Test Cases | Coverage |
|--------|-----------|------------|----------|
| EventBus | test_event_bus.py | 6 | 核心功能 |
| RiskManager | test_risk_manager.py | 6 | 核心功能 |
| ScannerConfig | test_scanner_config.py | 13 | 完整覆盖 |
| ExposureModel | test_exposure_model.py | 12 | 核心功能 |
| SpreadCalculator | test_spread_calculator.py | 14 | 完整覆盖 |
| **Total** | **5 files** | **51 tests** | **核心模块** |

### 测试类型分布

- **功能测试**: 35个 (68%)
- **边界测试**: 10个 (20%)
- **集成测试**: 6个 (12%)

---

## 🔍 测试方法论

### 1. 测试结构

每个测试文件遵循以下结构：

```python
import unittest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.module_name import ClassName

class TestClassName(unittest.TestCase):
    def setUp(self):
        """每个测试前初始化"""
        pass

    def tearDown(self):
        """每个测试后清理"""
        pass

    def test_feature_name(self):
        """测试特定功能"""
        # Arrange (准备)
        # Act (执行)
        # Assert (断言)
        pass

if __name__ == "__main__":
    unittest.main()
```

### 2. 测试命名规范

- 测试文件: `test_<module_name>.py`
- 测试类: `Test<ClassName>`
- 测试方法: `test_<feature_description>`

### 3. 断言方法

```python
# 相等性
self.assertEqual(a, b)
self.assertNotEqual(a, b)

# 真值
self.assertTrue(condition)
self.assertFalse(condition)

# 比较
self.assertGreater(a, b)
self.assertLess(a, b)
self.assertGreaterEqual(a, b)
self.assertLessEqual(a, b)

# 近似相等（浮点数）
self.assertAlmostEqual(a, b, places=2)

# 包含
self.assertIn(item, container)
self.assertNotIn(item, container)

# 异常
self.assertRaises(ExceptionType, callable, *args)
with self.assertRaises(ExceptionType):
    # code that should raise exception
    pass

# 自定义失败
self.fail("Explanation of why test failed")
```

---

## 🧪 测试最佳实践

### 1. 测试隔离

- 每个测试独立运行，不依赖其他测试
- 使用 `setUp()` 和 `tearDown()` 确保干净的测试环境
- 避免全局状态和共享数据

### 2. 测试覆盖

- **正常路径**: 测试预期的正常使用场景
- **边界情况**: 测试极端值和边界条件
- **异常处理**: 测试错误输入和异常情况

### 3. 测试可读性

- 使用描述性的测试名称
- 添加清晰的注释说明测试意图
- 遵循 Arrange-Act-Assert 模式

### 4. 测试性能

- 单元测试应该快速执行（<100ms/test）
- 避免网络请求和文件 I/O
- 使用 mock 替代外部依赖

---

## 🔧 添加新测试

### 步骤1: 创建测试文件

```bash
# 在 tests/unit/ 目录下创建新文件
touch tests/unit/test_my_module.py
```

### 步骤2: 编写测试

```python
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from perpbot.my_module import MyClass

class TestMyClass(unittest.TestCase):
    def setUp(self):
        self.instance = MyClass()

    def test_my_feature(self):
        result = self.instance.my_method()
        self.assertEqual(result, expected_value)

if __name__ == "__main__":
    unittest.main()
```

### 步骤3: 运行测试

```bash
python tests/unit/test_my_module.py
```

---

## 📈 测试报告

### 生成覆盖率报告

```bash
# 安装 coverage
pip install coverage

# 运行测试并收集覆盖率
coverage run -m unittest discover tests/unit

# 生成报告
coverage report

# 生成 HTML 报告
coverage html
# 然后打开 htmlcov/index.html
```

### 示例输出

```
Name                          Stmts   Miss  Cover
-------------------------------------------------
src/perpbot/events/event_bus.py      45      2    96%
src/perpbot/risk_manager.py          78      5    94%
src/perpbot/scanner/config.py        32      0   100%
-------------------------------------------------
TOTAL                           823     42    95%
```

---

## 🐛 故障排查

### 测试失败

1. **导入错误**:
   ```
   ModuleNotFoundError: No module named 'perpbot'
   ```
   - 确保在测试文件中添加了 `sys.path.insert()`
   - 检查文件路径是否正确

2. **断言失败**:
   ```
   AssertionError: 10 != 20
   ```
   - 检查预期值是否正确
   - 使用 `print()` 调试实际值
   - 检查测试逻辑是否正确

3. **测试超时**:
   - 检查是否有阻塞操作
   - 使用 mock 替代耗时操作
   - 减少测试数据量

### 环境问题

```bash
# 确保依赖已安装
pip install -r requirements.txt

# 检查 Python 版本（需要 3.10+）
python --version

# 清理缓存
find . -type d -name "__pycache__" -exec rm -r {} +
find . -type f -name "*.pyc" -delete
```

---

## 🎯 测试目标

### 当前覆盖率
- **核心模块**: 5个
- **测试用例**: 51个
- **代码行数**: ~1,500 行

### 目标覆盖率
- **短期目标**: 覆盖所有核心模块（10+模块）
- **中期目标**: 80%+ 代码覆盖率
- **长期目标**: 90%+ 代码覆盖率

### 待添加测试
- [ ] Execution Engine (执行引擎)
- [ ] Position Aggregator (持仓聚合)
- [ ] Capital Orchestrator (资金编排)
- [ ] Health Monitor (健康监控)
- [ ] WebSocket Manager (WebSocket 管理器)

---

## 🔗 相关文档

- [DEVELOPMENT_ROADMAP.md](../../DEVELOPMENT_ROADMAP.md) - 项目开发路线图
- [tests/performance/README.md](../performance/README.md) - 性能测试文档

---

## 📝 贡献指南

### 添加新测试

1. 创建测试文件 `test_<module>.py`
2. 编写测试用例
3. 运行测试验证
4. 更新本 README

### 测试规范

- 每个公共方法至少1个测试
- 覆盖正常路径和边界情况
- 测试名称清晰描述测试内容
- 添加必要的注释

---

**维护者**: Claude Sonnet 4.5
**创建时间**: 2025-12-12
**版本**: 1.0.0
