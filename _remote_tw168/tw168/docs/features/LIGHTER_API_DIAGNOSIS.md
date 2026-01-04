# Lighter API 认证问题诊断

## 🚨 当前问题

```
⚠️ Lighter SignerClient 检查失败（将以只读模式运行）:
failed to get Api Keys. err: {"code":21109,"message":"api key not found"} on api key 2
```

**含义**: Lighter 平台上找不到 `api_key_index=2` 的 API key

## 📋 当前配置

从 `.env` 文件：
```
LIGHTER_ENV=mainnet
LIGHTER_API_KEY_PRIVATE_KEY=aae3e17485e6e3dc5a84f238ad0c4a7041c73345fe77c96cdc950450d0e26f255017197d00d65a11
LIGHTER_ACCOUNT_INDEX=1
LIGHTER_API_KEY_INDEX=2
LIGHTER_API_KEY=c0f2acf461cebd892a88541aaf41bc8039811543ab338b27b66a8edeb63e803bd156d9e3f7fa69be
```

## 🔍 问题原因

可能的原因：
1. **API key 已被删除** - 在 Lighter 平台上删除了 index=2 的 API key
2. **Index 错误** - 实际的 API key index 不是 2（可能是 0 或 1）
3. **Account 错误** - account_index=1 不正确
4. **环境错误** - 配置的是 testnet 的 key，但连接的是 mainnet

## 🛠️ 解决方案

### 方案 1: 检查 Lighter 平台上的 API Keys

1. 访问 https://app.lighter.xyz
2. 连接钱包
3. 进入 Settings → API Keys
4. 查看有哪些 API keys 及其 index

**需要确认**：
- Account Address: 是否匹配 `account_index=1`
- API Key Index: 实际的 index 是多少（0, 1, 2?）
- API Key Status: 是否 Active

### 方案 2: 尝试其他 Index

修改 `.env` 文件，尝试 index 0 或 1：

```bash
# 尝试 index=0
LIGHTER_API_KEY_INDEX=0

# 或 index=1
LIGHTER_API_KEY_INDEX=1
```

### 方案 3: 重新生成 API Key

如果 API key 已失效或被删除：

1. 在 Lighter 平台删除旧的 API key
2. 生成新的 API key
3. 更新 `.env`:
   ```
   LIGHTER_API_KEY_PRIVATE_KEY=<新的私钥>
   LIGHTER_ACCOUNT_INDEX=<账户 index>
   LIGHTER_API_KEY_INDEX=<新的 key index>
   ```

### 方案 4: 使用不同的认证方式

Lighter SDK 可能支持其他认证方式，查看文档。

## 🧪 诊断测试

运行以下命令测试不同的配置：

### 测试 Index 0
```bash
docker compose exec -T tv-okx python3 << EOF
import sys
sys.path.insert(0, "/src")
from lighter.lighter_client import SignerClient

# 测试 index=0
try:
    client = SignerClient(
        url="https://api.lighter.xyz",
        account_index=1,
        api_private_keys={0: "aae3e17485e6e3dc5a84f238ad0c4a7041c73345fe77c96cdc950450d0e26f255017197d00d65a11"}
    )
    err = client.check_client()
    if err:
        print(f"❌ Index 0 失败: {err}")
    else:
        print("✅ Index 0 成功!")
except Exception as e:
    print(f"❌ Index 0 异常: {e}")
EOF
```

### 测试 Index 1
```bash
docker compose exec -T tv-okx python3 << EOF
import sys
sys.path.insert(0, "/src")
from lighter.lighter_client import SignerClient

# 测试 index=1
try:
    client = SignerClient(
        url="https://api.lighter.xyz",
        account_index=1,
        api_private_keys={1: "aae3e17485e6e3dc5a84f238ad0c4a7041c73345fe77c96cdc950450d0e26f255017197d00d65a11"}
    )
    err = client.check_client()
    if err:
        print(f"❌ Index 1 失败: {err}")
    else:
        print("✅ Index 1 成功!")
except Exception as e:
    print(f"❌ Index 1 异常: {e}")
EOF
```

## 📊 测试影响

**当前状态**: Lighter 客户端以**只读模式**运行

**影响**：
- ✅ 可以查询价格
- ✅ 可以查询订单簿
- ✅ 可以查询持仓（公开数据）
- ❌ **无法下单**
- ❌ **无法撤单**
- ❌ **无法执行任何交易操作**

**结论**: 在修复认证之前，**无法进行任何真实交易测试**！

## 🎯 下一步行动

### 选项 A: 修复 Lighter 认证（推荐）
1. 访问 Lighter 平台检查 API keys
2. 找到正确的 index
3. 更新 `.env` 配置
4. 重启服务
5. 继续真实交易测试

### 选项 B: 切换到 OKX 测试
如果 Lighter 认证修复复杂，可以先用 OKX 测试：

```bash
# 修改 .env
EXCHANGE=okx  # 从 lighter 改为 okx

# 重启服务
docker compose restart
```

OKX 的认证应该是正常的（之前能工作）。

### 选项 C: 暂停测试
等待用户提供 Lighter API key 信息或手动修复。

## 📝 临时解决方案

**如果无法立即修复 Lighter 认证**，可以：
1. 保持当前只读模式
2. 等待真实 TradingView 信号
3. 观察系统尝试交易时的错误
4. 记录问题

**风险**: 收到信号但无法交易（错过机会）

---

**当前建议**: 需要用户登录 Lighter 平台检查 API key 配置，或切换到 OKX 进行测试。
