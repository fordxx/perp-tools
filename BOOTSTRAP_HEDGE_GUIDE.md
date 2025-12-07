# Bootstrap 双交易所对冲系统使用指南

## ✅ 系统概述

这是一个最小化的 **Binance + OKX 双交易所对冲验证系统**，用于验证：

- ✅ 真实 API 连接是否稳定
- ✅ 双边下单是否同步
- ✅ 双边平仓是否可控
- ✅ PnL 计算是否正确

## 🎯 对冲流程

```
1. 获取双边价格 (Binance, OKX)
   ↓
2. 同时开仓 (MARKET)
   - Binance: 做多 BTC/USDT
   - OKX: 做空 BTC/USDT
   ↓
3. 持仓 N 秒 (默认 10 秒)
   ↓
4. 同时平仓 (MARKET)
   - Binance: 卖出平多
   - OKX: 买入平空
   ↓
5. 计算 PnL
   - Binance PnL = (平仓价 - 开仓价) × 数量
   - OKX PnL = (开仓价 - 平仓价) × 数量
   - 总 PnL = Binance PnL + OKX PnL
```

---

## 📋 环境配置

### 1. Binance Testnet 配置

1. 访问：https://testnet.binancefuture.com/
2. 注册并生成 API Key

### 2. OKX Demo Trading 配置

1. 访问：https://www.okx.com/
2. 注册账号
3. 开启 Demo Trading（模拟交易）
4. 生成 API Key, Secret, Passphrase

### 3. 环境变量配置

创建或编辑 `.env` 文件：

```bash
# Binance USDT-M Testnet
BINANCE_API_KEY=your_binance_testnet_api_key
BINANCE_API_SECRET=your_binance_testnet_api_secret
BINANCE_ENV=testnet

# OKX Demo Trading
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_api_secret
OKX_PASSPHRASE=your_okx_passphrase
OKX_ENV=testnet
```

⚠️ **重要**：
- 只填写 Testnet/Demo Trading 密钥
- 绝对不要填写主网密钥

---

## 🧪 运行测试

### 方式 1: 直接运行 Bootstrap 脚本（推荐）

```bash
python run_bootstrap_hedge.py
```

### 方式 2: 使用 Python 脚本

```python
from bootstrap.hedge_executor import BootstrapHedgeExecutor, HedgeConfig
from perpbot.exchanges.binance import BinanceClient
from perpbot.exchanges.okx import OKXClient

# 连接交易所
binance = BinanceClient(use_testnet=True)
binance.connect()

okx = OKXClient(use_testnet=True)
okx.connect()

# 配置对冲参数
config = HedgeConfig(
    symbol="BTC/USDT",
    notional_usdt=300.0,           # 名义金额
    max_position_duration_seconds=10.0,  # 持仓时间
)

# 执行对冲
executor = BootstrapHedgeExecutor(binance, okx, config)
result = executor.execute_hedge_cycle()

# 查看结果
if result.success:
    print(f"✅ Total PnL: ${result.total_pnl:.2f}")
else:
    print(f"❌ Error: {result.error_message}")
```

---

## 📊 执行输出示例

```
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀
Bootstrap 双交易所对冲系统
🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀🚀

============================================================
Connecting to Exchanges
============================================================
✅ Binance USDT-M Testnet connected (sandbox=True, trading=True)
🧪 API URL: https://testnet.binancefuture.com
✅ OKX Demo Trading connected (x-simulated-trading=1, trading=True)
🧪 Demo mode: Enabled

============================================================
Bootstrap Hedge Executor Initialized
============================================================
Exchange A: binance
Exchange B: okx
Symbol: BTC/USDT
Notional: 300.00 USDT
============================================================

============================================================
Step 1: Fetching Prices
============================================================
Prices: binance=96234.50, okx=96235.20

============================================================
Step 2: Opening Hedge Positions (MARKET)
============================================================
Placing orders simultaneously...
✅ Orders filled:
   binance: BUY 0.0031 @ 96234.50 (OrderID: 12345678)
   okx: SELL 0.0031 @ 96235.20 (OrderID: 87654321)
   Latency: 345 ms

============================================================
Step 3: Holding Position for 10.0 seconds
============================================================

============================================================
Step 4: Closing Positions (MARKET)
============================================================
Prices: binance=96250.00, okx=96248.50
Closing positions simultaneously...
✅ Positions closed:
   binance: SELL 0.0031 @ 96250.00 (OrderID: 23456789)
   okx: BUY 0.0031 @ 96248.50 (OrderID: 98765432)

============================================================
Step 5: Calculating PnL
============================================================
binance PnL: $0.05
okx PnL: -$0.04
Total PnL: $0.01

============================================================
✅ HEDGE CYCLE COMPLETED SUCCESSFULLY
============================================================

🎉 双交易所对冲测试成功完成！
```

---

## 🔧 配置参数说明

### HedgeConfig 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `symbol` | "BTC/USDT" | 交易对 |
| `notional_usdt` | 300.0 | 单笔名义金额（USDT） |
| `max_slippage_bps` | 5.0 | 最大滑点（基点，0.05%） |
| `max_position_duration_seconds` | 10.0 | 最大持仓时间（秒） |
| `max_order_latency_ms` | 800.0 | 单边未成交超时（毫秒） |
| `max_acceptable_loss_pct` | 0.2 | 最大可接受亏损（%） |

---

## 🔒 安全机制

### 1. 强制 Testnet/Demo 模式

**Binance**:
- ✅ `set_sandbox_mode(True)`
- ✅ URL 验证：`testnet.binancefuture.com`

**OKX**:
- ✅ `x-simulated-trading: 1` header
- ✅ Demo Trading 强制启用

### 2. 自动回滚

如果任一交易所下单失败：
- ✅ 立即平掉已成交的仓位
- ✅ 避免单边风险

### 3. 延迟检测

如果双边下单延迟过高（> 800ms）：
- ⚠️ 记录警告
- ⚠️ 继续执行（但标记风险）

---

## ⚠️ 风险提示

### 可能的风险

1. **价格波动**
   - 持仓期间价格可能大幅波动
   - 对冲不一定完全对冲价格风险

2. **滑点**
   - MARKET 订单可能有滑点
   - 实际成交价格可能偏离盘口价

3. **延迟**
   - 双边下单可能不完全同步
   - 网络延迟可能导致时间差

4. **单边成交**
   - 一方成交，另一方失败
   - 系统会自动回滚

### 对策

- ✅ 小额测试（默认 300 USDT）
- ✅ 短持仓时间（默认 10 秒）
- ✅ 自动回滚机制
- ✅ 最大亏损限制（0.2%）

---

## 📝 成功标准

对冲测试成功需满足：

1. ✅ 能真实成交（Binance + OKX）
2. ✅ 能真实平仓
3. ✅ 能看到资金变化
4. ✅ 不爆仓
5. ✅ 手动中断（Ctrl+C）立即生效
6. ✅ 任意异常可退出

---

## 🚀 下一步

### 完成 Bootstrap 后的升级路线

1. **优化执行**
   - 加入 Maker / Taker 智能选择
   - 优化滑点控制

2. **增加风控**
   - 价差检查
   - 资金费率检查
   - 波动率检查

3. **扩展功能**
   - 三层资金模型（S1/S2/S3）
   - 多交易所调度
   - 刷量策略

4. **自动化**
   - 机会扫描
   - 自动执行
   - 风控熔断

---

## 📚 相关文档

- [BINANCE_TESTNET_SETUP.md](./BINANCE_TESTNET_SETUP.md) - Binance 设置
- [perpbot-important-architecture.md](./perpbot-important-architecture.md) - 工程哲学
- [docs/bootstrap-hedge-v1.md](./docs/bootstrap-hedge-v1.md) - Bootstrap 设计

---

**最后更新**: 2025-12-07
**状态**: ✅ Bootstrap 双交易所对冲系统就绪
**测试**: ⏸️ 等待用户验证
