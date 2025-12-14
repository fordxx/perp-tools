# 🚀 PerpBot 交易所测试框架 - 完整演示

**最后更新**: 2024-12-12  
**框架版本**: 2.0 (生产级)  
**支持交易所**: 12 个 (4 CEX + 8 DEX)  
**测试模式**: 主网 + 交互式选择

---

## 🎬 5 分钟快速开始

### 1️⃣ 第一次运行 - 查看所有交易所
```bash
python test_exchanges.py --list
```

**输出：**
```
🌍 支持的交易所 (生产级)
   1. okx             | ❌ 缺凭证      | DEMO   
   2. binance         | ❌ 缺凭证      | 主网     
   3. bitget          | ❌ 缺凭证      | 主网     
   4. bybit           | ❌ 缺凭证      | 主网     
   5. hyperliquid     | ✅ 已配置      | 主网     
   6. paradex         | ✅ 已配置      | 主网     
   7. extended        | ✅ 已配置      | 主网     
   8. lighter         | ❌ 缺凭证      | 主网     
   9. edgex           | ❌ 缺凭证      | 主网     
  10. backpack        | ❌ 缺凭证      | 主网     
  11. grvt            | ❌ 缺凭证      | 主网     
  12. aster           | ❌ 缺凭证      | 主网     
```

### 2️⃣ 运行测试 - 交互式选择
```bash
python test_exchanges.py
```

**提示您输入：**
```
请选择 (或输入 q 退出): 5 6 7
```

✅ **自动测试 hyperliquid, paradex, extended**

### 3️⃣ 查看结果
```
✅ hyperliquid test completed
✅ paradex test completed
✅ extended test completed

📊 TEST SUMMARY
Total: 3 exchanges
✅ Passed: 3
❌ Failed: 0
⏱️ Duration: 2.3s
```

---

## 📚 所有使用方式

### A. 交互式模式（推荐）

#### 方式 1: 基本交互
```bash
python test_exchanges.py
```

**输入示例：**
```
请选择: 1        # 选择第 1 个
请选择: 1 3 5    # 选择多个
请选择: 1-5      # 选择范围
请选择: all      # 全部
请选择: cex      # 仅 CEX
请选择: dex      # 仅 DEX
请选择: q        # 退出
```

#### 方式 2: 直接使用 --select
```bash
python test_exchanges.py --select
```
（功能同上）

### B. 命令行直接指定

#### 测试单个交易所
```bash
python test_exchanges.py hyperliquid
```

#### 测试多个交易所
```bash
python test_exchanges.py hyperliquid paradex extended
python test_exchanges.py okx binance hyperliquid
```

#### 按编号指定
```bash
python test_exchanges.py --select 5 6 7
```

### C. 快捷方式

#### 测试所有 CEX（中心化交易所）
```bash
python test_exchanges.py --cex

# 等价于：
python test_exchanges.py okx binance bitget bybit
```

#### 测试所有 DEX（去中心化）
```bash
python test_exchanges.py --dex

# 等价于：
python test_exchanges.py hyperliquid paradex extended lighter edgex backpack grvt aster
```

#### 测试所有交易所
```bash
python test_exchanges.py --all

# 等价于测试全部 12 个
```

### D. 高级选项

#### 自定义交易对
```bash
# 测试 ETH/USDT 而不是默认 BTC/USDT
python test_exchanges.py okx --symbol ETH/USDT
python test_exchanges.py --cex --symbol SOL/USDT
```

#### 详细日志
```bash
# 显示每一步的调试信息
python test_exchanges.py hyperliquid --verbose

# 示例输出：
# 23:05:20 | hyperliquid     | DEBUG   | Connecting...
# 23:05:21 | hyperliquid     | DEBUG   | Connected, fetching price
# 23:05:21 | hyperliquid     | INFO    | Price: 99000.50
```

#### 输出 JSON 报告
```bash
# 生成可机读的测试报告
python test_exchanges.py --all --json-report report.json

# 查看报告
cat report.json | jq .

# 示例内容：
# {
#   "test_time": "2024-12-12T23:05:20",
#   "duration_seconds": 5.23,
#   "total_exchanges": 12,
#   "passed_exchanges": 3,
#   "failed_exchanges": 9,
#   "metrics": [...]
# }
```

#### 包含交易测试（谨慎！）
```bash
# 执行小额实际交易
python test_exchanges.py okx --trading

# ⚠️ 警告：这会执行真实订单
# 仅在理解风险的情况下使用
```

---

## 🎯 常见场景

### 场景 1: 快速验证连接
```bash
# 测试 3 个已配置的交易所
python test_exchanges.py hyperliquid paradex extended

# 时间：< 3 秒
```

### 场景 2: 批量测试 CEX
```bash
# 需要先配置 API Keys
export OKX_API_KEY="..."
export BINANCE_API_KEY="..."

python test_exchanges.py --cex
```

### 场景 3: 性能基准测试
```bash
# 测试所有交易所的响应延迟
python test_exchanges.py --all --verbose --json-report bench.json

# 分析报告
python << 'EOF'
import json
with open('bench.json') as f:
    data = json.load(f)
    for m in data['metrics']:
        print(f"{m['exchange']:15} | Connection: {m['connection_time_ms']:6.1f}ms | Price: {m['price_time_ms']:6.1f}ms")
EOF
```

### 场景 4: 监控脚本
```bash
#!/bin/bash
# 每 5 分钟测试一次所有交易所

while true; do
    echo "[$(date)] Running exchange tests..."
    python test_exchanges.py --all \
        --json-report logs/report_$(date +%s).json \
        --verbose >> logs/monitor.log 2>&1
    
    sleep 300
done
```

### 场景 5: 添加新交易所
```bash
# 1. 配置凭证
echo "BINANCE_API_KEY=your_key" >> .env

# 2. 立即测试
python test_exchanges.py binance

# 3. 监控成功率
python test_exchanges.py --all --json-report report.json
```

---

## 🧪 连接 → 下单 → 关单 三部曲

为了验证交易所连接、下单和关仓能力，我们推荐结合自动化模式和交互式菜单，按照以下顺序逐步走通核心链路。

### 1️⃣ 连接健康检查
```
python test_exchanges.py hyperliquid paradex extended --auto-test
```
该命令会分别输出连接、价格、订单簿、账户、持仓等步骤的响应时间：

```
1️⃣ Testing connection...
   ✅ Connected (42ms)
2️⃣ Testing price...
   ✅ Price: 0.25-0.26 (71ms)
3️⃣ Testing orderbook...
   ✅ Bids: 5 / Asks: 5 (58ms)
...
✅ PARADex test completed
```

如果需要更细致指标，可以添加 `--json-report bench.json`，再用 `jq`/Python 读取 `connection_time_ms`、`price_time_ms` 等字段。

### 2️⃣ 限价单 + 撤单
启用了 `--trading` 后，脚本自动执行限价单 + 撤单流程：

```
python test_exchanges.py okx --auto-test --trading --trading-size 0.001
```

日志示例：

```
6️⃣ Testing limit order (BTC/USDT, size=0.001)...
   ✅ Order placed: ID=12345
   📍 Attempting to cancel order...
   ✅ Order cancelled: ID=12345
```

系统会在无法撤单时输出警告（`⚠️ Exchange does not support cancel_order`），避免交易断链。

### 3️⃣ 市价单 + 平仓
限价测试之后会依次执行市价单和 `place_close_order` 的验证：

```
7️⃣ Testing market/IOC order (BTC/USDT, size=0.001)...
   ✅ Market order placed: ID=54321, Price=45123.45

8️⃣ Testing close position (BTC/USDT)...
   ✅ Close order placed: ID=54322
```

如果没有对应持仓或缺少 `place_close_order` 方法，脚本会在日志中明确提示具体原因，便于补全。

### 4️⃣ 交互式菜单体验
想手动逐步验证也很简单：

```
python test_exchanges.py okx --symbol BTC/USDT
```

菜单里的 `5️⃣`/`6️⃣`/`7️⃣` 分别对应下限价单、下市价单、平仓，各操作会提示当前价格、订单 ID 和状态，是体验新版路线的最佳方式。

## 🔐 凭证配置

### 方式 1: 编辑 .env 文件
```bash
# 复制示例文件
cp .env.example .env

# 编辑
nano .env
```

**添加内容：**
```env
# OKX
OKX_API_KEY=your_api_key
OKX_API_SECRET=your_api_secret
OKX_API_PASSPHRASE=your_passphrase

# Binance
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret

# Hyperliquid (可选，已配置的可跳过)
HYPERLIQUID_PRIVATE_KEY=your_private_key
HYPERLIQUID_ACCOUNT_ADDRESS=your_account_address
```

### 方式 2: 使用环境变量
```bash
export OKX_API_KEY="your_key"
export OKX_API_SECRET="your_secret"
export OKX_API_PASSPHRASE="your_passphrase"

python test_exchanges.py okx
```

### 方式 3: 在脚本中设置
```bash
#!/bin/bash
export OKX_API_KEY="key"
export OKX_API_SECRET="secret"
export OKX_API_PASSPHRASE="passphrase"

python test_exchanges.py okx
```

---

## 📊 输出格式详解

### 标准测试输出
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
   - ETH: 1.00 free

5️⃣ Testing positions...
   ✅ Found 2 positions (150ms)

✅ HYPERLIQUID test completed
```

### 失败情况
```
======================================================================
Testing OKX
======================================================================
1️⃣ Testing connection...
   ❌ Failed to load client

⚠️ Missing env vars: OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE
```

### 汇总报告
```
======================================================================
📊 TEST SUMMARY
======================================================================
Total: 12 exchanges
✅ Passed: 3
❌ Failed: 9
⏱️ Duration: 0.5s

Exchange        Connection   Price        Orderbook    Balance      
-
hyperliquid     ✅           ✅           ✅           ✅           
paradex         ✅           ✅           ✅           ✅           
extended        ✅           ✅           ✅           ✅           
okx             ❌           ❌           ❌           ❌           
binance         ❌           ❌           ❌           ❌           
...
```

---

## 🐛 故障排查

### 错误：Missing module
```
Failed to import: No module named 'httpx'
```

**解决：**
```bash
pip install -r requirements.txt
```

### 错误：Missing env vars
```
⚠️ Missing env vars: HYPERLIQUID_PRIVATE_KEY
```

**解决：**
```bash
# 添加凭证到 .env
echo "HYPERLIQUID_PRIVATE_KEY=..." >> .env
```

### 错误：Connection timeout
```
❌ Connection timeout
```

**解决：**
```bash
# 检查网络
ping api.hyperliquid.com

# 或使用代理
export HTTP_PROXY=http://proxy:port
python test_exchanges.py
```

### 错误：Invalid API key
```
❌ Invalid API key
```

**解决：**
- 检查凭证是否正确
- 确认 API Key 未过期
- 检查账户 IP 白名单

---

## 💡 最佳实践

### 1. 首次使用
```bash
# Step 1: 查看可用交易所
python test_exchanges.py --list

# Step 2: 测试已配置的交易所
python test_exchanges.py hyperliquid

# Step 3: 配置新凭证
nano .env

# Step 4: 测试新交易所
python test_exchanges.py okx
```

### 2. 定期监控
```bash
# 创建监控脚本
cat > monitor.sh << 'EOF'
#!/bin/bash
while true; do
    python test_exchanges.py --all \
        --json-report logs/report_$(date +%s).json
    sleep 600  # 每 10 分钟
done
EOF

chmod +x monitor.sh
./monitor.sh &
```

### 3. 报告生成
```bash
# 完整报告
python test_exchanges.py --all \
    --verbose \
    --json-report full_report.json \
    --symbol BTC/USDT

# 快速报告
python test_exchanges.py --cex \
    --json-report cex_only.json
```

### 4. 故障诊断
```bash
# 使用详细日志
python test_exchanges.py okx --verbose

# 保存日志文件
python test_exchanges.py okx --verbose 2>&1 | tee debug.log
```

---

## 🔗 相关文档

- **快速指南**: [QUICK_TEST_GUIDE.md](QUICK_TEST_GUIDE.md)
- **完整指南**: [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md)
- **配置指南**: [EXCHANGES_CONFIG_GUIDE.md](EXCHANGES_CONFIG_GUIDE.md)
- **源代码**: [test_exchanges.py](test_exchanges.py)

---

## 🎓 学习资源

### 理解输入格式

| 输入 | 效果 |
|------|------|
| `5` | 选第 5 个 (hyperliquid) |
| `5 6 7` | 选第 5、6、7 个 |
| `5-8` | 选第 5-8 个 |
| `1 3 5-8` | 混合：第 1、3、5-8 个 |
| `all` | 所有 12 个 |
| `cex` | 前 4 个 (CEX) |
| `dex` | 后 8 个 (DEX) |

### 理解交易所分类

**CEX (中心化交易所)** - 1-4
- OKX - 提供 Demo Trading 安全测试
- Binance - 世界最大现货交易所
- Bitget - 创新交易所
- Bybit - 衍生品交易所

**DEX (去中心化交易所)** - 5-12
- Hyperliquid - Solana 上的永续合约
- Paradex - StarkNet DEX
- Extended - StarkNet DEX
- Lighter - Ethereum L2
- EdgeX - 多链 DEX
- Backpack - Solana 生态
- GRVT - Ethereum L2
- Aster - Solana DEX

---

## ✨ 核心特性

✅ **统一接口** - 所有交易所一致的 API  
✅ **无需 Testnet** - 直接主网小额测试  
✅ **交互式选择** - 灵活的数字/范围/快捷方式输入  
✅ **详细诊断** - 完整的错误信息和日志  
✅ **性能监控** - 各操作的延迟统计  
✅ **可扩展** - 轻松添加新交易所  
✅ **批量测试** - 同时测试多个交易所  
✅ **报告导出** - JSON 格式的完整报告  

---

**Ready to test? Run:** `python test_exchanges.py`

**Questions?** See [EXCHANGE_TEST_GUIDE.md](EXCHANGE_TEST_GUIDE.md)
