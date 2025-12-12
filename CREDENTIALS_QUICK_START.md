# 🔐 凭证配置 - 快速参考

## 📊 当前配置状态

| 编号 | 交易所 | 配置状态 | 必需凭证 |
|------|--------|--------|---------|
| 1 | OKX | ❌ 缺凭证 | API_KEY, API_SECRET, PASSPHRASE |
| 2 | Binance | ❌ 缺凭证 | API_KEY, API_SECRET |
| 3 | Bitget | ❌ 缺凭证 | API_KEY, API_SECRET, PASSPHRASE |
| 4 | Bybit | ❌ 缺凭证 | API_KEY, API_SECRET |
| 5 | Hyperliquid | ✅ 已配置 | - |
| 6 | Paradex | ✅ 已配置 | L2_PRIVATE_KEY, ACCOUNT_ADDRESS |
| 7 | Extended | ✅ 已配置 | API_KEY, STARK_PRIVATE_KEY, VAULT_NUMBER |
| 8 | Lighter | ❌ 缺凭证 | API_KEY, PRIVATE_KEY |
| 9 | EdgeX | ❌ 缺凭证 | API_KEY |
| 10 | Backpack | ❌ 缺凭证 | API_KEY, API_SECRET |
| 11 | GRVT | ❌ 缺凭证 | API_KEY |
| 12 | Aster | ❌ 缺凭证 | API_KEY |
| 13 | Sunx | ❌ 缺凭证 | API_KEY |

---

## ⚡ 3 种配置方式

### 方式 1️⃣: 交互式脚本（最简单）
```bash
bash setup_credentials.sh
```
按提示填入凭证，自动保存到 .env

### 方式 2️⃣: 手动编辑 .env 文件
```bash
# 复制示例文件
cp .env.example .env

# 编辑文件
nano .env
```

### 方式 3️⃣: 命令行导出环境变量
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

---

## 🚀 快速配置命令

### 配置 OKX（最安全，使用 Demo 账户）
```env
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase
```

### 配置 Binance
```env
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_api_secret
```

### 配置 Bitget
```env
BITGET_API_KEY=your_bitget_api_key
BITGET_API_SECRET=your_bitget_api_secret
BITGET_PASSPHRASE=your_bitget_passphrase
```

### 配置 Bybit
```env
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_api_secret
```

---

## 🔍 验证配置

### 查看所有交易所配置状态
```bash
python test_exchanges.py --list
```

### 测试单个交易所
```bash
# 测试 OKX
python test_exchanges.py okx

# 测试 Binance
python test_exchanges.py binance

# 测试 Hyperliquid
python test_exchanges.py hyperliquid
```

### 测试所有已配置的交易所
```bash
python test_exchanges.py --all
```

---

## 🔐 安全最佳实践

✅ **必须做**:
- 使用 `.env` 文件管理凭证
- 确保 `.env` 在 `.gitignore` 中
- 使用只读 API Key
- 设置 IP 白名单

❌ **绝对不要**:
- 在代码中硬编码凭证
- 在 Git 中提交 `.env` 文件
- 给予 API Key 交易权限
- 在公共频道分享 API Key

---

## 📋 .env 文件示例

```env
# OKX (Demo Trading)
OKX_API_KEY=your_okx_key_here
OKX_API_SECRET=your_okx_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here

# Binance
BINANCE_API_KEY=your_binance_key_here
BINANCE_API_SECRET=your_binance_secret_here

# Bitget
BITGET_API_KEY=your_bitget_key_here
BITGET_API_SECRET=your_bitget_secret_here
BITGET_PASSPHRASE=your_bitget_passphrase_here

# Bybit
BYBIT_API_KEY=your_bybit_key_here
BYBIT_API_SECRET=your_bybit_secret_here

# 其他 DEX（如果需要）
# LIGHTER_API_KEY=...
# EDGEX_API_KEY=...
# 等等
```

---

## 📚 详细配置指南

需要详细步骤？查看 [CREDENTIALS_SETUP_GUIDE.md](CREDENTIALS_SETUP_GUIDE.md)

每个交易所都有：
- 获取凭证的网址
- 详细的步骤说明
- 安全建议
- 故障排查

---

## 🎯 推荐配置顺序

### 第 1 步：配置 OKX（最安全）
```bash
# OKX 使用 Demo Trading，不会影响真实资金
bash setup_credentials.sh
# 填入 OKX 凭证
```

### 第 2 步：测试 OKX
```bash
python test_exchanges.py okx
```

### 第 3 步：添加 Binance
```bash
# 编辑 .env，添加 Binance 凭证
nano .env

# 测试
python test_exchanges.py binance
```

### 第 4 步：测试已配置的所有交易所
```bash
python test_exchanges.py --list
python test_exchanges.py --all
```

---

## ✨ 开始使用

```bash
# Step 1: 使用脚本配置
bash setup_credentials.sh

# Step 2: 验证配置
python test_exchanges.py --list

# Step 3: 测试 OKX
python test_exchanges.py okx

# Step 4: 测试所有交易所
python test_exchanges.py --all
```

---

**准备好配置了？** 运行 `bash setup_credentials.sh` 🚀
