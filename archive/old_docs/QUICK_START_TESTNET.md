# 四大交易所实盘连接测试 - 快速开始指南

## 🚀 快速启动（3分钟）

### 第一步：准备凭证

从各交易所获取 API Key：

**1️⃣ OKX**
- 网址: https://www.okx.com/account/my-api
- 创建新 API Key
- 复制: API Key, Secret, Passphrase
- 权限: 建议只开启"只读"权限用于测试

**2️⃣ Hyperliquid**
- 网址: https://app.hyperliquid.xyz (或 testnet 环境)
- 如果是 Testnet: https://testnet.hyperliquid.xyz
- 获取账户地址和私钥（可选，支持读-only 模式）
- 权限: 建议"只读"权限

**3️⃣ 币安** (可选，需实现)
- 网址: https://www.binance.com/en/account/api-management
- 创建测试网 API Key: https://testnet.binancefuture.com
- 复制: API Key, Secret
- 权限: 只读权限

**4️⃣ BITGET** (可选，需实现)
- 网址: https://www.bitget.com/en/user/account/api-management
- 创建新 API Key
- 复制: API Key, Secret, Passphrase
- 权限: 只读权限

### 第二步：配置凭证

编辑 `.env` 文件 (复制并修改以下内容)：

```bash
# ===== OKX (Demo Trading - 安全) =====
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_api_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here
OKX_ENV=testnet

# ===== Hyperliquid (可选凭证，支持读-only) =====
HYPERLIQUID_ACCOUNT_ADDRESS=0xyour_account_address_here
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_ENV=testnet

# ===== 币安 (Testnet - 待实现) =====
# BINANCE_API_KEY=your_binance_api_key_here
# BINANCE_API_SECRET=your_binance_api_secret_here
# BINANCE_ENV=testnet

# ===== BITGET (待实现) =====
# BITGET_API_KEY=your_bitget_api_key_here
# BITGET_API_SECRET=your_bitget_api_secret_here
# BITGET_PASSPHRASE=your_bitget_passphrase_here
# BITGET_ENV=testnet
```

### 第三步：运行测试

```bash
# 进入项目目录
cd /home/fordxx/perp-tools

# 测试 OKX 和 Hyperliquid
python test_multi_exchange.py --exchanges okx hyperliquid

# 测试所有可用交易所
python test_multi_exchange.py --exchanges all

# 详细日志输出
python test_multi_exchange.py --exchanges okx --verbose
```

---

## 📊 测试脚本说明

### 统一测试脚本：`test_multi_exchange.py`

支持同时测试多个交易所：

```bash
# 测试指定交易所
python test_multi_exchange.py --exchanges okx hyperliquid

# 参数说明
python test_multi_exchange.py --help
```

**测试内容**:
- ✅ 连接验证
- ✅ 价格查询 (Bid/Ask)
- ✅ 订单簿深度
- ✅ 账户信息 (如有凭证)
- ✅ 持仓信息 (如有凭证)

### 单个交易所测试脚本

```bash
# OKX 测试
source venv_okx/bin/activate
python test_okx.py --inst BTC-USDT
deactivate

# Hyperliquid 测试
source venv_hyperliquid/bin/activate
python test_hyperliquid.py --symbol BTC/USDC
deactivate

# 币安测试 (待实现)
python test_binance.py --symbol BTC/USDT

# BITGET 测试 (待实现)
python test_bitget.py --inst BTC-USDT
```

---

## ✅ 当前状态

| 交易所 | 虚拟环境 | 客户端实现 | 测试脚本 | 凭证 | 状态 |
|--------|---------|---------|---------|------|------|
| **OKX** | ✅ venv_okx | ✅ okx.py | ✅ test_okx.py | 📋 需配置 | 🟢 可测 |
| **Hyperliquid** | ✅ venv_hyperliquid | ✅ hyperliquid.py | ✅ test_hyperliquid.py | 📋 可选 | 🟢 可测 |
| **币安** | ❌ 需创建 | ✅ binance.py | ✅ test_binance.py | 📋 需配置 | 🟡 部分准备 |
| **BITGET** | ❌ 需创建 | ✅ bitget.py | ✅ test_bitget.py | 📋 需配置 | 🟡 部分准备 |

---

## 🔧 故障排查

### 问题 1: "ModuleNotFoundError: No module named 'okx'"

**解决**:
```bash
source venv_okx/bin/activate
pip install okx python-dotenv
deactivate
```

### 问题 2: "BINANCE_API_KEY 缺失"

**解决**: 编辑 `.env` 文件，添加币安的 API Key

### 问题 3: "连接失败: 网络错误"

**解决**:
- 检查网络连接
- 确保代理配置正确
- 使用 `--verbose` 参数查看详细日志

### 问题 4: ".env 文件不存在"

**解决**:
```bash
# 复制示例文件
cp .env.example .env

# 编辑添加凭证
nano .env
```

---

## 📋 测试清单

### OKX 检查项
- [ ] 连接成功
- [ ] BTC-USDT 价格正确
- [ ] 订单簿深度有效
- [ ] 账户余额显示
- [ ] Demo Trading 模式确认

### Hyperliquid 检查项
- [ ] 连接成功 (读-only 模式)
- [ ] BTC/USDC 价格正确
- [ ] 订单簿深度有效
- [ ] 如有凭证：账户信息显示
- [ ] Testnet 环境确认

### 币安检查项 (待实现)
- [ ] 虚拟环境创建
- [ ] 客户端导入成功
- [ ] 连接到 Testnet
- [ ] 价格查询正常
- [ ] 账户信息显示

### BITGET 检查项 (待实现)
- [ ] 虚拟环境创建
- [ ] 客户端导入成功
- [ ] 连接到 BITGET
- [ ] 价格查询正常
- [ ] 账户信息显示

---

## 🔐 安全建议

⚠️ **重要**:

1. **不要提交 `.env` 到 Git**
   ```bash
   # .env 已在 .gitignore 中
   git check-ignore .env  # 应该返回 .env
   ```

2. **使用只读 API Key 测试**
   - 大多数交易所允许"只读"权限
   - 测试时避免使用交易权限

3. **配置 IP 白名单**
   - 在交易所面板中为 API Key 添加 IP 白名单
   - 限制 API Key 的使用范围

4. **定期更换 API Key**
   - 建议每月更换一次
   - 如果有泄露风险，立即更换

5. **不要在代码中硬编码凭证**
   - 始终使用环境变量 (`.env` 文件)
   - 使用 `dotenv` 库加载

---

## 📚 参考文档

- [TESTNET_CONNECTION_GUIDE.md](TESTNET_CONNECTION_GUIDE.md) - 详细的测试指南
- [README.md](README.md) - 项目概述
- [DEVELOPING_GUIDE.md](docs/DEVELOPING_GUIDE.md) - 开发指南

---

## 💡 下一步

1. ✅ **配置凭证** - 编辑 `.env`
2. ✅ **运行 OKX/Hyperliquid 测试** - `python test_multi_exchange.py --exchanges okx hyperliquid`
3. ⏳ **实现币安和 BITGET** - 创建虚拟环境并安装依赖
4. 📊 **集成到主系统** - 连接到 Capital Orchestrator 和 RiskManager

---

**需要帮助？** 查看 [MANUAL_TESTING_GUIDE.md](MANUAL_TESTING_GUIDE.md)
