# 阶梯订单等待时间优化方案

## 背景

当前问题：阶梯订单使用限价单在入场价上下设置买卖单，但固定等待11秒太短，导致很多订单未成交就放弃。

核心矛盾：
- **限价单本质**：以更好的价格成交，需要等待价格回撤
- **DIV信号含义**：趋势可能已反转，价格可能不回撤
- **如何平衡**：既要抓住行情，又要优化成本

---

## 方案A：混合订单策略（推荐）

### 核心思路

部分市价单确保抓住行情 + 部分限价单优化成本

### 订单分配

```
市价单: 30%  # 立即成交，确保参与行情
限价L1: 35%  # 信号价 -5bps（买）/ +5bps（卖）
限价L2: 20%  # 信号价 -15bps
限价L3: 15%  # 信号价 -30bps
```

### 等待时间策略（按时间周期）

| 时间周期 | 基础等待 | 有成交延长到 | 价格远离阈值 |
|---------|---------|-------------|-------------|
| 1m      | 3根K线  | 5根K线      | 0.3% |
| 3m      | 2根K线  | 4根K线      | 0.4% |
| 5m      | 2根K线  | 3根K线      | 0.5% |
| 15m     | 1根K线  | 2根K线      | 0.6% |
| 30m     | 1根K线  | 2根K线      | 0.7% |
| 1h      | 1根K线  | 1.5根K线    | 0.8% |
| 4h      | 0.5根K线 | 1根K线     | 1.0% |

**逻辑**：
- **短周期（1m-5m）**：波动快，价格容易回撤，多等几根K线
- **中周期（15m-30m）**：趋势较明显，适度等待
- **长周期（1h-4h）**：趋势确认后很少回撤，快速决策

### 智能退出逻辑

```python
for retry in range(max_retries):
    await sleep(check_interval)

    # 1. 检查成交情况
    if total_filled_sz >= 30%:  # 市价单肯定成交了
        if total_filled_sz == 100%:
            # 全部成交
            break
        elif retry >= base_wait_candles:
            # 超过基础等待时间，有部分成交
            if retry < max_wait_candles:
                # 还没到最大等待，继续等
                continue
            else:
                # 到达最大等待，取消剩余订单
                cancel_unfilled_orders()
                break

    # 2. 价格远离检测
    current_price = get_current_price()
    l1_price = ladder_orders[0]["price"]
    distance_pct = abs(current_price - l1_price) / l1_price * 100

    if distance_pct > price_distance_threshold:
        # 价格已远离，限价单不太可能成交
        if total_filled_sz >= 30%:
            # 至少市价单成交了，取消剩余继续
            cancel_unfilled_orders()
            break
        else:
            # 不应该发生（市价单应该立即成交）
            # 但如果发生了，说明交易所有问题
            cancel_all_and_abort()
            return error
```

### 配置参数

```bash
# .env 配置
LADDER_MARKET_PCT=0.30                    # 市价单比例（30%）
LADDER_LIMIT_L1_PCT=0.35                  # 限价L1比例（35%）
LADDER_LIMIT_L2_PCT=0.20                  # 限价L2比例（20%）
LADDER_LIMIT_L3_PCT=0.15                  # 限价L3比例（15%）

# 等待时间配置（按周期）
LADDER_WAIT_CANDLES_BY_TF="1m:3,3m:2,5m:2,15m:1,30m:1,1h:1,4h:0.5"
LADDER_MAX_WAIT_CANDLES_BY_TF="1m:5,3m:4,5m:3,15m:2,30m:2,1h:1.5,4h:1"
LADDER_PRICE_DISTANCE_BY_TF="1m:0.3,3m:0.4,5m:0.5,15m:0.6,30m:0.7,1h:0.8,4h:1.0"

# 默认值（如果周期未配置）
LADDER_WAIT_CANDLES=2
LADDER_MAX_WAIT_CANDLES=3
LADDER_PRICE_DISTANCE_PCT=0.5
```

### 优势

- ✅ **确保参与**：30%市价单立即成交，不会错过行情
- ✅ **成本优化**：70%限价单有机会获得更好价格
- ✅ **自适应**：根据时间周期调整等待策略
- ✅ **快速决策**：价格远离时及时放弃
- ✅ **风险可控**：至少有30%仓位，最差情况也能参与

### 劣势

- ❌ **滑点成本**：30%市价单会有滑点
- ❌ **复杂度**：需要处理两种订单类型
- ❌ **仓位不确定**：最终仓位在30%-100%之间

---

## 方案B：智能等待（纯限价单 + 价格距离监控）

### 核心思路

保持纯限价单策略，但根据价格变化动态调整等待时间

### 等待时间策略

| 时间周期 | 最大等待 | 检查频率 | 价格远离阈值 |
|---------|---------|---------|-------------|
| 1m      | 5根K线  | 10秒    | 0.3% |
| 3m      | 4根K线  | 20秒    | 0.4% |
| 5m      | 3根K线  | 30秒    | 0.5% |
| 15m     | 2根K线  | 30秒    | 0.6% |
| 30m     | 2根K线  | 60秒    | 0.7% |
| 1h      | 1.5根K线 | 60秒   | 0.8% |
| 4h      | 1根K线  | 120秒   | 1.0% |

### 智能退出逻辑

```python
for retry in range(max_retries):
    await sleep(check_interval)

    # 检查成交
    if total_filled_sz > 0:
        # 有部分成交，继续等待直到max
        if retry >= max_retries - 1:
            cancel_unfilled_orders()
            break
        continue

    # 完全未成交，检查价格距离
    current_price = get_current_price()
    l1_price = ladder_orders[0]["price"]  # 最接近市价的订单

    distance_pct = abs(current_price - l1_price) / l1_price * 100

    if distance_pct > price_distance_threshold:
        # 价格已经走远，放弃所有订单
        cancel_all_orders()
        return {
            "ok": False,
            "error": "ladder_price_too_far",
            "distance": f"{distance_pct:.2f}%",
            "threshold": f"{price_distance_threshold:.2f}%"
        }

    if retry >= max_retries - 1:
        # 达到最大等待时间，价格还在范围内但就是不成交
        cancel_all_orders()
        return {
            "ok": False,
            "error": "ladder_no_fills_timeout"
        }
```

### 配置参数

```bash
LADDER_WAIT_CANDLES_BY_TF="1m:5,3m:4,5m:3,15m:2,30m:2,1h:1.5,4h:1"
LADDER_PRICE_DISTANCE_BY_TF="1m:0.3,3m:0.4,5m:0.5,15m:0.6,30m:0.7,1h:0.8,4h:1.0"
```

### 优势

- ✅ **最优成本**：全部限价单，成交价格最好
- ✅ **智能判断**：价格远离时快速放弃
- ✅ **简单清晰**：只有一种订单类型

### 劣势

- ❌ **可能错过**：如果价格直接反转，完全不成交
- ❌ **执行率低**：限价单天然成交率低于市价单
- ❌ **策略冲突**：DIV信号表示反转，但限价单需要价格回撤

---

## 方案C：自适应策略（基于波动率）

### 核心思路

根据当前市场波动率动态选择市价单比例和等待时间

### 波动率计算

```python
atr = calculate_atr(candles, period=14)
volatility_pct = (atr / current_price) * 100

if volatility_pct > 2.0:
    # 高波动市场
    market_pct = 20%
    limit_pct = 80%
    wait_candles = 3  # 波动大，价格容易回撤

elif volatility_pct > 1.0:
    # 中等波动
    market_pct = 30%
    limit_pct = 70%
    wait_candles = 2

else:
    # 低波动市场
    market_pct = 40%
    limit_pct = 60%
    wait_candles = 1  # 波动小，价格不太会回撤，快速决策
```

### 优势

- ✅ **完全自适应**：根据实时市场状态调整
- ✅ **理论最优**：高波动用限价，低波动用市价

### 劣势

- ❌ **极其复杂**：需要实时计算波动率
- ❌ **参数调优难**：波动率阈值难以确定
- ❌ **过度优化**：可能过拟合历史数据

---

## 推荐实施：方案A（混合订单策略）

### 实施步骤

1. **配置30%市价单 + 70%限价单**
2. **按时间周期设置等待K线数**：
   - 短周期（1m-5m）：基础2-3根，最多3-5根
   - 中周期（15m-30m）：基础1根，最多2根
   - 长周期（1h-4h）：基础0.5-1根，最多1-1.5根
3. **价格远离检测**：超过阈值（0.3%-1.0%）立即放弃限价单
4. **渐进实施**：
   - 第一阶段：市价30%，观察成交情况
   - 第二阶段：根据数据调整比例和等待时间
   - 第三阶段：优化参数达到最佳平衡

### 预期效果

- **执行率**：>95%（至少30%市价单成交）
- **成本优化**：平均成交价优于纯市价单5-15bps
- **不错过率**：>99%（市价单确保参与）

---

## 测试建议

### A/B测试方案

**对照组（当前策略）**：
- 纯限价单
- 等待11秒
- 记录：成交率、平均成交价、错过信号数

**实验组（方案A）**：
- 30%市价 + 70%限价
- 按周期等待
- 记录：成交率、平均成交价、错过信号数

**评估指标**：
1. **执行率**：信号到实际开仓的成功率
2. **成本效率**：平均成交价 vs 信号价的偏差
3. **盈亏比**：考虑成交成本后的整体盈亏

---

生成时间：2025-12-28
版本：v1.0
