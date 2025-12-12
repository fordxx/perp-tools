# 交易所实盘功能测试指南
# Manual Exchange Testing Guide

**测试日期**: 2025-12-12
**模式**: 只读测试 (READ-ONLY - 安全)

---

## 📋 测试准备

### 1. 检测已配置的交易所

根据你的 `.env` 文件，已配置的交易所有：

```bash
# 运行检测脚本
cat .env | grep -E "^[A-Z].*_API_KEY|^[A-Z].*_PRIVATE_KEY" | grep -v "your_"
```

### 2. 当前问题

❌ **问题1**: 虚拟环境问题
- `venv_paradex` 和 `venv_extended` 无法激活
- 建议重新创建虚拟环境或使用系统 Python

❌ **问题2**: 缺少依赖
- `dotenv` 模块未安装
- 某些交易所SDK可能未安装

---

## 🔧 解决方案

### 方案 A: 安装缺失的依赖到系统 Python

```bash
# 安装基础依赖
pip3 install python-dotenv

# 安装交易所 SDK
pip3 install paradex-py  # Paradex
pip3 install hyperliquid-python-sdk  # Hyperliquid (如果使用)
```

### 方案 B: 重新创建虚拟环境

```bash
# Paradex
python3 -m venv venv_paradex
source venv_paradex/bin/activate
pip install python-dotenv paradex-py
deactivate

# Extended
python3 -m venv venv_extended
source venv_extended/bin/activate
pip install python-dotenv
# Extended 的 SDK 安装
deactivate
```

---

## 🧪 手动测试步骤

### 测试 Paradex

```bash
# 1. 激活虚拟环境（如果有）
source venv_paradex/bin/activate

# 2. 确保依赖已安装
pip install python-dotenv paradex-py

# 3. 运行测试
python3 test_paradex.py

# 4. 停用虚拟环境
deactivate
```

### 测试 Extended

```bash
# 1. 激活虚拟环境（如果有）
source venv_extended/bin/activate

# 2. 确保依赖已安装
pip install python-dotenv

# 3. 运行测试
python3 test_extended.py

# 4. 停用虚拟环境
deactivate
```

### 测试 Hyperliquid (如果配置)

```bash
# 安装依赖
pip3 install python-dotenv

# 运行测试
python3 test_hyperliquid.py
```

---

## 📊 测试内容

每个交易所的测试包括：

### ✅ Test 1: 连接和认证
- 验证 API 凭证有效
- 验证网络连接
- 预期结果: 成功连接

### ✅ Test 2: 获取价格
- 查询 BTC 或其他主要币种的当前价格
- 预期结果: 返回 Bid/Ask 价格

### ✅ Test 3: 查询余额
- 查询账户余额（USDT/USDC）
- 预期结果: 返回可用余额

### ✅ Test 4: 查询持仓
- 查询当前活跃持仓
- 预期结果: 返回持仓列表（可能为空）

### ⏭️ Test 5: 下单测试 (跳过)
- **默认跳过**，需要明确启用
- 如需测试，使用最小金额

---

## 🚀 快速测试命令

### 一键测试所有已配置交易所

```bash
# 方法1: 使用自动化脚本（需要先修复依赖）
./run_live_exchange_tests.sh

# 方法2: 手动逐个测试
for script in test_paradex.py test_extended.py test_hyperliquid.py; do
    if [ -f "$script" ]; then
        echo "Testing $script..."
        python3 "$script" || echo "Failed: $script"
    fi
done
```

### 测试单个交易所

```bash
# Paradex
python3 test_paradex.py

# Extended
python3 test_extended.py

# Hyperliquid
python3 test_hyperliquid.py

# OKX (如果配置)
python3 test_okx.py

# EdgeX (如果配置)
python3 test_edgex.py

# Lighter (如果配置)
python3 test_lighter.py
```

---

## 📝 预期输出示例

### 成功的测试输出

```
============================================================
  测试 Paradex 连接
============================================================
[INFO] 连接到 Paradex (testnet 模式)...
✅ 连接成功！

============================================================
  测试 获取价格
============================================================
[INFO] 查询 BTC-USD-PERP 价格...
✅ Bid: $95,234.50, Ask: $95,235.00, Spread: $0.50

============================================================
  测试 查询余额
============================================================
[INFO] 查询账户余额...
✅ USDC 可用: $1,234.56, 总计: $1,234.56

============================================================
  测试 查询持仓
============================================================
[INFO] 查询活跃持仓...
✅ 找到 2 个活跃持仓
  - BTC-USD-PERP: long 0.01 @ $94,500.00
  - ETH-USD-PERP: short 0.10 @ $3,450.00
```

### 失败的测试输出

```
❌ 连接失败: Invalid API key
或
❌ 查询价格失败: Network timeout
或
❌ 查询余额失败: Insufficient permissions
```

---

## 🔍 故障排查

### 问题1: ModuleNotFoundError: No module named 'dotenv'

```bash
# 解决方案
pip3 install python-dotenv
```

### 问题2: ModuleNotFoundError: No module named 'perpbot'

```bash
# 解决方案: 确保在正确的目录运行
cd /home/fordxx/perp-tools
python3 test_paradex.py
```

### 问题3: API 认证失败

```bash
# 检查 .env 文件
cat .env | grep PARADEX

# 确保配置正确
# PARADEX_L2_PRIVATE_KEY=0x...  (真实的私钥)
# PARADEX_ACCOUNT_ADDRESS=0x... (真实的地址)
# PARADEX_ENV=testnet
```

### 问题4: 网络连接超时

```bash
# 检查网络连接
ping -c 3 api.paradex.trade
或
curl -I https://api.paradex.trade/v1/system/time
```

### 问题5: 虚拟环境激活失败

```bash
# 方法1: 重新创建虚拟环境
rm -rf venv_paradex
python3 -m venv venv_paradex
source venv_paradex/bin/activate
pip install -r requirements.txt  # 如果有
pip install python-dotenv paradex-py

# 方法2: 不使用虚拟环境，直接使用系统 Python
pip3 install python-dotenv paradex-py
python3 test_paradex.py
```

---

## 📈 测试结果记录模板

```
交易所实盘功能测试报告
测试时间: 2025-12-12

| 交易所 | 连接 | 价格 | 余额 | 持仓 | 备注 |
|--------|------|------|------|------|------|
| Paradex | ✅ | ✅ | ✅ | ✅ | 测试网，连接正常 |
| Extended | ✅ | ✅ | ❌ | - | 余额查询失败 |
| Hyperliquid | ❌ | - | - | - | API 密钥无效 |

总结:
- 成功: 1/3 (Paradex)
- 部分成功: 1/3 (Extended)
- 失败: 1/3 (Hyperliquid)
```

---

## 🛡️ 安全提醒

1. ✅ **只读模式**: 默认测试不执行下单
2. ✅ **测试网优先**: 优先使用测试网（testnet）
3. ✅ **小金额**: 如果需要下单测试，使用最小金额
4. ❌ **不要分享**: 不要分享测试输出中的私钥或 API 密钥
5. ❌ **不要提交**: 不要将包含凭证的 .env 文件提交到 Git

---

## 📞 需要帮助？

如果遇到问题，请提供以下信息：

1. **错误信息**: 完整的错误堆栈
2. **测试的交易所**: 例如 Paradex, Extended
3. **环境信息**:
   ```bash
   python3 --version
   pip3 list | grep -E "dotenv|paradex"
   ```
4. **配置检查** (隐藏敏感信息):
   ```bash
   cat .env | grep -E "^[A-Z]" | sed 's/=.*/=***/'
   ```

---

**下一步**: 修复依赖问题后，运行 `./run_live_exchange_tests.sh` 或手动测试各交易所
