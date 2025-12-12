# 🔐 交易所凭证配置指南

**最后更新**: 2024-12-12  
**支持交易所**: 13 个  

---

## ⚡ 快速配置（3 种方式）

### 方式 1️⃣: 编辑 .env 文件（推荐）
```bash
# 第一次使用时复制示例
cp .env.example .env

# 编辑配置文件
nano .env
```

### 方式 2️⃣: 使用环境变量
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

### 方式 3️⃣: 一行命令
```bash
OKX_API_KEY="key" OKX_API_SECRET="secret" OKX_PASSPHRASE="pass" python test_exchanges.py okx
```

---

## 🌍 所有交易所凭证配置

### 已配置的交易所（3 个）✅

#### 5. Hyperliquid ✅
```bash
# 可选凭证（如果需要特定账户）
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
HYPERLIQUID_ACCOUNT_ADDRESS=0xYourAddress
```

#### 6. Paradex ✅
```bash
# 必需（L2 私钥来自 Starknet 钱包）
PARADEX_L2_PRIVATE_KEY=0xyour_l2_private_key_here
PARADEX_ACCOUNT_ADDRESS=0xYourStarknetWalletAddress
```

#### 7. Extended ✅
```bash
# 必需
EXTENDED_API_KEY=your_api_key
EXTENDED_STARK_PRIVATE_KEY=0xyour_stark_private_key
EXTENDED_VAULT_NUMBER=your_vault_number
```

---

### 需要配置的交易所（10 个）❌

#### 1. OKX (CEX - Demo Trading)
**获取方式**: https://www.okx.com/account/my-api

```env
# 必需
OKX_API_KEY=your_okx_api_key_here
OKX_API_SECRET=your_okx_api_secret_here
OKX_PASSPHRASE=your_okx_passphrase_here
```

**步骤**:
1. 登录 OKX 账户
2. 进入 **账户 → API**
3. 点击 **创建 API Key**
4. 选择权限：**只读**（推荐）
5. 复制 API Key、Secret、Passphrase

⚠️ **重要**: OKX 强制使用 Demo Trading 模式，不会影响真实资金

---

#### 2. Binance (CEX)
**获取方式**: https://www.binance.com/en/account/api-management

```env
# 必需
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_API_SECRET=your_binance_api_secret_here
```

**步骤**:
1. 登录 Binance 账户
2. 进入 **账户 → API**
3. 点击 **Create API**
4. 选择权限：**只读** + **现货交易**（小额）
5. 设置 IP 白名单（推荐）
6. 复制 API Key 和 Secret

⚠️ **推荐**: 使用 IP 白名单限制 API 访问

---

#### 3. Bitget (CEX)
**获取方式**: https://www.bitget.com/en/user/account/apimanagement

```env
# 必需
BITGET_API_KEY=your_bitget_api_key_here
BITGET_API_SECRET=your_bitget_api_secret_here
BITGET_PASSPHRASE=your_bitget_passphrase_here
```

**步骤**:
1. 登录 Bitget 账户
2. 进入 **账户 → API 管理**
3. 点击 **新建 API Key**
4. 选择权限：**只读**
5. 复制 API Key、Secret、Passphrase

---

#### 4. Bybit (CEX)
**获取方式**: https://www.bybit.com/en/user/api-management

```env
# 必需
BYBIT_API_KEY=your_bybit_api_key_here
BYBIT_API_SECRET=your_bybit_api_secret_here

# 可选
BYBIT_UID=your_uid
```

**步骤**:
1. 登录 Bybit 账户
2. 进入 **账户 → API**
3. 点击 **创建新密钥**
4. 选择权限：**只读**
5. 复制 API Key 和 Secret

---

#### 8. Lighter (DEX - Ethereum L2)
**获取方式**: https://lighter.xyz

```env
# 必需
LIGHTER_API_KEY=your_lighter_api_key_here
LIGHTER_PRIVATE_KEY=0xyour_ethereum_private_key
```

**步骤**:
1. 访问 Lighter.xyz
2. 连接钱包
3. 进入 **设置 → API**
4. 创建 API Key
5. 导出私钥（来自 MetaMask 或其他钱包）

⚠️ **警告**: 私钥需要妥善保管！

---

#### 9. EdgeX (DEX)
**获取方式**: https://app.edgex.exchange

```env
# 必需
EDGEX_API_KEY=your_edgex_api_key_here

# 可选
EDGEX_API_SECRET=your_edgex_api_secret_here
```

**步骤**:
1. 访问 EdgeX
2. 连接钱包
3. 进入 **设置 → API Keys**
4. 创建新 API Key

---

#### 10. Backpack (DEX - Solana)
**获取方式**: https://backpack.app

```env
# 必需
BACKPACK_API_KEY=your_backpack_api_key_here
BACKPACK_API_SECRET=your_backpack_api_secret_here
```

**步骤**:
1. 访问 Backpack
2. 连接 Solana 钱包
3. 进入 **设置 → API**
4. 生成新密钥对

---

#### 11. GRVT (DEX - Ethereum L2)
**获取方式**: https://grvt.io

```env
# 必需
GRVT_API_KEY=your_grvt_api_key_here
```

**步骤**:
1. 访问 GRVT
2. 进入 **账户 → API**
3. 创建新 API Key

---

#### 12. Aster (DEX - Solana)
**获取方式**: https://aster.exchange

```env
# 必需
ASTER_API_KEY=your_aster_api_key_here
```

**步骤**:
1. 访问 Aster
2. 进入 **设置 → API**
3. 生成新 Key

---

#### 13. Sunx (DEX)
**获取方式**: https://sunx.exchange (待确认)

```env
# 必需
SUNX_API_KEY=your_sunx_api_key_here

# 可选
SUNX_API_SECRET=your_sunx_api_secret_here
```

**步骤**:
1. 访问 Sunx
2. 进入 **账户 → API**
3. 创建新 API Key

---

## 🛠️ 配置方式详细步骤

### 方式 A: 直接编辑 .env 文件

#### 第 1 步：复制示例文件
```bash
cd /home/fordxx/perp-tools
cp .env.example .env
```

#### 第 2 步：编辑文件
```bash
nano .env
```

或使用 VS Code:
```bash
code .env
```

#### 第 3 步：添加凭证
```env
# OKX
OKX_API_KEY=pk_xxxxx
OKX_API_SECRET=sk_xxxxx
OKX_PASSPHRASE=pass_xxxxx

# Binance
BINANCE_API_KEY=xxx
BINANCE_API_SECRET=yyy

# 其他交易所...
```

#### 第 4 步：保存并测试
```bash
python test_exchanges.py okx
```

---

### 方式 B: 使用脚本快速配置

创建 `setup_credentials.sh`:
```bash
#!/bin/bash

# OKX
read -p "OKX API Key: " okx_key
read -p "OKX API Secret: " okx_secret
read -p "OKX Passphrase: " okx_pass

echo "OKX_API_KEY=$okx_key" >> .env
echo "OKX_API_SECRET=$okx_secret" >> .env
echo "OKX_PASSPHRASE=$okx_pass" >> .env

# Binance
read -p "Binance API Key: " binance_key
read -p "Binance API Secret: " binance_secret

echo "BINANCE_API_KEY=$binance_key" >> .env
echo "BINANCE_API_SECRET=$binance_secret" >> .env

echo "✅ 凭证已保存到 .env"
```

运行:
```bash
chmod +x setup_credentials.sh
./setup_credentials.sh
```

---

## ✅ 验证凭证配置

### 查看哪些交易所已配置
```bash
python test_exchanges.py --list
```

输出示例:
```
   1. okx             | ✅ 已配置      | DEMO   
   2. binance         | ❌ 缺凭证      | 主网     
   ...
   5. hyperliquid     | ✅ 已配置      | 主网     
```

### 测试特定交易所
```bash
# 测试 OKX
python test_exchanges.py okx

# 输出：
# ✅ Connected (45ms)
# ✅ Price: 99000.50-99001.50 (120ms)
# ✅ Orderbook: 5 bids, 5 asks (95ms)
```

---

## 🔐 安全建议

### 1️⃣ API Key 权限
- ✅ **使用只读权限** - 不要给予交易权限
- ❌ 避免给予提币权限
- ❌ 避免给予账户修改权限

### 2️⃣ IP 白名单
```
设置 IP 白名单为:
- 本地: 127.0.0.1
- 或限制到你的固定 IP
```

### 3️⃣ Key 轮换
```bash
# 定期（每月）轮换 API Key：
1. 在交易所生成新 Key
2. 更新 .env 文件
3. 删除旧 Key
4. 测试新 Key
```

### 4️⃣ 凭证保护
```bash
# .env 文件必须在 .gitignore 中
cat .gitignore | grep .env

# 确保输出包含：
# .env
# .env.local
# *.key
```

---

## 📋 推荐配置计划

### 快速开始（5 分钟）
```bash
# 只配置 Hyperliquid（已有凭证）
python test_exchanges.py hyperliquid
```

### 基础配置（15 分钟）
```bash
# 添加 OKX (Demo Trading 最安全)
# + Binance (世界最大交易所)
python test_exchanges.py okx binance
```

### 完整配置（1 小时）
```bash
# 配置所有 13 个交易所
python test_exchanges.py --all --verbose
```

---

## 🚨 常见问题

### Q: 凭证在哪里存储？
A: 在 `.env` 文件中（不要提交到 Git）

### Q: 如何更换凭证？
A: 编辑 `.env` 文件，保存后立即生效

### Q: 凭证会泄露吗？
A: 只要 `.env` 在 `.gitignore` 中就安全

### Q: 可以使用多个账户吗？
A: 可以，但需要在代码中修改变量名

### Q: 忘记了 API Key 怎么办？
A: 在交易所网站重新生成或查看

---

## 🔧 故障排查

### 错误：Missing env vars
```
⚠️ Missing env vars: OKX_API_KEY
```

**解决**:
```bash
# 检查 .env 文件
cat .env | grep OKX

# 确保已添加凭证
echo $OKX_API_KEY  # 应该显示你的 key
```

### 错误：Invalid API key
```
❌ Invalid API key
```

**解决**:
1. 检查 Key 是否正确复制（无空格）
2. 检查 Key 是否过期
3. 检查 IP 白名单是否包含你的 IP

### 错误：Authentication failed
```
❌ Authentication failed
```

**解决**:
1. 检查 Secret 是否正确
2. 确保 Passphrase（如果需要）正确
3. 检查交易所 API 是否已启用

---

## 📊 配置检查清单

```
凭证配置清单
═════════════════════════════════════

□ 已复制 .env.example → .env
□ 已在 .gitignore 中检查 .env
□ 已配置 OKX
  □ API Key
  □ API Secret
  □ Passphrase
□ 已配置 Binance
  □ API Key
  □ API Secret
□ 已配置其他交易所
□ 已验证 --list 显示 ✅
□ 已测试 python test_exchanges.py okx
□ 已设置 IP 白名单
□ 已确认权限为只读
```

---

## 🎯 快速命令

```bash
# 查看 .env 文件
cat .env

# 查看特定凭证
grep OKX .env

# 编辑 .env
nano .env

# 验证配置
python test_exchanges.py --list

# 测试 OKX
python test_exchanges.py okx

# 测试所有
python test_exchanges.py --all
```

---

**记住**: 
- ✅ `.env` 文件包含真实凭证，**不要分享**
- ✅ 定期检查 API 日志
- ✅ 使用只读权限
- ✅ 设置 IP 白名单

**准备好了?** 运行 `python test_exchanges.py --list` 查看配置状态 🚀
