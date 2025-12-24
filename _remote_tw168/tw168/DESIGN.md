# TV168 交易系统设计文档

**版本**: v1.0  
**更新时间**: 2025-12-20  
**环境**: OKX主网 (https://www.okx.com)

---

## 📋 目录

1. [系统概述](#系统概述)
2. [信号接收流程](#信号接收流程)
3. [止损计算](#止损计算)
4. [止盈计算](#止盈计算)
5. [仓位管理](#仓位管理)
6. [风控机制](#风控机制)
7. [形态过滤](#形态过滤)
8. [订单执行](#订单执行)
9. [Trade Manager](#trade-manager)
10. [完整交易流程](#完整交易流程)
11. [配置参数索引](#配置参数索引)
12. [已知问题与限制](#已知问题与限制)

---

## 系统概述

TV168是一个基于FastAPI的TradingView Webhook服务，实现自动化交易策略：
- **信号源**: TradingView Pine Script策略
- **交易所**: OKX (主网/实盘)
- **持仓模式**: 双向持仓 (long_short_mode)
- **下单方式**: Market订单 + 附加止损单
- **止盈方式**: 分批止盈 + 移动止盈

**核心特性**:
- ✅ 双信号确认机制 (ZONE + DIV)
- ✅ 动态止损计算 (基于ATR和历史价格)
- ✅ 四级止盈阶梯 (1.5R / 2.0R / 2.5R / 3.5R)
- ✅ 移动止盈保护 (trailing stop)
- ✅ 形态识别过滤 (W底/头肩顶)
- ✅ 完善的风控机制

---

## 信号接收流程

### 信号类型

系统使用**两步确认**机制，避免误触发：

#### 1️⃣ ZONE信号 (设置市场状态)

**作用**: 标记当前市场处于超买/超卖区域

**Webhook格式**:
```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "instId": "BCH-USDT-SWAP",
  "tf": "15m",
  "t": "2025-12-20 14:30:00",
  "close": "607.5"
}
```

**参数说明**:
- `type`: 固定为 "ZONE"
- `zone`: 区域类型
  - `OVERSOLD`: 超卖区域 (准备做多)
  - `OVERBOUGHT`: 超买区域 (准备做空)
  - `NEUTRAL`: 中性 (不交易)
- `instId`: OKX合约代码 (如 BCH-USDT-SWAP)
- `tf`: 时间周期 (1m/5m/15m/1H/4H等)
- `t`: 时间戳 (可选)
- `close`: 收盘价 (可选)

**状态管理**:
- 存储在内存 (InMemoryState)
- TTL: 900秒 (15分钟) - 配置项: `ZONE_TTL_SECONDS`
- 过期后自动失效，需要新的ZONE信号

---

#### 2️⃣ DIV信号 (触发交易)

**作用**: 基于当前ZONE状态触发实际交易

**Webhook格式**:
```json
{
  "secret": "rtrwrwtrtsgssdfgsfgfhdghdfgsgdsgsfhgsfhgggdhsfgfdghgdgfhgfgsgdsfeaff6",
  "type": "DIV",
  "instId": "BCH-USDT-SWAP",
  "tf": "15m",
  "t": "2025-12-20 14:30:30",
  "close": "608.0"
}
```

**交易决策逻辑**:
```
IF zone == "OVERSOLD":
    → 开多单 (side=buy, posSide=long)
    
IF zone == "OVERBOUGHT":
    → 开空单 (side=sell, posSide=short)
    
IF zone == "NEUTRAL" OR zone已过期:
    → 跳过交易
```

**前置检查** (按顺序):
1. ✅ Webhook密钥验证
2. ✅ 交易对白名单验证
3. ✅ 去重检查 (30分钟内相同信号)
4. ✅ ZONE状态存在且未过期
5. ✅ 冷却时间检查 (120秒)
6. ✅ 方向开关检查 (ENABLE_LONG/ENABLE_SHORT)
7. ✅ 形态过滤 (如果启用)

---

### 去重机制

**目的**: 防止TradingView重复发送相同信号

**实现**:
```python
dedupe_key = f"{type}:{instId}:{tf}:{timestamp}"
# 示例: "DIV:BCH-USDT-SWAP:15m:2025-12-20 14:30:30"

TTL = 1800秒 (30分钟)
```

如果30分钟内收到完全相同的信号 (包括时间戳)，则跳过处理。

---

## 止损计算

系统支持两种止损计算方法，通过 `STOP_METHOD` 配置切换。

### 方法1: lookback (回看法) ⭐ 推荐/当前使用

**原理**: 基于最近N根K线的极值点 + ATR缓冲

**配置**:
```bash
STOP_METHOD=lookback
STOP_LOOKBACK_BARS=50     # 回看50根K线
ATR_LEN=14                # ATR周期14
ATR_BUFFER_MULT=0.45      # ATR乘数0.45
MIN_BUFFER_BPS=3.5        # 最小缓冲3.5个基点
```

**计算步骤**:

```
步骤1: 获取最近N根K线
candles = 最近50根K线

步骤2: 找基准价
IF side == "buy" (做多):
    base = min(candles[i].low for i in range(50))  # 最低价
ELSE (做空):
    base = max(candles[i].high for i in range(50)) # 最高价

步骤3: 计算ATR
ATR = 最近14根K线的平均真实波幅

步骤4: 计算缓冲区
buffer_atr = ATR × 0.45
buffer_bps = 入场价 × 0.00035  # 3.5个基点
buffer = max(buffer_atr, buffer_bps)

步骤5: 最终止损价
IF side == "buy":
    stop_loss = base - buffer
ELSE:
    stop_loss = base + buffer
```

**示例计算**:
```
场景: BCH做多
入场价: 607.5 USDT
最近50根K线最低价: 585.0 USDT
ATR(14): 8.0 USDT

计算:
buffer_atr = 8.0 × 0.45 = 3.6 USDT
buffer_bps = 607.5 × 0.00035 = 0.21 USDT
buffer = max(3.6, 0.21) = 3.6 USDT

止损 = 585.0 - 3.6 = 581.4 USDT
```

**优点**:
- ✅ 自适应市场波动 (ATR动态调整)
- ✅ 计算简单，速度快
- ✅ 适合趋势跟踪策略

**缺点**:
- ❌ 极端行情下可能止损过远
- ❌ 不考虑价格结构

---

### 方法2: pivot (枢轴法)

**原理**: 基于价格结构的局部高低点 + ATR缓冲

**配置**:
```bash
STOP_METHOD=pivot
PIVOT_LEN=3              # 左右各3根K线
ATR_LEN=14               # ATR周期14
ATR_BUFFER_MULT=0.2      # ATR乘数0.2
MIN_BUFFER_BPS=3         # 最小缓冲3个基点
```

**枢轴点定义**:

**Pivot Low** (局部低点):
```
中心K线的低点 <= 左边3根K线的最低点
              AND
中心K线的低点 <  右边3根K线的最低点
```

**Pivot High** (局部高点):
```
中心K线的高点 >= 左边3根K线的最高点
              AND
中心K线的高点 >  右边3根K线的最高点
```

**计算步骤**:
```
步骤1: 寻找最近的确认枢轴点
从最新K线向前搜索，找到第一个符合条件的枢轴点

步骤2: 应用缓冲区
buffer = max(ATR × 0.2, 入场价 × 0.0003)

步骤3: 计算止损
IF side == "buy":
    stop_loss = pivot_low - buffer
ELSE:
    stop_loss = pivot_high + buffer
```

**优点**:
- ✅ 尊重价格结构
- ✅ 止损更精确
- ✅ 适合震荡市场

**缺点**:
- ❌ 枢轴点可能不存在 (返回None)
- ❌ 计算复杂度较高
- ❌ 需要足够的历史数据

---

### ATR (平均真实波幅) 计算

**公式**:
```python
True Range (TR) = max(
    high - low,
    abs(high - 前收盘价),
    abs(low - 前收盘价)
)

ATR(n) = average(TR) over last n periods
```

**当前配置**: `ATR_LEN=14` (14根K线)

**作用**:
- 衡量市场波动性
- 波动大 → ATR大 → 止损距离远
- 波动小 → ATR小 → 止损距离近

---

### 止损验证

计算完成后，系统会验证止损价格的合理性：

**做多止损验证**:
```python
if stop_loss >= entry_price:
    跳过交易 (止损价不能高于入场价)
```

**做空止损验证**:
```python
if stop_loss <= entry_price:
    跳过交易 (止损价不能低于入场价)
```

如果验证失败，系统会记录日志并跳过交易。

---

## 止盈计算

### 核心概念: R值 (Risk)

**定义**:
```
R = |入场价 - 止损价|  (风险距离)
```

**示例**:
```
入场: 607.5 USDT
止损: 581.5 USDT
R = |607.5 - 581.5| = 26 USDT
```

**R的意义**:
- 1R = 你愿意承受的风险
- 1.5R = 获利1.5倍风险
- 3R = 获利3倍风险 (风险回报比 1:3)

---

### 四级止盈阶梯

**当前配置**:
```bash
TP_ENABLED=true          # 启用止盈

# 第一批止盈
TP1_R=1.5                # 1.5倍R距离
TP1_PCT=0.70             # 平仓70%仓位

# 第二批止盈
TP2_R=2.0                # 2.0倍R距离
TP2_PCT=0.15             # 平仓15%仓位

# 第三批止盈
TP3_R=2.5                # 2.5倍R距离
TP3_PCT=0.10             # 平仓10%仓位

# 第四批止盈
TP4_R=3.5                # 3.5倍R距离
TP4_PCT=0.05             # 平仓5%仓位
```

**计算公式**:
```python
def calculate_tp(entry, stop_loss, R_multiple):
    R = abs(entry - stop_loss)
    
    IF side == "buy":
        TP = entry + (R × R_multiple)
    ELSE:
        TP = entry - (R × R_multiple)
    
    return TP
```

**完整示例**:

```
场景: BCH做多
─────────────────────────────
入场价:  607.5 USDT
止损:    581.5 USDT
R值:     26 USDT
总仓位:  1 BCH

止盈计算:
─────────────────────────────
TP1 = 607.5 + (26 × 1.5) = 646.5 USDT
TP2 = 607.5 + (26 × 2.0) = 659.5 USDT
TP3 = 607.5 + (26 × 2.5) = 672.5 USDT
TP4 = 607.5 + (26 × 3.5) = 698.5 USDT

执行流程:
─────────────────────────────
┌─────────┬──────────┬──────────┬───────────┐
│ 阶段    │ 触发价格 │ 平仓动作 │ 剩余仓位  │
├─────────┼──────────┼──────────┼───────────┤
│ 开仓    │ 607.5    │ 做多1 BCH│ 1.00 BCH  │
│ TP1     │ 646.5    │ 平0.7 BCH│ 0.30 BCH  │
│ TP2     │ 659.5    │ 平0.15   │ 0.15 BCH  │
│         │          │ +启动移动│           │
│ TP3     │ 672.5    │ 平0.10   │ 0.05 BCH  │
│ TP4     │ 698.5    │ 平0.05   │ 0.00 BCH  │
└─────────┴──────────┴──────────┴───────────┘
```

---

### 移动止盈 (Trailing Stop)

**目的**: 保护已实现的利润，避免大幅回撤

**配置**:
```bash
TRAIL_START_R=2.0        # 达到2R后启动
TRAIL_BACK_R=0.75        # 回撤0.75R触发平仓
```

**启动条件**:
```
当价格达到 (入场价 + 2R) 时启动移动止盈
```

**触发逻辑**:
```
最高价 = 跟踪到的最高价格
移动止损线 = 最高价 - (0.75 × R)

IF 当前价 <= 移动止损线:
    平掉剩余所有仓位
```

**示例**:
```
R = 26 USDT
入场 = 607.5

启动条件: 价格 >= 607.5 + (2 × 26) = 659.5
回撤触发: 从最高价回撤 0.75R = 19.5 USDT

场景:
─────────────────────────────
价格涨到 670 → 启动移动止盈 ✅
  移动止损线 = 670 - 19.5 = 650.5
  
价格继续涨到 680 → 更新移动止损线
  移动止损线 = 680 - 19.5 = 660.5
  
价格回落到 660 → 触发平仓 ⚠️
  (660 <= 660.5)
  平掉剩余0.15 BCH
```

**优势**:
- ✅ 锁定大部分利润
- ✅ 给予价格继续上涨的空间
- ✅ 避免贪婪导致利润回吐

---

## 仓位管理

### 当前模式: 固定数量

**配置**:
```bash
ORDER_SZ=1               # 每次下单1个币
```

**问题分析**:

| 币种 | 价格 | 仓位 | USDT价值 | 风险 |
|------|------|------|----------|------|
| HYPE | $22  | 1    | $22      | ⚠️ 太小 |
| SOL  | $140 | 1    | $140     | ✅ 合适 |
| BCH  | $610 | 1    | $610     | ⚠️ 偏大 |
| BTC  | $100k| 1    | $100,000 | 🚫 过大 |

**风险评估**:
```
假设止损都是5%:
HYPE: 风险 = $22 × 5% = $1.1
SOL:  风险 = $140 × 5% = $7
BCH:  风险 = $610 × 5% = $30.5
BTC:  风险 = $100k × 5% = $5000  ← 危险！
```

**结论**: 固定数量模式**风险不一致**，不适合多币种交易。

---

### 计划模式: 固定风险金额 (待实现)

**配置** (已添加到.env):
```bash
RISK_PER_TRADE_USDT=100  # 每次风险100 USDT
```

**计算逻辑**:
```python
R = abs(entry_price - stop_loss)
position_size = RISK_PER_TRADE_USDT / R

# 如果设置了RISK_PER_TRADE_USDT，优先使用
# 否则回退到ORDER_SZ
```

**示例计算**:

```
场景1: BCH做多
─────────────────────────────
入场: 607.5
止损: 581.5
R = 26 USDT

仓位 = 100 / 26 = 3.85 BCH
风险 = 3.85 × 26 = 100 USDT ✅

场景2: SOL做多
─────────────────────────────
入场: 140
止损: 133
R = 7 USDT

仓位 = 100 / 7 = 14.29 SOL
风险 = 14.29 × 7 = 100 USDT ✅

场景3: BTC做多
─────────────────────────────
入场: 100,000
止损: 95,000
R = 5,000 USDT

仓位 = 100 / 5000 = 0.02 BTC
风险 = 0.02 × 5000 = 100 USDT ✅
```

**优势**:
- ✅ 每笔交易风险一致
- ✅ 自动适应币种价格
- ✅ 止损距离大 → 仓位小 (降低风险)
- ✅ 止损距离小 → 仓位大 (提高收益)

**实现状态**: 
- [x] 配置已添加到 .env
- [ ] 代码逻辑待实现
- [ ] 测试验证待完成

---

## 风控机制

### 1. 交易冷却 (Cooldown)

**配置**:
```bash
COOLDOWN_SECONDS=120     # 120秒 = 2分钟
```

**逻辑**:
```
key = f"{instId}:{tf}"
# 示例: "BCH-USDT-SWAP:15m"

IF 上次交易时间 + 120秒 > 当前时间:
    跳过交易 (冷却中)
```

**目的**:
- 防止同一币种频繁开仓
- 避免震荡行情反复止损
- 给策略留出观察时间

---

### 2. 方向控制开关

**配置**:
```bash
ENABLE_LONG=true         # 允许做多
ENABLE_SHORT=true        # 允许做空
```

**用途**:
- 单边行情只做一个方向
- 测试策略时禁用某个方向
- 规避特定市场风险

**示例**:
```bash
# 牛市只做多
ENABLE_LONG=true
ENABLE_SHORT=false

# 熊市只做空
ENABLE_LONG=false
ENABLE_SHORT=true
```

---

### 3. 交易对白名单

**配置**:
```bash
SYMBOL_ALLOWLIST=HYPE-USDT-SWAP,SOL-USDT-SWAP,BCH-USDT-SWAP
```

**验证**:
```python
if payload.instId not in SETTINGS.symbol_allowlist:
    return HTTP 403 "Symbol not allowed"
```

**目的**:
- 限制交易范围
- 避免错误信号
- 控制资金分配

---

### 4. ZONE信号过期

**配置**:
```bash
ZONE_TTL_SECONDS=900     # 15分钟
```

**逻辑**:
```python
zone_age = 当前时间 - zone设置时间

IF zone_age > 900:
    zone状态过期，跳过交易
```

**目的**:
- 避免使用过时的市场状态
- 确保信号时效性
- 减少误判风险

---

### 5. 去重机制

**TTL**: 1800秒 (30分钟)

**Key格式**:
```
f"{type}:{instId}:{tf}:{timestamp}"
```

**目的**:
- 防止TradingView重复发送
- 避免同一信号多次执行
- 节省API调用

---

### 6. 实盘开关

**配置**:
```bash
TRADING_ENABLED=true     # ⚠️ 当前为实盘模式
```

**行为差异**:

| TRADING_ENABLED | 行为 |
|-----------------|------|
| `false` | Paper模式: 只计算，不下单，返回模拟结果 |
| `true`  | 实盘模式: 真实下单到OKX |

**Paper模式响应示例**:
```json
{
  "ok": true,
  "paper": true,
  "instId": "BCH-USDT-SWAP",
  "side": "buy",
  "entry": 607.5,
  "sl": 581.5,
  "tp": 685.5
}
```

---

## 形态过滤

### 功能说明

形态过滤是**可选的附加条件**，用于提高交易质量。

**启用方式**:
```bash
# 做多时要求W底形态
PATTERN_LONG=w_bottom

# 做空时要求头肩顶形态
PATTERN_SHORT=hs_top

# 禁用形态过滤
PATTERN_LONG=none
PATTERN_SHORT=none
```

**当前状态**: 均设置为 `none` (已禁用)

---

### 形态1: W底 (W Bottom)

**适用**: 做多信号

**配置**:
```bash
PATTERN_LONG=w_bottom              # 启用W底过滤
PATTERN_PIVOT_LEN=3                # 枢轴周期
PATTERN_TOL_PCT=0.006              # 容差0.6%
W_MIN_BOUNCE_PCT=0.004             # 最小反弹0.4%
W_REQUIRE_BREAKOUT=false           # 不强制突破颈线
```

**识别逻辑**:

```
1. 寻找枢轴序列: L-H-L
   - L1: 第一个局部低点
   - H:  中间的局部高点
   - L2: 第二个局部低点

2. 验证双底:
   L1 和 L2 的价格接近 (差异 < 0.6%)
   
3. 验证反弹:
   H 的价格 > max(L1, L2) × (1 + 0.004)
   即: 高点至少比低点高0.4%
   
4. (可选) 验证突破:
   当前价 > H  (突破颈线)
```

**图示**:
```
价格
 │
 │         ╱╲  H (颈线)
 │        ╱  ╲
 │       ╱    ╲
 │      ╱      ╲
 │   L1         L2  ← 双底 (价格接近)
 │  ╱            ╲
 └─────────────────→ 时间
      W底形态
```

**通过条件**:
- ✅ 枢轴序列 = [L, H, L]
- ✅ L1 ≈ L2 (容差6个千分点)
- ✅ H - L >= 0.4%
- ✅ (可选) 突破颈线

**失败原因**:
- ❌ 枢轴点不足3个
- ❌ 序列不是L-H-L
- ❌ 双底价格差异大
- ❌ 反弹幅度不足
- ❌ (如果启用) 未突破颈线

---

### 形态2: 头肩顶 (Head & Shoulders Top)

**适用**: 做空信号

**配置**:
```bash
PATTERN_SHORT=hs_top                      # 启用头肩顶过滤
PATTERN_PIVOT_LEN=3                       # 枢轴周期
PATTERN_TOL_PCT=0.006                     # 容差0.6%
HS_MIN_SHOULDER_DROP_PCT=0.004            # 头部最小突出0.4%
HS_REQUIRE_BREAKDOWN=false                # 不强制跌破颈线
```

**识别逻辑**:

```
1. 寻找枢轴序列: H-L-H-L-H
   - H1: 左肩
   - L1: 左肩回撤
   - H2: 头部
   - L2: 头部回撤
   - H3: 右肩

2. 验证头部最高:
   H2 > H1 AND H2 > H3
   
3. 验证双肩对称:
   H1 和 H3 价格接近 (差异 < 0.6%)
   
4. 验证头部突出:
   (H2 - max(H1,H3)) / H2 >= 0.004
   即: 头部至少比肩部高0.4%
   
5. (可选) 验证跌破颈线:
   当前价 < (L1 + L2) / 2
```

**图示**:
```
价格
 │      H2 (头部)
 │      ╱╲
 │     ╱  ╲
 │  H1╱    ╲H3  ← 双肩 (价格接近)
 │  ╱╲    ╱╲
 │ ╱  ╲  ╱  ╲
 │╱  L1╲╱L2  ╲  ← 颈线 = (L1+L2)/2
 └──────────────→ 时间
   头肩顶形态
```

**通过条件**:
- ✅ 枢轴序列 = [H, L, H, L, H]
- ✅ H2 > H1 且 H2 > H3
- ✅ H1 ≈ H3 (容差6个千分点)
- ✅ 头部突出 >= 0.4%
- ✅ (可选) 跌破颈线

**失败原因**:
- ❌ 枢轴点不足5个
- ❌ 序列不是H-L-H-L-H
- ❌ 头部不是最高点
- ❌ 双肩不对称
- ❌ 头部突出不足
- ❌ (如果启用) 未跌破颈线

---

### 枢轴点提取算法

**定义**:
```python
Pivot Low (局部低点):
  中心K线.low <= 左边pivot_len根K线的最低
  AND
  中心K线.low <  右边pivot_len根K线的最低

Pivot High (局部高点):
  中心K线.high >= 左边pivot_len根K线的最高
  AND
  中心K线.high >  右边pivot_len根K线的最高
```

**参数**: `PATTERN_PIVOT_LEN=3` (左右各3根K线)

**去重逻辑**:
- 保留最极端的枢轴点
- 同类型连续枢轴只保留更高/更低的
- 确保枢轴序列交替 (H-L-H-L...)

---

## 订单执行

### 订单类型

**当前配置**:
```bash
ORDER_TYPE=market        # 市价单
LIMIT_SLIPPAGE_BPS=5     # 限价单滑点(未使用)
```

**Market订单**:
- ✅ 立即成交
- ✅ 无需设置价格
- ❌ 可能有滑点

**Limit订单** (未启用):
```bash
ORDER_TYPE=limit
LIMIT_SLIPPAGE_BPS=5
```
- ✅ 价格可控
- ❌ 可能不成交
- 限价 = 入场价 × (1 ± 0.0005)

---

### 持仓模式

**配置**:
```bash
OKX_TD_MODE=cross        # 全仓模式
```

**选项**:
- `cross`: 全仓 (所有仓位共享保证金)
- `isolated`: 逐仓 (每个仓位独立保证金)

**当前使用**: 全仓模式

---

### 订单参数构建

**主订单** (开仓):
```json
{
  "instId": "BCH-USDT-SWAP",
  "tdMode": "cross",
  "side": "buy",
  "posSide": "long",
  "ordType": "market",
  "sz": "1",
  "clOrdId": "tv1766217728392b"
}
```

**附加止损单**:
```json
{
  "attachAlgoOrds": [
    {
      "slTriggerPx": "581.5",
      "slOrdPx": "-1"
    }
  ]
}
```

**参数说明**:
- `slTriggerPx`: 止损触发价
- `slOrdPx`: "-1" 表示市价止损
- 止盈单 (tpTriggerPx) 当前未使用，由TradeManager管理

---

### 订单ID (clOrdId)

**格式**:
```
tv{timestamp}{random}{direction}
```

**示例**:
```
tv1766217728392b
├─ tv: 前缀标识
├─ 1766217728: Unix时间戳
├─ 392: 随机数(100-999)
└─ b: 方向 (b=buy, s=sell)
```

**长度**: 最多32字符 (OKX限制)

**关键点**:
- ⚠️ **不能包含下划线** (OKX会返回51000错误)
- ✅ 可以包含字母、数字
- ✅ 时间戳 + 随机数保证唯一性

---

## Trade Manager

### 功能概述

TradeManager是一个**后台异步任务**，负责管理多级止盈和移动止盈。

**启动时机**: 服务启动时自动启动 (如果 `TRADING_ENABLED=true`)

**轮询周期**: 
```bash
MANAGER_POLL_SECONDS=2   # 每2秒检查一次
```

---

### TradePlan数据结构

每笔交易都会创建一个TradePlan:

```python
@dataclass
class TradePlan:
    inst_id: str              # 交易对
    tf: str                   # 时间周期
    side: str                 # 方向 (buy/sell)
    pos_side: str             # 持仓方向 (long/short)
    td_mode: str              # 保证金模式 (cross/isolated)
    entry_price: float        # 入场价
    stop_loss: float          # 止损价
    total_sz: Decimal         # 总仓位
    r_value: float            # R值
    cl_ord_id: str            # 订单ID
    
    # 状态标记
    filled: bool = False      # 是否成交
    tp1_done: bool = False    # TP1是否完成
    tp2_done: bool = False    # TP2是否完成
    tp3_done: bool = False    # TP3是否完成
    tp4_done: bool = False    # TP4是否完成
    trail_active: bool = False # 移动止盈是否激活
    closed_sz: Decimal = 0    # 已平仓数量
```

---

### 执行逻辑

**每2秒循环**:
```
1. 遍历所有TradePlan
   
2. 检查持仓是否还存在
   IF 持仓 == 0:
       清除TradePlan (已止损或手动平仓)
       
3. 获取当前价格
   
4. 执行TP阶梯:
   
   IF !tp1_done AND 价格达到TP1:
       平仓70%仓位
       标记tp1_done = true
       
   IF !tp2_done AND 价格达到TP2:
       平仓15%仓位
       标记tp2_done = true
       启动移动止盈 (trail_active = true)
       
   IF !tp3_done AND 价格达到TP3:
       平仓10%仓位
       标记tp3_done = true

   IF !tp4_done AND 价格达到TP4:
       平仓5%仓位
       标记tp4_done = true
       清除TradePlan
       
5. 移动止盈逻辑:
   
   IF trail_active:
       更新最高价/最低价
       
       IF 回撤 >= TRAIL_BACK_R:
           平掉剩余所有仓位
           清除TradePlan
```

---

### 平仓订单生成

**reduce-only订单**:
```json
{
  "instId": "BCH-USDT-SWAP",
  "tdMode": "cross",
  "side": "sell",           # 平多单
  "posSide": "long",
  "ordType": "market",
  "sz": "0.7",              # 平仓数量
  "reduceOnly": "true",     # 只减仓
  "clOrdId": "tp1_xxx"
}
```

**为什么用reduce-only**:
- 防止意外开新仓位
- 确保只减少持仓
- 提高安全性

---

### 最小下单量处理

**问题**: 交易所有最小下单量限制 (如0.1 BCH)

**处理**:
```python
def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step
```

**示例**:
```
总仓位: 1 BCH
TP1: 70% = 0.7 BCH ✅
TP2: 15% = 0.15 BCH ✅
TP3: 10% = 0.10 BCH ✅
TP4: 5% = 0.05 BCH ✅

如果最小下单量 = 0.1:
所有平仓都满足要求
```

---

### 持仓检查

**API调用**:
```python
okx.get_position(
    inst_id="BCH-USDT-SWAP",
    pos_side="long"
)
```

**检查逻辑**:
```
IF position == None OR position.pos == 0:
    持仓已关闭 (可能是止损或手动平仓)
    清除TradePlan
    停止管理
```

**意义**:
- 避免对已平仓位重复操作
- 自动清理过期计划
- 节省API调用

---

## 完整交易流程

### 流程图

```
┌─────────────────────────────────────────────────────────┐
│                    TradingView信号                       │
└───────────────────────┬─────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
   [ZONE信号]                       [DIV信号]
        │                               │
        ▼                               │
  存储状态到内存                         │
  (TTL: 15分钟)                         │
        │                               │
        └───────────────┬───────────────┘
                        │
                        ▼
            ┌──────────────────────┐
            │  前置验证检查         │
            │  1. Webhook密钥      │
            │  2. 交易对白名单     │
            │  3. 去重检查         │
            │  4. ZONE状态有效     │
            │  5. 冷却时间         │
            │  6. 方向开关         │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  获取K线数据          │
            │  (最近300根)         │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  形态过滤 (可选)      │
            │  - W底检测           │
            │  - 头肩顶检测        │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  计算止损价          │
            │  - lookback方法      │
            │  或                  │
            │  - pivot方法         │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  止损验证             │
            │  - 做多: SL < Entry  │
            │  - 做空: SL > Entry  │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  计算止盈价          │
            │  TP1/TP2/TP3/TP4     │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  生成订单ID          │
            │  (含时间戳+随机数)   │
            └──────────┬───────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
  [Paper模式]                    [实盘模式]
  返回模拟结果                  提交OKX订单
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  主订单 (Market)     │
        │                  │  + 附加止损单        │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  注册TradePlan       │
        │                  │  到TradeManager      │
        │                  └──────────┬───────────┘
        │                             │
        └─────────────┬───────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │  返回JSON响应        │
            └──────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              TradeManager后台循环 (每2秒)                │
└───────────────────────┬─────────────────────────────────┘
                        │
                        ▼
            ┌──────────────────────┐
            │  检查所有TradePlan   │
            └──────────┬───────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  获取当前持仓        │
            └──────────┬───────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
   [持仓 = 0]                    [持仓 > 0]
   清除TradePlan                 继续管理
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  获取当前价格        │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  检查TP1触发         │
        │                  │  (价格 >= TP1)       │
        │                  └──────────┬───────────┘
        │                             │ Yes
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  平仓70%仓位         │
        │                  │  标记tp1_done        │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  检查TP2触发         │
        │                  │  (价格 >= TP2)       │
        │                  └──────────┬───────────┘
        │                             │ Yes
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  平仓15%仓位         │
        │                  │  启动移动止盈        │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  检查TP3触发         │
        │                  │  (价格 >= TP3)       │
        │                  │  检查TP4触发         │
        │                  │  (价格 >= TP4)       │
        │                  └──────────┬───────────┘
        │                             │ Yes
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  平仓剩余15%         │
        │                  │  清除TradePlan       │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  移动止盈检查        │
        │                  │  (如果已启动)       │
        │                  └──────────┬───────────┘
        │                             │
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  回撤 >= 0.75R?      │
        │                  └──────────┬───────────┘
        │                             │ Yes
        │                             ▼
        │                  ┌──────────────────────┐
        │                  │  平掉剩余仓位        │
        │                  │  清除TradePlan       │
        │                  └──────────────────────┘
        │                             │
        └─────────────────────────────┘
```

---

### 时序图

```
TradingView    Webhook服务    OKX API    TradeManager
    │             │             │             │
    │──ZONE信号──>│             │             │
    │             │             │             │
    │             ├─存储状态─>内存            │
    │             │             │             │
    │<──200 OK────│             │             │
    │             │             │             │
    │──DIV信号───>│             │             │
    │             │             │             │
    │             ├─检查ZONE───>内存           │
    │             │             │             │
    │             ├─获取K线────>│             │
    │             │<────────────┤             │
    │             │             │             │
    │             ├─计算止损/止盈               │
    │             │             │             │
    │             ├─下单请求───>│             │
    │             │<──订单确认──┤             │
    │             │             │             │
    │             ├─注册Plan────────────────>│
    │             │             │             │
    │<──200 OK────│             │             │
    │             │             │             │
    │             │             │   [后台循环每2秒]
    │             │             │             │
    │             │             │<──检查持仓──┤
    │             │             │             │
    │             │             │<──获取价格──┤
    │             │             │             │
    │             │             │<──TP1平仓───┤
    │             │             │             │
    │             │             │<──TP2平仓───┤
    │             │             │             │
    │             │             │<──移动止盈──┤
```

---

## 配置参数索引

### OKX API配置
```bash
OKX_BASE_URL=https://www.okx.com              # API基础URL
OKX_API_KEY=xxx                                # API密钥
OKX_API_SECRET=xxx                             # API密钥
OKX_API_PASSPHRASE=xxx                         # API密码
OKX_TD_MODE=cross                              # 保证金模式 (cross/isolated)
```

### Webhook配置
```bash
TV_WEBHOOK_SECRET=xxx                          # Webhook验证密钥
TRADING_ENABLED=true                           # 实盘交易开关
```

### 交易对配置
```bash
SYMBOL_ALLOWLIST=HYPE-USDT-SWAP,SOL-USDT-SWAP,BCH-USDT-SWAP
ENABLE_LONG=true                               # 允许做多
ENABLE_SHORT=true                              # 允许做空
```

### 时间控制
```bash
ZONE_TTL_SECONDS=900                           # ZONE过期时间(秒)
COOLDOWN_SECONDS=120                           # 交易冷却时间(秒)
```

### 订单配置
```bash
ORDER_TYPE=market                              # 订单类型 (market/limit)
LIMIT_SLIPPAGE_BPS=5                           # 限价单滑点(基点)
ORDER_SZ=1                                     # 固定仓位大小
RISK_PER_TRADE_USDT=100                        # 每笔风险金额(USDT) [待实现]
```

### 止损配置
```bash
STOP_METHOD=lookback                           # 止损方法 (lookback/pivot)
STOP_LOOKBACK_BARS=50                          # 回看K线数量
PIVOT_LEN=3                                    # 枢轴周期
ATR_LEN=14                                     # ATR周期
ATR_BUFFER_MULT=0.45                           # ATR乘数
MIN_BUFFER_BPS=3.5                             # 最小缓冲(基点)
```

### 止盈配置
```bash
TP_ENABLED=true                                # 启用止盈
TP1_R=1.5                                      # TP1倍数
TP1_PCT=0.70                                   # TP1平仓比例
TP2_R=2.0                                      # TP2倍数
TP2_PCT=0.15                                   # TP2平仓比例
TP3_R=2.5                                      # TP3倍数
TP3_PCT=0.10                                   # TP3平仓比例
TP4_R=3.5                                      # TP4倍数
TP4_PCT=0.05                                   # TP4平仓比例
TRAIL_START_R=2.0                              # 移动止盈启动倍数
TRAIL_BACK_R=0.75                              # 移动止盈回撤倍数
```

### 形态过滤配置
```bash
PATTERN_LONG=none                              # 做多形态 (w_bottom/none)
PATTERN_SHORT=none                             # 做空形态 (hs_top/none)
PATTERN_PIVOT_LEN=3                            # 形态枢轴周期
PATTERN_TOL_PCT=0.006                          # 形态容差
W_MIN_BOUNCE_PCT=0.004                         # W底最小反弹
W_REQUIRE_BREAKOUT=false                       # W底是否要求突破
HS_MIN_SHOULDER_DROP_PCT=0.004                 # 头肩顶头部最小突出
HS_REQUIRE_BREAKDOWN=false                     # 头肩顶是否要求跌破
```

### TradeManager配置
```bash
MANAGER_POLL_SECONDS=2                         # 轮询周期(秒)
```

---

## 已知问题与限制

### 1. 仓位管理问题

**问题**: 固定数量模式导致不同币种风险差异巨大

**影响**:
- SOL (1个 = $140) vs BTC (1个 = $100,000)
- 风险不一致，难以统一管理

**状态**: 
- [x] 已添加 RISK_PER_TRADE_USDT 配置
- [ ] 代码逻辑待实现

---

### 2. clOrdId格式限制

**问题**: OKX不接受包含下划线的clOrdId

**原因**: 
```python
# ❌ 错误格式
cl_ord_id = "tv_1766217728_buy"  # 返回51000错误

# ✅ 正确格式  
cl_ord_id = "tv1766217728b"      # 成功
```

**解决**: 已修改为无下划线格式

---

### 3. 止盈订单未附加到主订单

**当前**: OKX 由 TradeManager 异步管理多级止盈；Extended 通过多笔 reduce-only 限价单挂多级 TP。

**原因**: 
- OKX的attachAlgoOrds只能设置一个止盈价
- Extended 的 TPSL 仅支持单层 TP/SL，多级 TP 需拆单实现

**影响**:
- ✅ 灵活性高
- ❌ 依赖后台服务稳定运行
- ❌ 服务重启会丢失TradePlan

**改进方向**:
- 考虑将TradePlan持久化到数据库
- 服务重启后可恢复

---

### 4. K线数据依赖

**问题**: 每次交易需要获取300根K线

**影响**:
- API调用开销
- 可能有延迟
- 依赖OKX API稳定性

**优化方向**:
- 考虑缓存K线数据
- 使用WebSocket实时更新

---

### 5. 没有最大持仓限制

**问题**: 理论上可以无限开仓

**风险**:
- 信号密集时可能过度开仓
- 爆仓风险

**建议**:
- 添加最大同时持仓数限制
- 添加最大总风险限制

---

### 6. 形态识别的局限性

**问题**: 
- 枢轴点检测可能不准确
- 形态容差参数敏感
- 可能产生假阳性

**建议**:
- 谨慎使用形态过滤
- 优先依赖止损止盈
- 形态过滤作为辅助

---

### 7. 移动止盈的滞后性

**问题**: 2秒轮询周期可能错过快速波动

**示例**:
```
价格快速上涨到700，然后秒跌回650
如果刚好在2秒间隔内，可能无法捕捉到700的高点
```

**影响**: 可能少赚一些利润

**优化方向**:
- 缩短轮询周期 (增加API调用)
- 使用WebSocket实时价格

---

## 维护指南

### 修改配置

**步骤**:
```bash
# 1. SSH登录服务器
ssh -i ~/lightsail.pem ubuntu@3.38.98.169

# 2. 编辑配置
cd tw168
nano .env

# 3. 重启服务
pkill -f uvicorn
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > tw168.log 2>&1 &

# 4. 检查服务状态
curl http://127.0.0.1:8000/health
```

---

### 查看日志

**实时日志**:
```bash
tail -f tw168.log
```

**搜索特定交易**:
```bash
grep "BCH-USDT-SWAP" tw168.log | grep "order_placed"
```

**查看错误**:
```bash
grep "ERROR\|Exception" tw168.log
```

---

### 测试信号

**手动发送ZONE信号**:
```bash
curl -X POST http://127.0.0.1:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "你的密钥",
    "type": "ZONE",
    "zone": "OVERSOLD",
    "instId": "BCH-USDT-SWAP",
    "tf": "15m",
    "close": "607.5"
  }'
```

**手动发送DIV信号**:
```bash
curl -X POST http://127.0.0.1:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{
    "secret": "你的密钥",
    "type": "DIV",
    "instId": "BCH-USDT-SWAP",
    "tf": "15m",
    "close": "608.0"
  }'
```

---

### 紧急停止

**停止交易**:
```bash
# 方法1: 禁用实盘交易
sed -i 's/TRADING_ENABLED=true/TRADING_ENABLED=false/' .env
pkill -f uvicorn
# 重启服务 (Paper模式)

# 方法2: 完全关闭服务
pkill -f uvicorn
```

**平掉所有持仓**:
```python
# 使用OKX网页平仓
# 或运行平仓脚本 (需要自己编写)
```

---

## 更新日志

### v1.0 (2025-12-20)
- ✅ 初始版本部署
- ✅ 支持BCH/SOL/HYPE交易对
- ✅ 实现lookback止损方法
- ✅ 实现三级止盈 + 移动止盈
- ✅ 修复clOrdId下划线问题
- ✅ 添加RISK_PER_TRADE_USDT配置 (待实现)

---

## 待办事项

- [ ] 实现固定风险金额仓位计算
- [ ] TradePlan持久化 (数据库)
- [ ] 最大持仓数限制
- [ ] WebSocket实时价格
- [ ] 完善监控告警
- [ ] 添加性能统计
- [ ] 编写自动化测试

---

**文档结束**

---

## 🔄 更新日志 (续)

### v1.1 (2025-12-20 18:00)
- ✅ **优化ZONE过期逻辑**
  - ZONE_TTL_SECONDS: 900秒 → 43200秒 (12小时)
  - 移除ZONE过期时间检查
  - 现在只要设置了ZONE就一直有效，直到被新的ZONE覆盖
  
- ✅ **改进多周期支持**
  - 1H、4H等大周期现在可以正常工作
  - ZONE信号可以持续多个小时
  - 只看最新一次ZONE状态，不管多久之前设置的

- ✅ **交易逻辑说明**
  ```
  最后一次ZONE = OVERBOUGHT (RSI上穿阈值)
    → DIV触发 → 做空 (sell/short)
    
  最后一次ZONE = OVERSOLD (RSI下穿阈值)
    → DIV触发 → 做多 (buy/long)
  ```

- ✅ **测试验证**
  - OVERSOLD → 做多 ✅
  - OVERBOUGHT → 做空 ✅
  - ZONE状态可以正确切换 ✅

---

## 📝 TradingView配置建议

### 告警设置

**做多信号** (RSI下穿SHORT阈值):
```
1. 触发条件: RSI 大于 Short ML Threshold
2. 消息体:
{
  "secret": "你的密钥",
  "type": "ZONE",
  "zone": "OVERSOLD",
  "instId": "SOL-USDT-SWAP",
  "tf": "{{interval}}",
  "close": "{{close}}",
  "t": "{{time}}"
}

3. 频率: 每根K线收盘一次
```

**做空信号** (RSI上穿LONG阈值):
```
1. 触发条件: RSI 大于 Long ML Threshold
2. 消息体:
{
  "secret": "你的密钥",
  "type": "ZONE",
  "zone": "OVERBOUGHT",
  "instId": "SOL-USDT-SWAP",
  "tf": "{{interval}}",
  "close": "{{close}}",
  "t": "{{time}}"
}

3. 频率: 每根K线收盘一次
```

**触发交易** (你的开单条件):
```
1. 触发条件: 你的复杂条件(RSI位置+其他)
2. 消息体:
{
  "secret": "你的密钥",
  "type": "DIV",
  "instId": "SOL-USDT-SWAP",
  "tf": "{{interval}}",
  "close": "{{close}}",
  "t": "{{time}}"
}

3. 频率: 每根K线收盘一次
```

### 工作流程

```
TradingView策略运行中...

├─ RSI上穿LONG阈值 
│  → 发送 ZONE=OVERBOUGHT
│  → 服务器记录: "准备做空"
│
├─ 满足你的开单条件
│  → 发送 DIV信号
│  → 服务器检查: 最新ZONE=OVERBOUGHT
│  → 开空单 ✅
│
├─ (几个小时后) RSI下穿SHORT阈值
│  → 发送 ZONE=OVERSOLD  
│  → 服务器更新: "准备做多"
│
└─ 再次满足开单条件
   → 发送 DIV信号
   → 服务器检查: 最新ZONE=OVERSOLD
   → 开多单 ✅
```

---

## ⚙️ 配置变更说明

### 修改的配置
```bash
# v1.0 → v1.1
ZONE_TTL_SECONDS=900      # 旧: 15分钟
ZONE_TTL_SECONDS=43200    # 新: 12小时
```

### 代码变更
```python
# 旧代码 (检查过期时间):
if (zone_state.zone not in {"OVERSOLD", "OVERBOUGHT"}) or \
   ((zone_state.ts + SETTINGS.zone_ttl_seconds) < time.time()):
    return {"ok": True, "skipped": "zone_expired_or_neutral"}

# 新代码 (只检查状态有效性):
if zone_state.zone not in {"OVERSOLD", "OVERBOUGHT"}:
    return {"ok": True, "skipped": "zone_expired_or_neutral"}
```

### 影响范围
- ✅ 1H、4H等大周期策略现在可以正常工作
- ✅ ZONE信号不会因为时间过长而失效
- ✅ 可以在不同时间周期混合使用
- ⚠️ ZONE状态会一直保留，直到新的ZONE信号覆盖

---
