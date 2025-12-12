# 四大交易所实盘连接测试指南

**测试日期**: 2025-12-12  
**目标交易所**: OKX、币安、BITGET、Hyperliquid  
**模式**: Demo Trading / Testnet (无真实资金风险)

---

## 📊 交易所就绪状态

| 交易所 | 虚拟环境 | 测试脚本 | 客户端 | SDK | 凭证 | 状态 |
|--------|---------|---------|--------|-----|------|------|
| **OKX** | ✅ venv_okx | ✅ test_okx.py | ✅ okx.py | ✅ okx 2.1.2 | ❌ 缺失 | 📋 准备中 |
| **币安** | ❌ 不存在 | ❌ 不存在 | ❌ 不存在 | ❌ 缺失 | ❌ 缺失 | ⏸️ 需要实现 |
| **BITGET** | ❌ 不存在 | ❌ 不存在 | ❌ 不存在 | ❌ 缺失 | ❌ 缺失 | ⏸️ 需要实现 |
| **Hyperliquid** | ✅ venv_hyperliquid | ✅ test_hyperliquid.py | ✅ hyperliquid.py | ✅ SDK 0.21.0 | ❌ 缺失 | 📋 准备中 |

---

## 🟢 立即可测试（已有完整实现）

### 1. OKX 实盘连接测试

**特点**:
- ✅ 虚拟环境完整 (`venv_okx`)
- ✅ 客户端实现完整 (`src/perpbot/exchanges/okx.py`)
- ✅ 测试脚本已有 (`test_okx.py`)
- ⚠️ Demo Trading 模式（安全）
- ✅ OKX SDK (ccxt okx 2.1.2) 已安装

**所需凭证**:
```bash
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet
```

**获取方式**: https://www.okx.com/account/my-api

**测试命令**:
```bash
# 激活虚拟环境
source venv_okx/bin/activate

# 配置 .env（复制凭证后）
# 编辑 .env 添加 OKX_* 变量

# 运行测试
python test_okx.py --inst BTC-USDT
python test_okx.py --inst ETH-USDT
```

---

### 2. Hyperliquid 实盘连接测试

**特点**:
- ✅ 虚拟环境完整 (`venv_hyperliquid`)
- ✅ 客户端实现完整 (`src/perpbot/exchanges/hyperliquid.py`)
- ✅ 测试脚本已有 (`test_hyperliquid.py`)
- ✅ Testnet 模式可用
- ✅ Hyperliquid SDK (0.21.0) 已安装

**所需凭证** (可选读写分离):
```bash
# 读-only 模式（无凭证也可查价格）
# 需要时添加以下配置进行交易：

HYPERLIQUID_ACCOUNT_ADDRESS=0xyour_account_address
HYPERLIQUID_PRIVATE_KEY=your_private_key
HYPERLIQUID_VAULT_ADDRESS=your_vault_address  # 可选
HYPERLIQUID_ENV=testnet
```

**获取方式**: 
- 账户: https://app.hyperliquid.xyz
- Testnet: https://testnet.hyperliquid.xyz

**测试命令**:
```bash
# 激活虚拟环境
source venv_hyperliquid/bin/activate

# 运行测试（可以只读模式，无凭证）
python test_hyperliquid.py --symbol BTC/USDC --depth 20
python test_hyperliquid.py --symbol ETH/USDC --depth 20
```

---

## 🔴 需要实现（暂无集成）

### 3. 币安 (Binance)

**当前状态**: ❌ 未实现

**需要做的**:
1. ✏️ 创建 `src/perpbot/exchanges/binance.py` 客户端
2. ✏️ 创建虚拟环境 `venv_binance`
3. ✏️ 安装 `python-binance` 或 `ccxt`
4. ✏️ 创建 `test_binance.py` 测试脚本
5. 📝 更新 `.env.example`

**预期实现**:
```python
# 类似 OKX 实现，支持:
- Demo trading 模式
- 读写分离
- 市场数据 API
- 账户信息 API
- 订单管理 API
```

**获取 API**: https://www.binance.com/en/account/api-management

**所需凭证**:
```bash
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_ENV=testnet
```

---

### 4. BITGET

**当前状态**: ⚠️ 部分实现

**已有文件**:
- ✅ `src/perpbot/incentives/bitget.py` (激励相关)
- ✅ `docs/BITGET_SETUP_GUIDE.md` (文档)
- ❌ `src/perpbot/exchanges/bitget.py` (交易客户端缺失)

**需要做的**:
1. ✏️ 创建 `src/perpbot/exchanges/bitget.py` 交易客户端
2. ✏️ 创建虚拟环境 `venv_bitget`
3. ✏️ 安装 BITGET SDK
4. ✏️ 创建 `test_bitget.py` 测试脚本
5. 📝 更新 `.env.example`

**预期实现**:
```python
# 支持:
- BITGET API (REST)
- Demo trading 模式
- 市场数据和账户管理
```

**获取 API**: https://www.bitget.com/en/user/account/api-management

**所需凭证**:
```bash
BITGET_API_KEY=your_key
BITGET_API_SECRET=your_secret
BITGET_PASSPHRASE=your_passphrase
BITGET_ENV=testnet
```

---

## 🚀 快速开始

### 步骤 1: 更新 .env 配置

在 `/home/fordxx/perp-tools/.env` 中添加凭证：

```bash
# ===== OKX =====
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase
OKX_ENV=testnet

# ===== Hyperliquid =====
HYPERLIQUID_ACCOUNT_ADDRESS=0xyour_account_address
HYPERLIQUID_PRIVATE_KEY=your_private_key
HYPERLIQUID_ENV=testnet

# ===== 币安 (待实现) =====
# BINANCE_API_KEY=your_key
# BINANCE_API_SECRET=your_secret
# BINANCE_ENV=testnet

# ===== BITGET (待实现) =====
# BITGET_API_KEY=your_key
# BITGET_API_SECRET=your_secret
# BITGET_PASSPHRASE=your_passphrase
# BITGET_ENV=testnet
```

### 步骤 2: 运行 OKX 测试

```bash
cd /home/fordxx/perp-tools
source venv_okx/bin/activate
python test_okx.py --inst BTC-USDT
```

### 步骤 3: 运行 Hyperliquid 测试

```bash
source venv_hyperliquid/bin/activate
python test_hyperliquid.py --symbol BTC/USDC
```

### 步骤 4: 实现币安和 BITGET (可选)

```bash
# 创建币安虚拟环境
python3 -m venv venv_binance
source venv_binance/bin/activate
pip install python-binance python-dotenv

# 创建 BITGET 虚拟环境
python3 -m venv venv_bitget
source venv_bitget/bin/activate
pip install bitget python-dotenv
```

---

## 📋 测试清单

### OKX 测试用例
- [ ] 连接测试 (读取账户余额)
- [ ] 价格查询 (BTC-USDT, ETH-USDT)
- [ ] 订单簿深度 (前 5 档)
- [ ] 账户持仓
- [ ] 下单测试 (Demo 模式)
- [ ] 取消订单
- [ ] WebSocket 实时订单更新 (可选)

### Hyperliquid 测试用例
- [ ] 连接测试 (读-only 模式)
- [ ] 价格查询 (BTC/USDC, ETH/USDC)
- [ ] 订单簿深度
- [ ] 账户信息 (若有凭证)
- [ ] 下单测试 (若有凭证)
- [ ] WebSocket 实时行情 (可选)

### 币安测试用例 (待实现)
- [ ] 客户端实现
- [ ] 虚拟环境配置
- [ ] 连接测试
- [ ] 价格查询
- [ ] Demo Trading 模式

### BITGET 测试用例 (待实现)
- [ ] 客户端实现
- [ ] 虚拟环境配置
- [ ] 连接测试
- [ ] 价格查询
- [ ] Demo Trading 模式

---

## ⚠️ 重要提示

1. **Demo Trading 模式**: OKX 和币安都支持演示交易，无需真实资金
2. **Testnet**: Hyperliquid 有专门的 Testnet 环境
3. **API 权限**: 建议仅启用 "读" 权限用于测试
4. **IP 白名单**: 为 API Key 配置 IP 白名单提高安全性
5. **.env 安全**: 不要提交 `.env` 文件到 Git

---

## 🔗 有用链接

- [OKX API 文档](https://www.okx.com/docs-v5/en/)
- [OKX Demo Trading](https://www.okx.com/account/my-api)
- [Hyperliquid 文档](https://hyperliquid.gitbook.io/hyperliquid-docs/)
- [币安 API 文档](https://binance-docs.github.io/apidocs/)
- [BITGET API 文档](https://bitget-doc.github.io/en/)

