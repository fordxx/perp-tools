# PerpBot 系统架构文档

> **分支**: `claude/unified-okx-dex-01TjmxFxGKzkrJdDrBhgxSbF`  
> **版本**: v1.0  
> **最后更新**: 2024-12-08

---

## 目录

- [架构概览](#架构概览)
- [分层架构](#分层架构)
- [核心模块](#核心模块)
- [数据流](#数据流)
- [资金管理架构](#资金管理架构)
- [交易执行流程](#交易执行流程)
- [风控体系](#风控体系)
- [监控与告警](#监控与告警)
- [技术选型](#技术选型)
- [扩展性设计](#扩展性设计)

---

## 架构概览

### 设计原则

1. **模块化**: 每个功能独立模块，便于测试和维护
2. **解耦**: 策略、风控、交易所完全解耦
3. **异步优先**: 使用 asyncio 提升并发性能
4. **配置驱动**: 参数可配置，无需修改代码
5. **可观测性**: 完整的日志、监控、告警体系

### 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.10+ | 核心逻辑 |
| 异步 | asyncio | 并发处理 |
| Web | FastAPI | REST API + WebSocket |
| 数据 | CSV / SQLite | 交易记录 |
| 配置 | YAML | 参数管理 |
| 监控 | 自研 + 多渠道 | 实时监控 |

---

## 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         表示层 (Presentation Layer)              │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Web Console  │  │     CLI      │  │   REST API   │        │
│  │  (FastAPI)   │  │  (Click)     │  │  (FastAPI)   │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
└─────────┼──────────────────┼──────────────────┼────────────────┘
          │                  │                  │
┌─────────┼──────────────────┼──────────────────┼────────────────┐
│         │     应用层 (Application Layer)      │                │
├─────────┴──────────────────┴──────────────────┴────────────────┤
│  ┌──────────────────────────────────────────────────────────┐ │
│  │            Trading Service (主控循环)                    │ │
│  │  ┌────────────────────────────────────────────────────┐ │ │
│  │  │  • 协调策略执行                                      │ │ │
│  │  │  • 调度资金分配                                      │ │ │
│  │  │  • 管理交易生命周期                                  │ │ │
│  │  └────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌────────────────────────────┼───────────────────────────────────┐
│         业务层 (Business Layer)                                │
├────────────────────────────┴───────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ 策略引擎      │  │ 套利扫描器    │  │ 刷量引擎      │        │
│  │ TakeProfit   │  │ Scanner      │  │ HedgeVolume  │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ 风险管理      │  │ 仓位守卫      │  │ 提醒系统      │        │
│  │ RiskManager  │  │ PosGuard     │  │ Alerts       │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌────────────────────────────┼───────────────────────────────────┐
│       资金层 (Capital Layer)                                    │
├────────────────────────────┴───────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐ │
│  │            Capital Orchestrator (资金总控)               │ │
│  │  ┌─────────────────────────────────────────────────────┐│ │
│  │  │  刷量层 (70%)  │  套利层 (20%)  │  储备层 (10%)     ││ │
│  │  │  Wash Pool    │  Arb Pool     │  Reserve Pool    ││ │
│  │  └─────────────────────────────────────────────────────┘│ │
│  │  • 动态资金分配                                          │ │
│  │  • 安全模式触发                                          │ │
│  │  • 跨层借用管理                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────────────────┬───────────────────────────────────┘
                             │
┌────────────────────────────┼───────────────────────────────────┐
│       交易所层 (Exchange Layer)                                 │
├────────────────────────────┴───────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────────┐ │
│  │              Exchange Base (统一接口)                     │ │
│  │  • connect() / disconnect()                             │ │
│  │  • place_order() / cancel_order()                       │ │
│  │  • get_position() / get_balance()                       │ │
│  │  • subscribe_orderbook()                                │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Paradex │ │Extended│ │  OKX   │ │Binance │ │ Others │    │
│  │ (DEX)  │ │ (DEX)  │ │ (行情) │ │ (行情) │ │(待启用)│    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 核心模块

### 1. 数据模型层 (`models.py`)

**职责**: 定义所有数据结构

```python
# 核心数据模型
@dataclass
class Order:
    """订单模型"""
    order_id: str
    symbol: str
    side: str  # "BUY" / "SELL"
    size: float
    price: float
    order_type: str  # "LIMIT" / "MARKET"
    status: str  # "PENDING" / "FILLED" / "CANCELLED"
    filled_size: float
    timestamp: float

@dataclass
class Position:
    """持仓模型"""
    symbol: str
    side: str  # "LONG" / "SHORT"
    size: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    leverage: float
    margin: float

@dataclass
class Quote:
    """报价模型"""
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp: float

@dataclass
class ArbitrageOpportunity:
    """套利机会"""
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    spread_pct: float
    net_profit_pct: float  # 扣除成本后
    confidence: float
    score: float
```

### 2. 资金管理层 (`capital_orchestrator.py`)

**职责**: 三层资金池管理与调度

```python
class CapitalOrchestrator:
    """
    三层资金管理:
    - 刷量层 (70%): 高频对冲刷量
    - 套利层 (20%): 跨所套利
    - 储备层 (10%): 应急与对冲
    
    核心功能:
    1. 资金预留与释放
    2. 安全模式切换
    3. 跨层借用
    4. 实时快照
    """
    
    def __init__(self, wu_size, wash_budget_pct, arb_budget_pct, reserve_pct):
        # 初始化三层资金池
        self.pools = {
            "wash": PoolState(wash_budget_pct),
            "arb": PoolState(arb_budget_pct),
            "reserve": PoolState(reserve_pct)
        }
    
    def reserve_for_strategy(self, exchanges, amount, strategy):
        """为策略预留资金"""
        pool = self._strategy_to_pool(strategy)
        # 检查资金池可用额度
        # 检查安全模式限制
        # 占用资金
        return CapitalReservation(approved, reason, allocations)
    
    def release(self, reservation):
        """释放资金占用"""
        # 归还各交易所各层级的占用
    
    def update_drawdown(self, exchange, drawdown_pct):
        """更新回撤，触发安全模式"""
        if drawdown_pct >= self.drawdown_limit_pct:
            self.safe_mode = True
            # 仅允许 wash + reserve
```

**状态机**:
```
正常模式:
  ├─ 刷量层: ✅ 可用
  ├─ 套利层: ✅ 可用
  └─ 储备层: ✅ 可用

安全模式 (回撤 >= 5%):
  ├─ 刷量层: ✅ 可用（低风险）
  ├─ 套利层: ❌ 禁用（停止套利）
  └─ 储备层: ✅ 可用（应急对冲）
```

### 3. 交易所层 (`exchanges/`)

**职责**: 统一交易所接口

#### 3.1 基类 (`base.py`)
```python
class ExchangeBase(ABC):
    """抽象基类，定义统一接口"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """建立连接（REST + WebSocket）"""
    
    @abstractmethod
    async def place_order(self, symbol, side, size, price, order_type) -> Order:
        """下单"""
    
    @abstractmethod
    async def get_position(self, symbol) -> Position:
        """查询持仓"""
    
    @abstractmethod
    async def subscribe_orderbook(self, symbol):
        """订阅深度行情"""
```

#### 3.2 Paradex 客户端 (`paradex_client.py`)
```python
class ParadexClient(ExchangeBase):
    """
    Paradex DEX 客户端
    - Layer 2: Starknet
    - 认证: JWT + STARK 签名
    - 特点: 零 Maker 费
    """
    
    def __init__(self, config):
        self.api_key = os.getenv('PARADEX_API_KEY')
        self.private_key = os.getenv('PARADEX_PRIVATE_KEY')
        self.base_url = "https://api.paradex.trade/v1"
        self.ws_url = "wss://ws.paradex.trade"
    
    async def _sign_request(self, payload) -> str:
        """STARK 签名"""
        # 使用 starknet_py 签名
        return signature
    
    async def place_order(self, symbol, side, size, price, order_type):
        # 1. 构建订单数据
        # 2. STARK 签名
        # 3. 发送 POST /orders
        # 4. 解析响应
        return Order(...)
```

#### 3.3 Extended 客户端 (`extended_client.py`)
```python
class ExtendedClient(ExchangeBase):
    """
    Extended Exchange 客户端
    - Layer 2: Starknet
    - 认证: API Key + STARK 签名
    - 特点: 统一保证金，支持 TradFi 资产
    """
    
    async def place_order(self, symbol, side, size, price, order_type):
        # Extended 特殊要求:
        # 1. Market order 也需要 price
        # 2. 必须提供 fee 参数
        # 3. STARK 签名
        order_data = {
            "market": symbol,
            "side": side,
            "price": str(price),  # 必填
            "size": str(size),
            "fee": str(self._calculate_fee(size, price))  # 必填
        }
        return Order(...)
```

### 4. 策略层 (`strategy/`, `arbitrage/`)

#### 4.1 止盈策略 (`take_profit.py`)
```python
class TakeProfitStrategy:
    """
    自动止盈策略
    - 监控所有持仓
    - 达到目标利润自动平仓
    - 支持移动止损
    """
    
    async def check_and_close(self):
        for exchange in self.exchanges:
            positions = await exchange.get_positions()
            for pos in positions:
                pnl_pct = self._calculate_pnl_pct(pos)
                
                if pnl_pct >= self.target_profit_pct:
                    # 止盈平仓
                    await self._close_position(exchange, pos)
                
                elif pnl_pct <= -self.stop_loss_pct:
                    # 止损平仓
                    await self._close_position(exchange, pos)
```

#### 4.2 套利扫描器 (`arbitrage/scanner.py`)
```python
class ArbitrageScanner:
    """
    套利机会扫描器
    - 并发获取所有交易所报价
    - 计算跨所价差
    - 扣除交易成本（手续费 + 滑点 + Gas）
    - 评分排序
    """
    
    async def scan(self) -> List[ArbitrageOpportunity]:
        # 1. 并发获取报价
        quotes = await self._fetch_all_quotes()
        
        # 2. 寻找价差
        opportunities = []
        for symbol in self.symbols:
            # 找到最低买价和最高卖价
            best_buy = min(quotes[symbol], key=lambda q: q.ask)
            best_sell = max(quotes[symbol], key=lambda q: q.bid)
            
            # 3. 计算净利润
            spread_pct = (best_sell.bid - best_buy.ask) / best_buy.ask
            costs = self._calculate_costs(symbol, best_buy, best_sell)
            net_profit_pct = spread_pct - costs
            
            if net_profit_pct >= self.min_profit_pct:
                # 4. 评分
                score = self._calculate_score(
                    net_profit_pct,
                    best_buy.ask_size,
                    best_sell.bid_size,
                    best_buy.exchange,
                    best_sell.exchange
                )
                
                opportunities.append(ArbitrageOpportunity(...))
        
        # 5. 排序
        return sorted(opportunities, key=lambda x: x.score, reverse=True)
    
    def _calculate_score(self, profit, buy_liquidity, sell_liquidity, buy_ex, sell_ex):
        """
        评分算法:
        score = profit_weight * profit_pct
              + liquidity_weight * liquidity_score
              + reliability_weight * exchange_reliability
        """
        return score
```

#### 4.3 套利执行器 (`arbitrage/arbitrage_executor.py`)
```python
class ArbitrageExecutor:
    """
    套利执行器
    - 资金预留
    - 双边并发下单
    - 异常处理（单边成交、滑点等）
    - 自动对冲
    """
    
    async def execute(self, opportunity):
        # 1. 资金预留
        reservation = self.orchestrator.reserve_for_arb(
            exchanges=[opportunity.buy_exchange, opportunity.sell_exchange],
            amount=opportunity.size * opportunity.buy_price
        )
        
        if not reservation.approved:
            return ExecutionResult(success=False, reason=reservation.reason)
        
        try:
            # 2. 风险检查
            if not self.risk_manager.check(opportunity):
                return ExecutionResult(success=False, reason="风控拒绝")
            
            # 3. 并发下单
            buy_order, sell_order = await asyncio.gather(
                self._place_buy_order(opportunity),
                self._place_sell_order(opportunity)
            )
            
            # 4. 检查成交
            if buy_order.status != "FILLED" or sell_order.status != "FILLED":
                # 单边成交 → 对冲或取消
                await self._handle_partial_fill(buy_order, sell_order)
                return ExecutionResult(success=False, reason="部分成交")
            
            # 5. 记录结果
            return ExecutionResult(success=True, orders=[buy_order, sell_order])
        
        finally:
            # 6. 释放资金
            self.orchestrator.release(reservation)
```

### 5. 风控层 (`risk_manager.py`, `position_guard.py`)

#### 5.1 风险管理器 (`risk_manager.py`)
```python
class RiskManager:
    """
    账户级风控
    - 单笔风险限制
    - 最大回撤
    - 每日亏损限制
    - 连续失败保护
    - 快市冻结
    """
    
    def check(self, opportunity) -> Tuple[bool, str]:
        # 1. 单笔风险检查
        position_size = opportunity.size * opportunity.price
        if position_size > self.assumed_equity * self.max_risk_pct:
            return False, "单笔风险超限"
        
        # 2. 回撤检查
        if self.current_drawdown >= self.max_drawdown_pct:
            return False, "回撤超限，已暂停交易"
        
        # 3. 每日亏损检查
        if self.daily_pnl <= -self.daily_loss_limit:
            return False, "触达每日亏损上限"
        
        # 4. 连续失败检查
        if self.consecutive_failures >= self.max_consecutive_failures:
            if not self._manual_override_active():
                return False, "连续失败次数过多"
        
        # 5. 品种敞口检查
        current_exposure = self._get_symbol_exposure(opportunity.symbol)
        if current_exposure + position_size > self.max_symbol_exposure:
            return False, "品种敞口超限"
        
        # 6. 快市检查
        if self._is_fast_market(opportunity.symbol):
            return False, "快市冻结中"
        
        return True, "OK"
```

#### 5.2 仓位守卫 (`position_guard.py`)
```python
class PositionGuard:
    """
    仓位级风控
    - 单笔仓位大小限制
    - 仓位冷却时间
    - 集中度检查
    """
    
    def can_open_position(self, exchange, symbol, size) -> Tuple[bool, str]:
        # 1. 大小限制
        if size > self.max_position_size:
            return False, "仓位过大"
        
        # 2. 冷却检查
        if self._in_cooldown(exchange, symbol):
            return False, "冷却中"
        
        # 3. 集中度检查
        if self._exceeds_concentration_limit(exchange, symbol, size):
            return False, "集中度过高"
        
        return True, "OK"
    
    def record_failure(self, exchange, symbol):
        """记录失败，触发冷却"""
        self.cooldowns[(exchange, symbol)] = time.time() + self.cooldown_seconds
```

### 6. 监控层 (`monitoring/`)

#### 6.1 提醒系统 (`alerts.py`)
```python
class AlertSystem:
    """
    智能提醒系统
    - 多条件触发
    - 多渠道通知
    - 自动动作（启动交易/自动下单）
    """
    
    def __init__(self, config):
        self.rules = self._parse_alert_rules(config['alerts'])
        self.channels = self._init_channels(config['notifications'])
    
    async def check_alerts(self, market_data):
        for rule in self.rules:
            if self._should_trigger(rule, market_data):
                # 1. 通知
                await self._notify(rule, market_data)
                
                # 2. 执行动作
                if rule.action == "start-trading":
                    await self.trading_service.start()
                
                elif rule.action == "auto-order":
                    await self._place_order(rule)
                
                # 3. 记录
                self._record_alert(rule, market_data)
    
    def _should_trigger(self, rule, market_data):
        if rule.type == "price_breakout":
            current_price = market_data[rule.symbol].price
            if rule.direction == "above":
                return current_price >= rule.threshold
            else:
                return current_price <= rule.threshold
        
        elif rule.type == "price_spread":
            # 计算跨所价差
            spread = self._calculate_spread(rule.symbols, market_data)
            return abs(spread) >= rule.threshold_pct
        
        # ... 其他条件类型
```

#### 6.2 Web 控制台 (`web_console.py`)
```python
class TradingService:
    """
    Web 控制台后台服务
    - 主交易循环
    - WebSocket 实时推送
    - REST API 端点
    """
    
    def __init__(self):
        self.app = FastAPI()
        self.setup_routes()
        self.active_connections = []
    
    async def trading_loop(self):
        """主交易循环"""
        while self.running:
            try:
                # 1. 获取行情
                quotes = await self._fetch_quotes()
                
                # 2. 扫描套利
                opportunities = await self.scanner.scan(quotes)
                
                # 3. 执行套利
                if self.arbitrage_enabled:
                    for opp in opportunities[:3]:  # 前3个机会
                        await self.executor.execute(opp)
                
                # 4. 止盈检查
                await self.take_profit.check_and_close()
                
                # 5. 提醒检查
                await self.alerts.check_alerts(quotes)
                
                # 6. 推送更新
                await self._broadcast_update({
                    "quotes": quotes,
                    "opportunities": opportunities,
                    "positions": await self._get_positions()
                })
                
            except Exception as e:
                logger.error(f"交易循环异常: {e}")
            
            await asyncio.sleep(self.loop_interval)
    
    def setup_routes(self):
        @self.app.get("/api/overview")
        async def get_overview():
            return {
                "capital_snapshot": self.orchestrator.current_snapshot(),
                "total_trades": self.total_trades,
                "total_pnl": self.total_pnl
            }
        
        @self.app.post("/api/control/start")
        async def start_arbitrage():
            self.arbitrage_enabled = True
            return {"status": "success"}
        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket):
            await websocket.accept()
            self.active_connections.append(websocket)
            # 保持连接，推送更新
```

---

## 数据流

### 1. 行情获取流程

```
┌─────────────┐
│ 交易所 API  │
└──────┬──────┘
       │
       ├─ WebSocket (实时推送)
       │   ├─ 深度更新 → orderbook_cache
       │   ├─ 成交更新 → trade_cache
       │   └─ 价格更新 → price_cache
       │
       └─ REST API (回退/补充)
           └─ 轮询获取 → cache
           
┌──────────────────┐
│  Price Cache     │
│  • BTC-USD-PERP  │
│    - Paradex     │
│    - Extended    │
│  • ETH-USD-PERP  │
│    - Paradex     │
│    - Extended    │
└────────┬─────────┘
         │
         ↓
┌─────────────────┐
│  Strategy Layer │
│  • Scanner      │
│  • TakeProfit   │
└─────────────────┘
```

### 2. 套利执行流程

```
1. Scanner 发现套利机会
   ↓
2. 评分排序（利润 + 流动性 + 可靠性）
   ↓
3. Executor 开始执行
   ├─ (a) 申请资金
   │   ├─ CapitalOrchestrator.reserve_for_arb()
   │   ├─ 检查资金池可用额度
   │   ├─ 检查安全模式
   │   └─ 返回 Reservation 或拒绝
   │
   ├─ (b) 风控检查
   │   ├─ RiskManager.check()
   │   ├─ 单笔风险、回撤、每日亏损
   │   └─ 返回 OK 或拒绝
   │
   ├─ (c) 仓位检查
   │   ├─ PositionGuard.can_open_position()
   │   ├─ 大小、冷却、集中度
   │   └─ 返回 OK 或拒绝
   │
   ├─ (d) 并发下单
   │   ├─ asyncio.gather(
   │   │     place_buy_order(Paradex),
   │   │     place_sell_order(Extended)
   │   │   )
   │   └─ 等待成交确认
   │
   ├─ (e) 成交检查
   │   ├─ 两边都成交 → 成功
   │   ├─ 单边成交 → 对冲或取消
   │   └─ 都未成交 → 失败
   │
   ├─ (f) 记录结果
   │   ├─ 写入 trades.db
   │   ├─ 更新 PnL 统计
   │   └─ 记录到 orchestrator
   │
   └─ (g) 释放资金
       └─ CapitalOrchestrator.release()
```

### 3. 资金流转图

```
                  ┌───────────────────┐
                  │  Capital Pool     │
                  │  (总资金池)        │
                  └────────┬──────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌────▼────┐      ┌────▼────┐
    │ 刷量层   │      │ 套利层   │      │ 储备层   │
    │  70%    │      │  20%    │      │  10%    │
    │ (Wash)  │      │ (Arb)   │      │(Reserve)│
    └────┬────┘      └────┬────┘      └────┬────┘
         │                 │                 │
         │                 │                 │
    [占用 150]        [占用 500]        [占用 0]
    [可用 6850]       [可用 1500]       [可用 1000]
         │                 │                 │
         ↓                 ↓                 ↓
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │刷量策略  │       │套利策略  │       │应急对冲  │
    │HFT对冲  │       │跨所套利  │       │风险管理  │
    └─────────┘       └─────────┘       └─────────┘

回撤 >= 5% 触发安全模式:
    ┌─────────────────────────────────────┐
    │  安全模式                            │
    │  ├─ 刷量层: ✅ 继续                  │
    │  ├─ 套利层: ❌ 禁用                  │
    │  └─ 储备层: ✅ 应急                  │
    └─────────────────────────────────────┘
```

---

## 资金管理架构

### 三层资金池详细设计

```python
# 每个交易所独立维护三个资金池
ExchangePoolProfile = {
    "exchange": "paradex",
    "equity": 10000.0,  # 总权益
    "drawdown_pct": 0.03,  # 当前回撤 3%
    "safe_mode": False,
    
    "pools": {
        "wash": {
            "name": "刷量层",
            "budget_pct": 0.7,
            "pool": 7000.0,      # 总额度
            "allocated": 150.0,   # 已占用
            "available": 6850.0   # 可用
        },
        "arb": {
            "name": "套利层",
            "budget_pct": 0.2,
            "pool": 2000.0,
            "allocated": 500.0,
            "available": 1500.0
        },
        "reserve": {
            "name": "储备层",
            "budget_pct": 0.1,
            "pool": 1000.0,
            "allocated": 0.0,
            "available": 1000.0
        }
    }
}
```

### 策略到资金池的映射

```python
STRATEGY_POOL_MAPPING = {
    "wash_trade": "wash",    # 刷量对冲 → 刷量层
    "hft": "arb",            # 高频交易 → 套利层
    "flash": "arb",          # 闪电套利 → 套利层
    "stat": "arb",           # 统计套利 → 套利层
    "mid_freq": "arb",       # 中频交易 → 套利层
    "funding": "reserve",    # 资金费率 → 储备层
    "arbitrage": "arb",      # 跨所套利 → 套利层
    "emergency": "reserve"   # 应急操作 → 储备层
}
```

### 资金预留与释放生命周期

```python
# 1. 预留
reservation = orchestrator.reserve_for_strategy(
    exchanges=["paradex", "extended"],
    amount=100.0,
    strategy="arbitrage"  # → 映射到 "arb" 层
)

# 内部逻辑:
# - 检查 paradex.arb.available >= 100
# - 检查 extended.arb.available >= 100
# - 检查是否在安全模式（若是，arb 层被禁用）
# - 占用资金: allocated += 100
# - 返回 reservation 对象

# 2. 使用（执行交易）
if reservation.approved:
    result = await execute_trade(...)

# 3. 释放
orchestrator.release(reservation)

# 内部逻辑:
# - paradex.arb.allocated -= 100
# - extended.arb.allocated -= 100
# - 记录 PnL
```

---

## 交易执行流程

### 完整的订单生命周期

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: 准备阶段                                           │
├─────────────────────────────────────────────────────────────┤
│  1. Scanner 发现套利机会                                     │
│     ├─ Paradex BTC-USD-PERP: Buy @ $95,123.45             │
│     └─ Extended BTC-USD-PERP: Sell @ $95,234.56           │
│     └─ 价差: 0.12%, 扣除成本后: 0.06%                      │
│                                                             │
│  2. 评分与排序                                               │
│     ├─ profit_score: 8/10                                  │
│     ├─ liquidity_score: 7/10                               │
│     ├─ reliability_score: 9/10                             │
│     └─ final_score: 8.1                                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: 风控检查                                           │
├─────────────────────────────────────────────────────────────┤
│  3. 资金预留                                                 │
│     ├─ CapitalOrchestrator.reserve_for_arb()               │
│     ├─ Paradex 套利层: 需要 100 USDT, 可用 1500 USDT → ✅ │
│     └─ Extended 套利层: 需要 100 USDT, 可用 1500 USDT → ✅│
│                                                             │
│  4. 风险检查                                                 │
│     ├─ 单笔风险: 100 / 10000 = 1% < 5% → ✅               │
│     ├─ 回撤: 3% < 10% → ✅                                 │
│     ├─ 每日亏损: -50 > -500 → ✅                           │
│     ├─ 连续失败: 0 < 3 → ✅                                │
│     └─ 快市: 否 → ✅                                        │
│                                                             │
│  5. 仓位检查                                                 │
│     ├─ 大小: 100 < 最大仓位 → ✅                           │
│     ├─ 冷却: 否 → ✅                                        │
│     └─ 集中度: OK → ✅                                      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: 下单执行                                           │
├─────────────────────────────────────────────────────────────┤
│  6. 并发下单                                                 │
│     ┌───────────────────────────────────────────────────┐  │
│     │  asyncio.gather(                                  │  │
│     │    place_buy_order(                               │  │
│     │      exchange=Paradex,                            │  │
│     │      symbol="BTC-USD-PERP",                       │  │
│     │      side="BUY",                                  │  │
│     │      size=0.001,                                  │  │
│     │      price=95123.45                               │  │
│     │    ),                                             │  │
│     │    place_sell_order(                              │  │
│     │      exchange=Extended,                           │  │
│     │      symbol="BTC-USD-PERP",                       │  │
│     │      side="SELL",                                 │  │
│     │      size=0.001,                                  │  │
│     │      price=95234.56                               │  │
│     │    )                                              │  │
│     │  )                                                │  │
│     └───────────────────────────────────────────────────┘  │
│                                                             │
│  7. 等待成交（最多 30 秒）                                   │
│     ├─ 轮询订单状态                                         │
│     └─ 超时则取消                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: 成交处理                                           │
├─────────────────────────────────────────────────────────────┤
│  8. 检查成交情况                                             │
│     ├─ Case A: 两边都成交 → 完美执行                       │
│     ├─ Case B: 单边成交 → 立即对冲或取消                   │
│     └─ Case C: 都未成交 → 失败，释放资金                   │
│                                                             │
│  9. Case A: 成功流程                                        │
│     ├─ 记录持仓                                             │
│     │   ├─ Paradex: LONG 0.001 BTC @ 95123.45           │
│     │   └─ Extended: SHORT 0.001 BTC @ 95234.56         │
│     ├─ 等待价差收敛                                         │
│     ├─ 止盈平仓（目标 1% 或价差消失）                       │
│     └─ 记录 PnL: +0.06% = +5.7 USDT                       │
│                                                             │
│ 10. Case B: 部分成交处理                                     │
│     ├─ 假设 Paradex 成交，Extended 未成交                  │
│     ├─ 选项 1: 立即在 Extended 对冲开仓                    │
│     └─ 选项 2: 取消 Paradex 订单（若未成交）               │
│                                                             │
│ 11. Case C: 失败处理                                         │
│     ├─ 记录失败原因                                         │
│     ├─ 触发冷却（60 秒）                                    │
│     └─ 告警通知                                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: 清理与记录                                         │
├─────────────────────────────────────────────────────────────┤
│ 12. 释放资金                                                 │
│     ├─ orchestrator.release(reservation)                   │
│     └─ 归还 Paradex 和 Extended 的套利层占用               │
│                                                             │
│ 13. 记录交易                                                 │
│     ├─ 写入 trades.db                                      │
│     ├─ 更新统计指标                                         │
│     └─ 推送到 Web 控制台                                    │
│                                                             │
│ 14. 更新风控状态                                             │
│     ├─ 成功: consecutive_failures = 0                      │
│     ├─ 失败: consecutive_failures += 1                     │
│     └─ 更新回撤、PnL 等指标                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 风控体系

### 多层风控架构

```
┌─────────────────────────────────────────────────────────────┐
│  Level 1: 资金层风控 (Capital Orchestrator)                  │
├─────────────────────────────────────────────────────────────┤
│  • 资金池额度限制                                             │
│  • 安全模式触发（回撤 >= 5%）                                 │
│  • 跨层借用控制                                               │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│  Level 2: 账户层风控 (Risk Manager)                          │
├─────────────────────────────────────────────────────────────┤
│  • 单笔风险上限: 5% 账户权益                                  │
│  • 最大回撤: 10%                                              │
│  • 每日亏损限制: 5% 或绝对金额                                │
│  • 连续失败保护: 3 次暂停                                     │
│  • 品种敞口上限: 30%                                          │
│  • 方向一致性: 禁止同品种双向                                 │
│  • 快市冻结: 1秒内 0.5% 波动                                 │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│  Level 3: 仓位层风控 (Position Guard)                        │
├─────────────────────────────────────────────────────────────┤
│  • 单笔仓位大小限制                                           │
│  • 仓位冷却时间（失败后 60s）                                 │
│  • 仓位集中度检查                                             │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│  Level 4: 执行层风控 (Executor)                              │
├─────────────────────────────────────────────────────────────┤
│  • 滑点上限: 0.1%                                            │
│  • 执行超时: 30 秒                                            │
│  • 部分成交对冲                                               │
│  • 异常价格过滤                                               │
└─────────────────────────────────────────────────────────────┘
```

### 风控决策树

```
订单请求
    ↓
[资金层检查]
    ├─ 资金池可用? 
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "资金不足"
    │
    ├─ 安全模式?
    │   ├─ No → 继续
    │   └─ Yes → 检查策略
    │       ├─ 刷量/储备 → 继续
    │       └─ 套利 → 拒绝 "安全模式禁止套利"
    ↓
[账户层检查]
    ├─ 单笔风险 < 5%?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "单笔风险超限"
    │
    ├─ 回撤 < 10%?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "回撤超限"
    │
    ├─ 每日亏损 < 限制?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "每日亏损超限"
    │
    ├─ 连续失败 < 3?
    │   ├─ Yes → 继续
    │   └─ No → 检查人工覆盖
    │       ├─ 有效 → 继续
    │       └─ 无效 → 拒绝 "连续失败过多"
    │
    ├─ 品种敞口 < 30%?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "敞口超限"
    │
    ├─ 快市冻结?
    │   ├─ No → 继续
    │   └─ Yes → 拒绝 "快市冻结"
    ↓
[仓位层检查]
    ├─ 仓位大小 OK?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "仓位过大"
    │
    ├─ 冷却中?
    │   ├─ No → 继续
    │   └─ Yes → 拒绝 "冷却中"
    │
    ├─ 集中度 OK?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "集中度过高"
    ↓
[执行层检查]
    ├─ 滑点 < 0.1%?
    │   ├─ Yes → 继续
    │   └─ No → 拒绝 "滑点过大"
    │
    ├─ 价格异常?
    │   ├─ No → 继续
    │   └─ Yes → 拒绝 "价格异常"
    ↓
✅ 批准下单
```

---

## 监控与告警

### 监控指标体系

```
┌─────────────────────────────────────────────────────────────┐
│  系统健康度指标                                               │
├─────────────────────────────────────────────────────────────┤
│  • 运行时间 (Uptime)                                         │
│  • CPU / 内存使用率                                          │
│  • 网络延迟                                                   │
│  • WebSocket 连接状态                                        │
│  • API 调用成功率                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  交易性能指标                                                 │
├─────────────────────────────────────────────────────────────┤
│  • 总交易笔数                                                 │
│  • 成功率                                                     │
│  • 平均执行时间                                               │
│  • 滑点分布                                                   │
│  • PnL (日/周/月/总)                                         │
│  • 夏普比率                                                   │
│  • 最大回撤                                                   │
│  • 胜率                                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  资金指标                                                     │
├─────────────────────────────────────────────────────────────┤
│  • 各层资金占用率                                             │
│  • 安全模式状态                                               │
│  • 累计成交量                                                 │
│  • 累计手续费                                                 │
│  • 资金曲线                                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  风险指标                                                     │
├─────────────────────────────────────────────────────────────┤
│  • 当前回撤                                                   │
│  • 今日 PnL                                                  │
│  • 连续失败次数                                               │
│  • 各品种敞口                                                 │
│  • 快市冻结状态                                               │
└─────────────────────────────────────────────────────────────┘
```

### 告警规则示例

```yaml
# 系统告警
- name: "WebSocket 断线"
  type: "system"
  condition: "websocket_disconnected"
  channels: ["telegram", "audio"]
  severity: "high"

- name: "API 调用失败率过高"
  type: "system"
  condition: "api_failure_rate > 10%"
  channels: ["telegram"]
  severity: "medium"

# 交易告警
- name: "单笔亏损过大"
  type: "trading"
  condition: "single_trade_loss > 50 USDT"
  channels: ["telegram", "lark"]
  severity: "high"

- name: "连续失败"
  type: "trading"
  condition: "consecutive_failures >= 3"
  channels: ["telegram", "audio"]
  severity: "high"
  action: "pause-trading"

# 风险告警
- name: "触达每日亏损上限"
  type: "risk"
  condition: "daily_pnl <= -daily_loss_limit"
  channels: ["telegram", "lark", "audio"]
  severity: "critical"
  action: "emergency-stop"

- name: "回撤超限"
  type: "risk"
  condition: "drawdown >= max_drawdown"
  channels: ["telegram", "lark", "audio"]
  severity: "critical"
  action: "pause-trading"

# 市场告警
- name: "价格异常波动"
  type: "market"
  condition: "price_change > 5% in 1 minute"
  channels: ["telegram"]
  severity: "medium"
  action: "freeze-trading"
```

---

## 技术选型

### 核心依赖

| 库 | 版本 | 用途 |
|---|------|------|
| Python | 3.10+ | 语言基础 |
| asyncio | - | 异步并发 |
| aiohttp | 3.9+ | 异步 HTTP |
| websockets | 12.0+ | WebSocket 客户端 |
| FastAPI | 0.104+ | Web API 框架 |
| uvicorn | 0.24+ | ASGI 服务器 |
| PyYAML | 6.0+ | 配置解析 |
| python-dotenv | 1.0+ | 环境变量 |
| cryptography | 41.0+ | 密钥加密 |
| starknet-py | 0.20+ | Starknet 签名 |
| web3 | 6.11+ | 以太坊交互 |
| ccxt | 4.0+ | 统一交易所接口 |
| pandas | 2.1+ | 数据分析 |
| numpy | 1.26+ | 数值计算 |

### 为什么选择这些技术？

**1. Python 3.10+**
- ✅ 类型注解增强
- ✅ 异步生态成熟
- ✅ 丰富的金融库
- ✅ 快速迭代

**2. asyncio**
- ✅ 原生异步支持
- ✅ 高并发性能
- ✅ 适合 I/O 密集任务（API 调用）

**3. FastAPI**
- ✅ 自动 API 文档
- ✅ 类型验证
- ✅ WebSocket 支持
- ✅ 高性能（基于 Starlette）

**4. starknet-py**
- ✅ Paradex/Extended 都基于 Starknet
- ✅ 提供签名工具
- ✅ 官方支持

---

## 扩展性设计

### 1. 新增交易所

```python
# 1. 创建新的客户端类
class NewExchangeClient(ExchangeBase):
    """新交易所客户端"""
    
    async def connect(self):
        # 实现连接逻辑
        pass
    
    async def place_order(self, ...):
        # 实现下单逻辑
        pass
    
    # ... 实现其他抽象方法

# 2. 在配置中注册
# config.yaml
exchanges:
  new_exchange:
    enabled: true
    type: "dex"
    min_order_size: 10.0

# 3. 初始化时加载
exchanges["new_exchange"] = NewExchangeClient(config)

# 4. 自动参与套利扫描和执行
```

### 2. 新增策略

```python
# 1. 创建策略类
class MyCustomStrategy:
    """自定义策略"""
    
    async def analyze(self, market_data):
        # 分析逻辑
        return signals
    
    async def execute(self, signals):
        # 执行逻辑
        pass

# 2. 注册到主循环
trading_service.strategies.append(MyCustomStrategy())

# 3. 自动调用
```

### 3. 新增风控规则

```python
# 扩展 RiskManager
class CustomRiskManager(RiskManager):
    def check(self, opportunity):
        # 调用父类检查
        ok, reason = super().check(opportunity)
        if not ok:
            return ok, reason
        
        # 添加自定义规则
        if self._custom_check(opportunity):
            return True, "OK"
        else:
            return False, "自定义规则拒绝"
```

### 4. 新增告警渠道

```python
# 实现新的通知器
class DiscordNotifier:
    async def send(self, message):
        # Discord webhook 逻辑
        pass

# 注册到 AlertSystem
alert_system.channels["discord"] = DiscordNotifier()
```

---

## 总结

PerpBot 采用**分层架构**和**模块化设计**，确保：

✅ **高内聚低耦合**: 每个模块职责明确
✅ **易于测试**: 每层可独立测试
✅ **灵活扩展**: 新增交易所/策略/风控规则简单
✅ **强风控**: 多层风控体系保护资金安全
✅ **可观测**: 完整的监控和告警体系
✅ **配置驱动**: 参数可调，无需修改代码

通过清晰的**数据流**和**执行流程**，开发者可以快速理解系统运作，并进行二次开发。

---

**最后更新**: 2024-12-08  
**文档版本**: v1.0  
**作者**: Claude (Anthropic)
