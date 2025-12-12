# 🚀 快速测试指南 - 5 分钟上手

## 第一步：验证环境

```bash
# 查看所有支持的交易所
python test_exchanges.py --list
```

**输出示例：**
```
🌍 支持的交易所 (生产级)
  1. okx             | ❌ 缺凭证      | DEMO   
  2. binance         | ❌ 缺凭证      | 主网     
  ...
  5. hyperliquid     | ✅ 已配置      | 主网     
  6. paradex         | ✅ 已配置      | 主网     
  7. extended        | ✅ 已配置      | 主网     
  ...
```

✅ **已配置 = 已有环境变量，可以立即测试**

---

## 第二步：选择并测试交易所

### 方式 1️⃣：交互式选择 (推荐)
```bash
python test_exchanges.py
```

**按提示输入：**
```
请选择 (或输入 q 退出): 5 6 7
```

### 方式 2️⃣：直接指定交易所名称
```bash
# 测试单个
python test_exchanges.py hyperliquid

# 测试多个
python test_exchanges.py hyperliquid paradex extended
```

### 方式 3️⃣：快捷方式
```bash
# 测试所有 CEX
python test_exchanges.py --cex

# 测试所有 DEX
python test_exchanges.py --dex

# 测试所有交易所
python test_exchanges.py --all
```

---

## 第三步：配置新交易所 (可选)

如果想测试未配置的交易所（如 OKX、Binance），需要设置 API 凭证：

```bash
# 编辑 .env 文件
nano .env

# 或使用 export 命令
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_API_PASSPHRASE="your_passphrase"
```

**然后立即测试：**
```bash
python test_exchanges.py okx
```

---

## 📊 实时输出示例

```
======================================================================
Testing HYPERLIQUID
======================================================================
1️⃣ Testing connection...
   ✅ Connected (45ms)
2️⃣ Testing price (BTC/USDT)...
   ✅ Price: 99000.50-99001.50 (120ms)
3️⃣ Testing orderbook (BTC/USDT)...
   ✅ Orderbook: 5 bids, 5 asks (95ms)
4️⃣ Testing account balances...
   ✅ Found 3 balances (180ms)
   - USDT: 1000.50 free
   - BTC: 0.01 free
5️⃣ Testing positions...
   ✅ Found 2 positions (150ms)

✅ HYPERLIQUID test completed
```

---

## 🎯 常见命令

| 命令 | 用途 |
|------|------|
| `python test_exchanges.py --list` | 列出所有交易所 |
| `python test_exchanges.py` | 交互式选择 |
| `python test_exchanges.py hyperliquid paradex` | 测试指定交易所 |
| `python test_exchanges.py --cex` | 测试所有 CEX |
| `python test_exchanges.py --dex` | 测试所有 DEX |
| `python test_exchanges.py okx --verbose` | 详细日志 |
| `python test_exchanges.py --all --json-report report.json` | 完整报告 |

---

## 💾 已配置的交易所

✅ **立即可用：**
- `hyperliquid` - Hyperliquid 永续交易
- `paradex` - Paradex DEX
- `extended` - Extended DEX

❌ **需要 API Key：**
- `okx` - OKX 交易所
- `binance` - Binance 交易所
- `bitget` - Bitget 交易所
- `bybit` - Bybit 交易所
- 其他 DEX...

---

## 🔧 故障排查

### 问题：缺少模块
```
Failed to import: No module named 'httpx'
```

**解决：**
```bash
pip install -r requirements.txt
```

### 问题：缺少凭证
```
❌ Missing env vars: HYPERLIQUID_PRIVATE_KEY
```

**解决：**
添加凭证到 `.env` 文件。参考 `.env.example`。

### 问题：连接超时
```
Connection timeout
```

**解决：**
- 检查网络连接
- 检查 API 端点是否可用
- 确认 IP 白名单配置

---

## 📚 更多文档

- **完整指南**: [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md)
- **配置详解**: [EXCHANGES_CONFIG_GUIDE.md](EXCHANGES_CONFIG_GUIDE.md)
- **源代码**: [test_exchanges.py](test_exchanges.py)

---

## 💡 提示

1. **首次运行** → 执行 `python test_exchanges.py --list` 了解情况
2. **测试已有凭证** → 运行 `python test_exchanges.py hyperliquid`
3. **添加新交易所** → 编辑 `.env`，然后运行测试
4. **保存报告** → 使用 `--json-report report.json`

**祝测试顺利！** 🚀
