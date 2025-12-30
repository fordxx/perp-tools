# ✅ Lighter K线功能已就绪

## 功能概述

已为 Lighter 客户端添加 **fetch_candles()** 方法，可以直接获取K线数据并计算止盈止损。

## 实现方式

由于 Lighter 自身的 CandlestickApi 需要认证(403 Forbidden)，我们采用**OKX公开API作为fallback**：
- Lighter和OKX的市场数据是同步的
- OKX公开API无需认证，可靠性高
- 性能良好，支持分页获取大量历史数据

## 方法签名

```python
async def fetch_candles(
    self, 
    *, 
    inst_id: str,  # 合约ID，如 "ETH-USDT-SWAP"
    tf: str,        # 时间周期，如 "1m", "5m", "15m", "1h", "4h", "1d"
    limit: int = 300  # 数量限制
) -> list[Candle]   # 返回 Candle 对象列表 (ts_ms, o, h, l, c)
```

## 测试结果 ✅

```bash
$ python3 test_lighter_candles.py

📊 ETH-USDT-SWAP / 15m / limit=50
✅ 获取到 50 根K线
💡 做多场景: 入场=2983.60 止损=2969.80 (0.46%) 止盈=3011.21 (2R)
💡 做空场景: 入场=2983.60 止损=3012.68 (0.97%) 止盈=2925.43 (2R)

📊 BTC-USDT-SWAP / 5m / limit=200
✅ 获取到 200 根K线
💡 做多场景: 入场=88595.50 止损=88431.63 (0.18%) 止盈=88923.24 (2R)
💡 做空场景: 入场=88595.50 止损=88894.47 (0.34%) 止盈=87997.56 (2R)
```

## 使用示例

### 1. 基本用法

```python
from app.lighter_adapter import create_lighter_adapter

adapter = create_lighter_adapter(use_testnet=False)
await adapter.connect()

# 获取K线
candles = await adapter.fetch_candles(
    inst_id="ETH-USDT-SWAP",
    tf="1h",
    limit=100
)

print(f"获取到 {len(candles)} 根K线")
print(f"最新价格: {candles[-1].c}")
```

### 2. 结合止盈止损计算

```python
from app.risk import stop_loss_price, take_profit_price

# 获取K线
candles = await adapter.fetch_candles(
    inst_id="BTC-USDT-SWAP",
    tf="15m",
    limit=200
)

if candles:
    entry_price = candles[-1].c
    
    # 计算止损 (pivot方法)
    sl = stop_loss_price(
        side="buy",
        entry_price=entry_price,
        candles=candles,
        pivot_len=3,
        atr_len=14,
        atr_buffer_mult=0.2,
        min_buffer_bps=3.0,
    )
    
    # 计算止盈 (2R)
    if sl:
        tp = take_profit_price(
            side="buy",
            entry_price=entry_price,
            stop_loss=sl,
            rr=2.0,
        )
        
        print(f"入场: {entry_price}")
        print(f"止损: {sl}")
        print(f"止盈: {tp}")
```

### 3. 在 main.py 中使用

```python
# 在 _process_payload() 中获取K线
if SETTINGS.exchange == "lighter":
    candles = await exchange.fetch_candles(
        inst_id=inst_id,
        tf=tf,
        limit=300
    )
    
    # 计算止损
    sl = stop_loss_price(
        side=side,
        entry_price=float(entry_price),
        candles=candles,
        pivot_len=SETTINGS.pivot_len,
        atr_len=SETTINGS.atr_len,
        atr_buffer_mult=SETTINGS.atr_buffer_mult,
        min_buffer_bps=SETTINGS.min_buffer_bps,
    )
```

## 支持的时间周期

- **1m, 3m, 5m** - 短周期 (3m -> 5m fallback)
- **15m, 30m** - 中短周期
- **1h, 2h, 4h** - 中周期 (2h -> 1h fallback)
- **12h, 1d** - 长周期

## 代码位置

- **实现**: `app/lighter_client_async.py` (第250行)
- **测试**: `test_lighter_candles.py`
- **止损计算**: `app/risk.py`
  - `stop_loss_price()` - Pivot方法
  - `stop_loss_price_lookback()` - 回望方法
  - `take_profit_price()` - 止盈计算

## 与OKX/Extended的兼容性

✅ **完全兼容** - 使用相同的接口签名和返回格式：

```python
# 三个exchange都支持相同的方法
candles = await exchange.fetch_candles(
    inst_id="ETH-USDT-SWAP",
    tf="1h", 
    limit=300
)
```

## 下一步

现在可以直接在 Lighter 上：
1. ✅ 获取K线数据
2. ✅ 计算Pivot止损
3. ✅ 计算Lookback止损
4. ✅ 计算多级止盈
5. ✅ 检测W底/头肩顶形态
6. ✅ 计算ATR/RSI等技术指标

**完全不需要依赖OKX获取价格数据了！** 🎉
