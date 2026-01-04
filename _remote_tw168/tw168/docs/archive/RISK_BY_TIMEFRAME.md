# 分时段风险管理 (Risk-Per-Trade by Timeframe)

## 功能说明

系统现在支持根据不同时间周期设置不同的风险金额，实现更精细化的资金管理。

### 配置说明

在 `.env` 文件中配置：

```bash
# 默认风险金额（所有周期的后备值）
RISK_PER_TRADE_USDT=50

# 按时间周期设置风险金额
RISK_PER_TRADE_BY_TF=15m:100,30m:300,1h:300,4h:300
```

### 当前设置

| 时间周期 | 每笔风险金额 |
|---------|------------|
| 15m     | 100 USDT   |
| 30m     | 300 USDT   |
| 1h      | 300 USDT   |
| 4h      | 300 USDT   |
| 其他周期 | 50 USDT (默认) |

## 实现原理

### 1. 配置解析 ([app/config.py](app/config.py#L161))

```python
risk_per_trade_by_tf: str = _getenv("RISK_PER_TRADE_BY_TF", "15m:100,30m:300,1h:300,4h:300")
```

系统启动时将配置字符串解析为字典：

```python
RISK_BY_TF = _parse_float_by_tf(SETTINGS.risk_per_trade_by_tf)
# 结果: {"15m": 100.0, "30m": 300.0, "1h": 300.0, "4h": 300.0}
```

### 2. 查询函数 ([app/config.py](app/config.py#L379-L381))

```python
def get_risk_per_trade(tf: str) -> float:
    """获取指定时间周期的风险金额，如果未配置则返回默认值"""
    return RISK_BY_TF.get(tf, SETTINGS.risk_per_trade_usdt)
```

### 3. 仓位计算 ([app/main.py](app/main.py#L446))

修改 `_calculate_order_size()` 函数支持时间周期参数：

```python
def _calculate_order_size(*, inst_id: str, r_value: float, tf: str | None = None) -> tuple[str, dict[str, object]]:
    # 获取该周期的风险金额
    risk_amount = get_risk_per_trade(tf) if tf else SETTINGS.risk_per_trade_usdt

    # 根据风险金额计算仓位
    # position_size = risk_amount / (entry_price - stop_loss)
    ...
```

## 使用示例

### 15分钟周期信号 (100U 风险)

```
信号: XRP-USDT-SWAP 15m 做多
入场: 2.5000
止损: 2.4900 (R = 0.01)

仓位计算: 100 USDT / 0.01 = 10,000 USDT 名义价值
```

### 1小时周期信号 (300U 风险)

```
信号: ETH-USDT-SWAP 1h 做多
入场: 3400.0
止损: 3350.0 (R = 50.0)

仓位计算: 300 USDT / 50.0 = 6 USDT 名义价值
```

## 日志输出

系统会在日志中显示使用的风险金额：

```
INFO: tv_webhook risk_based_sizing tf=15m risk_usdt=100 r_value=0.0100 coins=10000.00 ct_val=0.01 contracts=100 actual_coins=10000.00
INFO: tv_webhook risk_based_sizing tf=1h risk_usdt=300 r_value=50.0000 coins=6.00 ct_val=0.1 contracts=6 actual_coins=6.00
```

## 优势

1. **精细化风险管理**: 不同周期使用不同风险金额
2. **灵活配置**: 通过 `.env` 文件轻松调整
3. **向后兼容**: 未配置的周期自动使用 `RISK_PER_TRADE_USDT` 默认值
4. **透明可追溯**: 日志中清晰显示每笔交易使用的风险金额

## 修改历史

- 2025-12-28: 实现分时段风险管理功能
  - 添加 `RISK_PER_TRADE_BY_TF` 配置项
  - 修改 `_calculate_order_size()` 支持时间周期参数
  - 更新日志输出显示时间周期和风险金额
  - 默认配置: 15m=100U, 30m-4h=300U
