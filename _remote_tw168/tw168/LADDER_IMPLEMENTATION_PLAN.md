# 阶梯订单混合策略实施计划

## 实施状态

✅ **配置层完成**：
- 添加了 `ladder_market_pct`, `ladder_wait_candles_by_tf` 等配置
- 添加了解析函数 `get_ladder_wait_candles()`, `tf_to_seconds()` 等
- 调整了仓位分配比例（30% 市价 + 70% 限价）

⏳ **执行层待实施**：
- 修改 `main.py` 中阶梯订单下单逻辑
- 实现市价单 + 限价单混合下单
- 实现基于TF的智能等待逻辑
- 添加价格远离检测

---

## 配置参数

```bash
# 订单分配
LADDER_MARKET_PCT=0.30          # 30%市价单（立即成交）
LADDER_LEVEL1_PCT=0.35          # 35%限价L1（-5bps）
LADDER_LEVEL2_PCT=0.20          # 20%限价L2（-15bps）
LADDER_LEVEL3_PCT=0.15          # 15%限价L3（-30bps）

# 按周期等待K线数
LADDER_WAIT_CANDLES_BY_TF="1m:3,3m:2,5m:2,15m:1,30m:1,1h:1,4h:0.5"
LADDER_MAX_WAIT_CANDLES_BY_TF="1m:5,3m:4,5m:3,15m:2,30m:2,1h:1.5,4h:1"

# 价格远离阈值（%）
LADDER_PRICE_DISTANCE_BY_TF="1m:0.3,3m:0.4,5m:0.5,15m:0.6,30m:0.7,1h:0.8,4h:1.0"

# 默认值（未配置的周期）
LADDER_WAIT_CANDLES=2.0
LADDER_MAX_WAIT_CANDLES=3.0
LADDER_PRICE_DISTANCE_PCT=0.5
```

---

## 执行逻辑（伪代码）

```python
async def execute_ladder_orders(tf, side, inst_id, entry_price, order_sz):
    """
    混合订单策略：30%市价 + 70%限价
    """

    # 1. 计算订单分配
    market_sz = order_sz * SETTINGS.ladder_market_pct     # 30%
    limit_l1_sz = order_sz * SETTINGS.ladder_level1_pct   # 35%
    limit_l2_sz = order_sz * SETTINGS.ladder_level2_pct   # 20%
    limit_l3_sz = order_sz * SETTINGS.ladder_level3_pct   # 15%

    # 2. 下市价单（立即成交）
    market_order = place_order(
        ord_type="market",
        sz=market_sz
    )

    # 3. 下限价单（等待成交）
    if side == "buy":
        l1_price = entry_price * (1 - SETTINGS.ladder_level1_bps / 10000)
        l2_price = entry_price * (1 - SETTINGS.ladder_level2_bps / 10000)
        l3_price = entry_price * (1 - SETTINGS.ladder_level3_bps / 10000)
    else:
        l1_price = entry_price * (1 + SETTINGS.ladder_level1_bps / 10000)
        l2_price = entry_price * (1 + SETTINGS.ladder_level2_bps / 10000)
        l3_price = entry_price * (1 + SETTINGS.ladder_level3_bps / 10000)

    limit_orders = [
        place_order(ord_type="limit", sz=limit_l1_sz, px=l1_price, level="L1"),
        place_order(ord_type="limit", sz=limit_l2_sz, px=l2_price, level="L2"),
        place_order(ord_type="limit", sz=limit_l3_sz, px=l3_price, level="L3"),
    ]

    # 4. 等待限价单成交
    await wait_for_fills(tf, limit_orders, l1_price, side)

    # 5. 计算加权平均成交价
    total_filled_sz = market_sz  # 市价单肯定成交了
    total_filled_value = market_sz * market_fill_price

    for limit_ord in limit_orders:
        if limit_ord.filled_sz > 0:
            total_filled_sz += limit_ord.filled_sz
            total_filled_value += limit_ord.filled_sz * limit_ord.fill_price

    weighted_avg_price = total_filled_value / total_filled_sz

    return {
        "filled_sz": total_filled_sz,
        "avg_price": weighted_avg_price
    }


async def wait_for_fills(tf, limit_orders, l1_price, side):
    """
    智能等待逻辑
    """

    # 获取TF相关配置
    candle_seconds = tf_to_seconds(tf)
    base_wait_candles = get_ladder_wait_candles(tf)
    max_wait_candles = get_ladder_max_wait_candles(tf)
    price_distance_threshold = get_ladder_price_distance(tf)

    # 计算等待时间
    base_wait_time = candle_seconds * base_wait_candles
    max_wait_time = candle_seconds * max_wait_candles
    check_interval = min(30, candle_seconds / 10)  # 最多30秒检查一次

    max_retries = int(max_wait_time / check_interval)

    has_partial_fills = False

    for retry in range(max_retries):
        await asyncio.sleep(check_interval)

        # 查询所有限价单成交情况
        total_limit_filled = 0
        for limit_ord in limit_orders:
            ord_info = exchange.get_order(cl_ord_id=limit_ord.cl_ord_id)
            if ord_info and ord_info.get("accFillSz"):
                total_limit_filled += float(ord_info["accFillSz"])

        # 判断是否有部分成交
        if total_limit_filled > 0:
            has_partial_fills = True

        # 检查价格远离
        current_price = get_current_price(inst_id)
        distance_pct = abs(current_price - l1_price) / l1_price * 100

        if distance_pct > price_distance_threshold:
            # 价格已远离
            logger.info("Price too far: %.2f%% > %.2f%%", distance_pct, price_distance_threshold)

            # 取消未成交订单
            cancel_unfilled_orders(limit_orders)
            break

        # 判断是否继续等待
        elapsed_time = (retry + 1) * check_interval

        if has_partial_fills:
            # 有部分成交，等到max_wait_time
            if elapsed_time >= max_wait_time:
                cancel_unfilled_orders(limit_orders)
                break
        else:
            # 完全未成交，等到base_wait_time
            if elapsed_time >= base_wait_time:
                cancel_unfilled_orders(limit_orders)
                break
```

---

## 示例：5m周期执行流程

假设：TRX-USDT-SWAP 5m 周期，buy信号，入场价0.284，仓位82张

### 1. 订单下发

```
市价单：82 × 30% = 24.6张 @ 市价（立即成交约0.284）
限价L1：82 × 35% = 28.7张 @ 0.28386（-5bps）
限价L2：82 × 20% = 16.4张 @ 0.28357（-15bps）
限价L3：82 × 15% = 12.3张 @ 0.28315（-30bps）
```

### 2. 等待参数

```
K线周期：300秒（5分钟）
基础等待：2根K线 = 600秒
最大等待：3根K线 = 900秒
检查间隔：min(30, 300/10) = 30秒
最大检查次数：900 / 30 = 30次
价格远离阈值：0.5%
```

### 3. 执行场景

#### 场景A：价格回撤，限价单成交

```
T+0s:   下单完成，市价单成交24.6张@0.284
T+30s:  检查1，无限价单成交，价格0.285（距离0.3%）
T+60s:  检查2，无成交，价格0.286（距离0.7%）→ 超过0.5%阈值
        → 取消所有限价单
        → 使用24.6张仓位继续（成交率30%）
```

#### 场景B：价格回撤，部分成交

```
T+0s:   下单完成，市价单成交24.6张@0.284
T+120s: 检查4，L1部分成交15张@0.28386，价格回撤至0.28380
T+300s: 检查10，L1再成交10张，L2成交5张
T+600s: 基础等待时间到，但有部分成交，继续等
T+900s: 最大等待时间到
        → 取消未成交订单（L1剩余3.7张，L2剩余11.4张，L3全部）
        → 总成交：24.6 + 25 + 5 = 54.6张（成交率67%）
```

#### 场景C：价格快速反转，限价单不成交

```
T+0s:   下单完成，市价单成交24.6张@0.284
T+30s:  检查1，无限价单成交，价格0.287（距离1.0%）
        → 超过0.5%阈值，立即取消限价单
        → 使用24.6张仓位继续（成交率30%）
```

---

## 下一步

需要修改 `app/main.py` 约1950-2160行的阶梯订单逻辑，实现上述混合策略。

关键修改点：
1. 添加市价单下单逻辑
2. 调整限价单仓位分配
3. 实现基于TF的等待时间计算
4. 添加价格远离检测
5. 改进取消未成交订单的逻辑

---

生成时间：2025-12-28
版本：v1.0
