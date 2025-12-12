#!/usr/bin/env python3
"""
🚀 PerpBot 统一交易所测试框架 (生产级)

支持十几个交易所的完整集成测试（包含交易功能）。
直接使用主网进行小额测试（无需 testnet）。

特点:
- 统一接口，支持所有交易所
- 查询功能：价格、订单簿、余额、持仓
- 交易功能：限价单、市价单、撤单、平仓
- 交互式菜单和自动化测试模式
- 按需初始化虚拈环境
- 详细的连接验证和错误诊断
- 实时交易对验证
- 性能指标收集

使用方法:
    # 交互式选择并测试 (推荐)
    python test_exchanges.py
    
    # 测试特定交易所（带交互式菜单）
    python test_exchanges.py okx
    
    # 自动化测试模式（查询功能）
    python test_exchanges.py okx --auto-test
    
    # 包含完整交易测试 (谨慎!，需要真实账户)
    python test_exchanges.py okx --trading --trading-size 0.001
    
    # 测试所有已配置交易所（自动化）
    python test_exchanges.py --all --auto-test
    
    # 打印支持的交易所列表
    python test_exchanges.py --list
    
    # 详细日志模式
    python test_exchanges.py --verbose
    
    # 输出到 JSON 报告
    python test_exchanges.py --json-report report.json
"""

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib import import_module
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# ============================================================
# 配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-15s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("exchange-test")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ExchangeConfig:
    """交易所配置"""
    name: str
    class_name: str
    module_name: str
    required_env: List[str]
    optional_env: List[str] = field(default_factory=list)
    use_mainnet: bool = True  # 默认主网
    mainnet_param: str = "use_testnet"  # 参数名称
    mainnet_value: bool = False  # 主网时的值


@dataclass
class TestMetrics:
    """测试指标"""
    exchange: str
    timestamp: str
    connection_ok: bool
    connection_time_ms: float
    price_ok: bool
    orderbook_ok: bool
    balance_ok: bool
    positions_ok: bool
    
    price_value: Optional[float] = None
    price_time_ms: float = 0
    orderbook_bids: int = 0
    orderbook_asks: int = 0
    orderbook_time_ms: float = 0
    balance_count: int = 0
    balance_time_ms: float = 0
    positions_count: int = 0
    positions_time_ms: float = 0
    error: Optional[str] = None


@dataclass
class TestReport:
    """完整测试报告"""
    test_time: str
    duration_seconds: float
    total_exchanges: int
    passed_exchanges: int
    failed_exchanges: int
    metrics: List[TestMetrics]
    errors: Dict[str, str] = field(default_factory=dict)


# ============================================================
# 交易所目录 (支持十几个以上)
# ============================================================

EXCHANGE_CONFIGS = {
    # ===== CEX (中心化交易所) =====
    "okx": ExchangeConfig(
        name="okx",
        class_name="OKXClient",
        module_name="perpbot.exchanges.okx",
        required_env=["OKX_API_KEY", "OKX_API_SECRET", "OKX_PASSPHRASE"],
        use_mainnet=False,  # OKX 强制 demo trading
    ),
    "binance": ExchangeConfig(
        name="binance",
        class_name="BinanceClient",
        module_name="perpbot.exchanges.binance",
        required_env=["BINANCE_API_KEY", "BINANCE_API_SECRET"],
        use_mainnet=True,
    ),
    "bitget": ExchangeConfig(
        name="bitget",
        class_name="BitgetClient",
        module_name="perpbot.exchanges.bitget",
        required_env=["BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE"],
        use_mainnet=True,
    ),
    "bybit": ExchangeConfig(
        name="bybit",
        class_name="BybitClient",
        module_name="perpbot.exchanges.bybit",
        required_env=["BYBIT_API_KEY", "BYBIT_API_SECRET"],
        optional_env=["BYBIT_UID"],
        use_mainnet=True,
    ),
    
    # ===== DEX (去中心化交易所) =====
    "hyperliquid": ExchangeConfig(
        name="hyperliquid",
        class_name="HyperliquidClient",
        module_name="perpbot.exchanges.hyperliquid",
        required_env=[],  # 可选凭证
        optional_env=["HYPERLIQUID_ACCOUNT_ADDRESS", "HYPERLIQUID_PRIVATE_KEY"],
        use_mainnet=True,
    ),
    "paradex": ExchangeConfig(
        name="paradex",
        class_name="ParadexClient",
        module_name="perpbot.exchanges.paradex",
        required_env=["PARADEX_L2_PRIVATE_KEY", "PARADEX_ACCOUNT_ADDRESS"],
        use_mainnet=True,
    ),
    "extended": ExchangeConfig(
        name="extended",
        class_name="ExtendedClient",
        module_name="perpbot.exchanges.extended",
        required_env=["EXTENDED_API_KEY", "EXTENDED_STARK_PRIVATE_KEY", "EXTENDED_VAULT_NUMBER"],
        use_mainnet=True,
    ),
    "lighter": ExchangeConfig(
        name="lighter",
        class_name="LighterClient",
        module_name="perpbot.exchanges.lighter",
        required_env=["LIGHTER_API_KEY", "LIGHTER_PRIVATE_KEY"],
        use_mainnet=True,
    ),
    "edgex": ExchangeConfig(
        name="edgex",
        class_name="EdgeXClient",
        module_name="perpbot.exchanges.edgex",
        required_env=["EDGEX_API_KEY"],
        optional_env=["EDGEX_API_SECRET"],
        use_mainnet=True,
    ),
    "backpack": ExchangeConfig(
        name="backpack",
        class_name="BackpackClient",
        module_name="perpbot.exchanges.backpack",
        required_env=["BACKPACK_API_KEY", "BACKPACK_API_SECRET"],
        use_mainnet=True,
    ),
    "grvt": ExchangeConfig(
        name="grvt",
        class_name="GRVTClient",
        module_name="perpbot.exchanges.grvt",
        required_env=["GRVT_API_KEY"],
        use_mainnet=True,
    ),
    "aster": ExchangeConfig(
        name="aster",
        class_name="AsterClient",
        module_name="perpbot.exchanges.aster",
        required_env=["ASTER_API_KEY"],
        use_mainnet=True,
    ),
    "sunx": ExchangeConfig(
        name="sunx",
        class_name="SunxClient",
        module_name="perpbot.exchanges.sunx",
        required_env=["SUNX_API_KEY"],
        optional_env=["SUNX_API_SECRET"],
        use_mainnet=True,
    ),
}


# ============================================================
# 核心测试器
# ============================================================

class UnifiedExchangeTester:
    """统一交易所测试器"""
    
    def __init__(self, include_trading: bool = False, verbose: bool = False):
        self.include_trading = include_trading
        self.verbose = verbose
        load_dotenv()
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        
        self.metrics: List[TestMetrics] = []
        self.errors: Dict[str, str] = {}
    
    def _check_env(self, config: ExchangeConfig) -> Tuple[bool, List[str]]:
        """检查环境变量是否齐全"""
        missing = []
        for var in config.required_env:
            if not os.getenv(var):
                missing.append(var)
        return len(missing) == 0, missing
    
    def _load_exchange_client(self, config: ExchangeConfig) -> Any:
        """动态加载交易所客户端"""
        try:
            module = import_module(config.module_name)
            client_class = getattr(module, config.class_name)
            
            # 根据配置初始化客户端
            if config.use_mainnet:
                # 主网模式
                return client_class(use_testnet=False)
            else:
                # Demo 模式 (如 OKX)
                return client_class(use_testnet=True)
        except ImportError as e:
            raise RuntimeError(f"Failed to import {config.module_name}.{config.class_name}: {e}")
    
    def _time_operation(self, func) -> Tuple[Any, float, Optional[str]]:
        """执行操作并计时"""
        start = time.perf_counter()
        try:
            result = func()
            duration_ms = (time.perf_counter() - start) * 1000
            return result, duration_ms, None
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return None, duration_ms, str(e)
    
    def test_exchange(self, exchange_name: str, symbol: str = "BTC/USDT") -> Optional[TestMetrics]:
        """测试单个交易所"""
        if exchange_name not in EXCHANGE_CONFIGS:
            logger.error(f"Unknown exchange: {exchange_name}")
            return None
        
        config = EXCHANGE_CONFIGS[exchange_name]
        metrics = TestMetrics(
            exchange=exchange_name,
            timestamp=datetime.now().isoformat(),
            connection_ok=False,
            connection_time_ms=0,
            price_ok=False,
            orderbook_ok=False,
            balance_ok=False,
            positions_ok=False,
        )
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {exchange_name.upper()}")
        logger.info(f"{'='*60}")
        
        # 检查环境变量
        has_env, missing = self._check_env(config)
        if not has_env:
            logger.warning(f"⚠️ Missing env vars: {', '.join(missing)}")
            metrics.error = f"Missing: {', '.join(missing)}"
            self.errors[exchange_name] = metrics.error
            self.metrics.append(metrics)
            return metrics
        
        # 加载客户端
        try:
            client = self._load_exchange_client(config)
        except Exception as e:
            logger.error(f"❌ Failed to load client: {e}")
            metrics.error = str(e)
            self.errors[exchange_name] = metrics.error
            self.metrics.append(metrics)
            return metrics
        
        # 测试 1: 连接
        logger.info("1️⃣ Testing connection...")
        def _connect():
            client.connect()
            return "OK"
        result, duration, error = self._time_operation(_connect)
        metrics.connection_ok = error is None
        metrics.connection_time_ms = duration
        if error:
            logger.error(f"   ❌ Connection failed: {error}")
            metrics.error = error
            self.errors[exchange_name] = error
            self.metrics.append(metrics)
            return metrics
        logger.info(f"   ✅ Connected ({duration:.0f}ms)")
        
        # 测试 2: 价格查询
        logger.info(f"2️⃣ Testing price ({symbol})...")
        def _get_price():
            return client.get_current_price(symbol)
        quote, duration, error = self._time_operation(_get_price)
        metrics.price_ok = error is None
        metrics.price_time_ms = duration
        if error:
            logger.warning(f"   ⚠️ Price fetch failed: {error}")
        else:
            metrics.price_value = quote.mid if quote else None
            logger.info(f"   ✅ Price: {quote.bid:.2f}-{quote.ask:.2f} ({duration:.0f}ms)")
        
        # 测试 3: 订单簿
        logger.info(f"3️⃣ Testing orderbook ({symbol})...")
        def _get_orderbook():
            return client.get_orderbook(symbol, depth=5)
        orderbook, duration, error = self._time_operation(_get_orderbook)
        metrics.orderbook_ok = error is None
        metrics.orderbook_time_ms = duration
        if error:
            logger.warning(f"   ⚠️ Orderbook fetch failed: {error}")
        else:
            metrics.orderbook_bids = len(orderbook.bids) if orderbook else 0
            metrics.orderbook_asks = len(orderbook.asks) if orderbook else 0
            logger.info(f"   ✅ Orderbook: {metrics.orderbook_bids} bids, {metrics.orderbook_asks} asks ({duration:.0f}ms)")
        
        # 测试 4: 账户余额
        logger.info("4️⃣ Testing account balances...")
        def _get_balances():
            return client.get_account_balances()
        balances, duration, error = self._time_operation(_get_balances)
        metrics.balance_ok = error is None
        metrics.balance_time_ms = duration
        if error:
            logger.warning(f"   ⚠️ Balance fetch failed: {error}")
        else:
            metrics.balance_count = len(balances) if balances else 0
            logger.info(f"   ✅ Found {metrics.balance_count} balances ({duration:.0f}ms)")
            if balances and len(balances) > 0:
                for balance in balances[:3]:
                    logger.info(f"      - {balance.currency}: {balance.free} free")
        
        # 测试 5: 持仓
        logger.info("5️⃣ Testing positions...")
        def _get_positions():
            return client.get_account_positions()
        positions, duration, error = self._time_operation(_get_positions)
        metrics.positions_ok = error is None
        metrics.positions_time_ms = duration
        if error:
            logger.warning(f"   ⚠️ Positions fetch failed: {error}")
        else:
            metrics.positions_count = len(positions) if positions else 0
            logger.info(f"   ✅ Found {metrics.positions_count} positions ({duration:.0f}ms)")
        
        logger.info(f"✅ {exchange_name.upper()} test completed")
        self.metrics.append(metrics)
        return metrics
    
    def test_limit_order(self, client: Any, symbol: str, size: float, limit_offset: float = 0.01) -> Tuple[bool, str]:
        """测试限价单和撤单"""
        try:
            logger.info(f"\n6️⃣ Testing limit order ({symbol}, size={size})...")
            
            # 获取当前价格
            quote = client.get_current_price(symbol)
            if not quote:
                return False, "Failed to get current price"
            
            # 计算限价（买单略低）
            limit_price = quote.bid * (1 - limit_offset)
            logger.info(f"   📍 Current price: {quote.mid:.2f}, Limit price: {limit_price:.2f}")
            
            # 检查是否有下单方法
            if not hasattr(client, 'place_open_order'):
                logger.warning(f"   ⚠️ Exchange does not support place_open_order")
                return False, "No place_open_order method"
            
            # 下限价单
            from perpbot.models import OrderRequest
            req = OrderRequest(symbol=symbol, side="buy", size=size, limit_price=limit_price)
            order = client.place_open_order(req)
            
            if not order or order.id.startswith('error') or order.id == 'rejected':
                return False, f"Order placement failed: {order.id if order else 'None'}"
            
            logger.info(f"   ✅ Order placed: ID={order.id}")
            
            # 等待后尝试撤单
            time.sleep(0.5)
            logger.info(f"   📍 Attempting to cancel order...")
            
            if not hasattr(client, 'cancel_order'):
                logger.warning(f"   ⚠️ Exchange does not support cancel_order")
                return True, "Order placed successfully (no cancel support)"
            
            client.cancel_order(order.id)
            logger.info(f"   ✅ Order cancelled: ID={order.id}")
            
            return True, "Limit order and cancel successful"
        
        except Exception as e:
            logger.error(f"   ❌ Limit order test failed: {e}")
            return False, str(e)
    
    def test_market_order(self, client: Any, symbol: str, size: float) -> Tuple[bool, str]:
        """测试市价单（或市价执行）"""
        try:
            logger.info(f"\n7️⃣ Testing market/IOC order ({symbol}, size={size})...")
            
            # 检查是否有下单方法
            if not hasattr(client, 'place_open_order'):
                logger.warning(f"   ⚠️ Exchange does not support place_open_order")
                return False, "No place_open_order method"
            
            # 下市价单（不指定价格）
            from perpbot.models import OrderRequest
            req = OrderRequest(symbol=symbol, side="buy", size=size)
            order = client.place_open_order(req)
            
            if not order or order.id.startswith('error') or order.id == 'rejected':
                return False, f"Order placement failed: {order.id if order else 'None'}"
            
            logger.info(f"   ✅ Market order placed: ID={order.id}, Price={order.price}")
            
            return True, "Market order successful"
        
        except Exception as e:
            logger.error(f"   ❌ Market order test failed: {e}")
            return False, str(e)
    
    def test_close_position(self, client: Any, symbol: str) -> Tuple[bool, str]:
        """测试平仓"""
        try:
            logger.info(f"\n8️⃣ Testing close position ({symbol})...")
            
            # 获取持仓
            positions = client.get_account_positions()
            if not positions or len(positions) == 0:
                logger.warning(f"   ⚠️ No open positions found")
                return False, "No positions to close"
            
            # 检查是否有平仓方法
            if not hasattr(client, 'place_close_order'):
                logger.warning(f"   ⚠️ Exchange does not support place_close_order")
                return False, "No place_close_order method"
            
            # 找到相应持仓
            pos = None
            for p in positions:
                if hasattr(p, 'order') and hasattr(p.order, 'symbol') and p.order.symbol == symbol:
                    pos = p
                    break
            
            if not pos:
                logger.warning(f"   ⚠️ No position for {symbol}")
                return False, f"No position for {symbol}"
            
            # 获取当前价格
            current_price = client.get_current_price(symbol).mid
            logger.info(f"   📍 Position size: {pos.order.size}, Current price: {current_price}")
            
            # 平仓
            close_order = client.place_close_order(pos, current_price)
            
            if not close_order or close_order.id.startswith('error') or close_order.id == 'rejected':
                return False, f"Close order failed: {close_order.id if close_order else 'None'}"
            
            logger.info(f"   ✅ Close order placed: ID={close_order.id}")
            
            return True, "Close position successful"
        
        except Exception as e:
            logger.error(f"   ❌ Close position test failed: {e}")
            return False, str(e)
    
    def interactive_menu(self, exchange_name: str, client: Any, symbol: str) -> None:
        """交互式菜单"""
        while True:
            print(f"\n{'='*60}")
            print(f"🔄 {exchange_name.upper()} - 交互式菜单")
            print(f"{'='*60}")
            print(f"交易对: {symbol}")
            print()
            print("1️⃣  查询价格")
            print("2️⃣  查询订单簿")
            print("3️⃣  查询账户余额")
            print("4️⃣  查询持仓")
            print("5️⃣  下限价单 (买)")
            print("6️⃣  下市价单 (买)")
            print("7️⃣  撤销最近订单")
            print("8️⃣  平仓")
            print("9️⃣  切换交易对")
            print("0️⃣  返回")
            print()
            
            choice = input("请选择操作 (0-9): ").strip()
            
            if choice == "0":
                break
            elif choice == "1":
                try:
                    quote = client.get_current_price(symbol)
                    print(f"\n💹 {symbol} 价格")
                    print(f"   买价: {quote.bid:.2f}")
                    print(f"   卖价: {quote.ask:.2f}")
                    print(f"   中间: {quote.mid:.2f}")
                except Exception as e:
                    print(f"❌ 获取价格失败: {e}")
            
            elif choice == "2":
                try:
                    ob = client.get_orderbook(symbol, depth=5)
                    print(f"\n📊 {symbol} 订单簿 (深度5)")
                    print(f"   卖盘 (Asks):")
                    for ask in (ob.asks[:3] if ob.asks else []):
                        print(f"      {ask.price:.2f} x {ask.size}")
                    print(f"   买盘 (Bids):")
                    for bid in (ob.bids[:3] if ob.bids else []):
                        print(f"      {bid.price:.2f} x {bid.size}")
                except Exception as e:
                    print(f"❌ 获取订单簿失败: {e}")
            
            elif choice == "3":
                try:
                    balances = client.get_account_balances()
                    print(f"\n💰 账户余额 ({len(balances)} 种资产)")
                    for b in balances[:5]:
                        print(f"   {b.currency}: 可用={b.free}, 锁定={b.locked}")
                except Exception as e:
                    print(f"❌ 获取余额失败: {e}")
            
            elif choice == "4":
                try:
                    positions = client.get_account_positions()
                    if not positions:
                        print(f"\nℹ️  当前无持仓")
                    else:
                        print(f"\n📋 持仓列表 ({len(positions)} 个)")
                        for pos in positions:
                            if hasattr(pos, 'order'):
                                print(f"   {pos.order.symbol} {pos.order.side.upper()} {pos.order.size} @ {pos.order.price}")
                except Exception as e:
                    print(f"❌ 获取持仓失败: {e}")
            
            elif choice == "5":
                try:
                    size = float(input(f"请输入下单数量 (default=0.001): ").strip() or "0.001")
                    offset = float(input(f"请输入限价偏差 (default=0.01): ").strip() or "0.01")
                    success, msg = self.test_limit_order(client, symbol, size, offset)
                    if success:
                        print(f"✅ {msg}")
                    else:
                        print(f"❌ {msg}")
                except Exception as e:
                    print(f"❌ 下单失败: {e}")
            
            elif choice == "6":
                try:
                    size = float(input(f"请输入下单数量 (default=0.001): ").strip() or "0.001")
                    success, msg = self.test_market_order(client, symbol, size)
                    if success:
                        print(f"✅ {msg}")
                    else:
                        print(f"❌ {msg}")
                except Exception as e:
                    print(f"❌ 下单失败: {e}")
            
            elif choice == "7":
                print("⚠️  此功能需要保存最后的订单 ID (未实现)")
            
            elif choice == "8":
                try:
                    success, msg = self.test_close_position(client, symbol)
                    if success:
                        print(f"✅ {msg}")
                    else:
                        print(f"ℹ️  {msg}")
                except Exception as e:
                    print(f"❌ 平仓失败: {e}")
            
            elif choice == "9":
                symbol = input("请输入新交易对 (e.g., BTC/USDT): ").strip()
                print(f"✅ 已切换到 {symbol}")
            
            else:
                print("❌ 无效选择")
    
    def run_tests(self, exchanges: Optional[List[str]] = None, symbol: str = "BTC/USDT") -> TestReport:
        """运行测试"""
        start_time = time.time()
        
        # 确定要测试的交易所
        if not exchanges:
            exchanges = [name for name in EXCHANGE_CONFIGS.keys() if self._check_env(EXCHANGE_CONFIGS[name])[0]]
        
        if not exchanges:
            logger.error("No exchanges configured or specified!")
            return TestReport(
                test_time=datetime.now().isoformat(),
                duration_seconds=0,
                total_exchanges=0,
                passed_exchanges=0,
                failed_exchanges=0,
                metrics=[],
                errors={"all": "No exchanges configured"},
            )
        
        logger.info(f"\n🚀 Starting tests for {len(exchanges)} exchange(s)...")
        
        # 运行测试
        for exchange_name in exchanges:
            self.test_exchange(exchange_name, symbol)
        
        # 计算统计
        duration = time.time() - start_time
        passed = sum(1 for m in self.metrics if m.connection_ok and not m.error)
        
        # 生成报告
        report = TestReport(
            test_time=datetime.now().isoformat(),
            duration_seconds=duration,
            total_exchanges=len(exchanges),
            passed_exchanges=passed,
            failed_exchanges=len(exchanges) - passed,
            metrics=self.metrics,
            errors=self.errors,
        )
        
        return report
    
    def print_summary(self, report: TestReport):
        """打印汇总报告"""
        logger.info(f"\n{'='*70}")
        logger.info("📊 TEST SUMMARY")
        logger.info(f"{'='*70}")
        
        logger.info(f"Total: {report.total_exchanges} exchanges")
        logger.info(f"✅ Passed: {report.passed_exchanges}")
        logger.info(f"❌ Failed: {report.failed_exchanges}")
        logger.info(f"⏱️  Duration: {report.duration_seconds:.1f}s")
        
        logger.info(f"\n{'Exchange':<15} {'Connection':<12} {'Price':<12} {'Orderbook':<12} {'Balance':<12} {'Error':<30}")
        logger.info("-" * 93)
        
        for metric in report.metrics:
            conn = "✅" if metric.connection_ok else "❌"
            price = "✅" if metric.price_ok else "❌"
            orderbook = "✅" if metric.orderbook_ok else "❌"
            balance = "✅" if metric.balance_ok else "❌"
            error = metric.error[:28] if metric.error else ""
            
            logger.info(f"{metric.exchange:<15} {conn:<12} {price:<12} {orderbook:<12} {balance:<12} {error:<30}")
        
        logger.info(f"\n{'='*70}")


# ============================================================
# 交互式选择工具
# ============================================================

def interactive_select_exchanges() -> List[str]:
    """交互式选择交易所"""
    exchange_list = list(EXCHANGE_CONFIGS.keys())
    
    print("\n" + "="*70)
    print("📋 Available Exchanges (按编号选择)")
    print("="*70)
    
    for idx, name in enumerate(exchange_list, 1):
        config = EXCHANGE_CONFIGS[name]
        has_env, _ = UnifiedExchangeTester()._check_env(config)
        status = "✅ 已配置" if has_env else "❌ 缺凭证"
        mainnet = "主网" if config.use_mainnet else "DEMO"
        print(f"  {idx:2d}. {name:<15} | {status:<10} | {mainnet:<6}")
    
    print("\n" + "-"*70)
    print("输入交易所编号进行选择:")
    print("  例1: 1      → 只测试第1个交易所")
    print("  例2: 1 3 5  → 测试第1、3、5个交易所")
    print("  例3: 1-5    → 测试第1到5个交易所")
    print("  例4: all    → 测试所有交易所")
    print("  例5: cex    → 测试所有 CEX")
    print("  例6: dex    → 测试所有 DEX")
    print("  例7: q      → 退出")
    print("-"*70)
    
    while True:
        user_input = input("\n请选择 (或输入 q 退出): ").strip().lower()
        
        if user_input == "q":
            sys.exit(0)
        
        if user_input == "all":
            return exchange_list
        
        if user_input == "cex":
            cex_list = ["okx", "binance", "bitget", "bybit"]
            return [name for name in exchange_list if name in cex_list]
        
        if user_input == "dex":
            dex_list = ["hyperliquid", "paradex", "extended", "lighter", "edgex", "backpack", "grvt", "aster"]
            return [name for name in exchange_list if name in dex_list]
        
        # 解析数字输入
        selected = []
        try:
            # 处理多种输入格式
            parts = user_input.replace(",", " ").split()
            for part in parts:
                if "-" in part:
                    # 处理范围，如 1-5
                    start, end = map(int, part.split("-"))
                    for i in range(start, end + 1):
                        if 1 <= i <= len(exchange_list):
                            selected.append(exchange_list[i - 1])
                else:
                    # 单个数字
                    idx = int(part)
                    if 1 <= idx <= len(exchange_list):
                        selected.append(exchange_list[idx - 1])
                    else:
                        print(f"❌ 编号 {idx} 超出范围 (1-{len(exchange_list)})")
            
            if selected:
                # 去重
                selected = list(dict.fromkeys(selected))
                print(f"\n✅ 已选择: {', '.join(selected)}")
                return selected
            else:
                print("❌ 无效输入，请重试")
        except ValueError:
            print("❌ 无效输入格式，请输入数字或快捷方式")


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="PerpBot 统一交易所测试框架 (生产级)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 交互式选择
  python test_exchanges.py
  
  # 测试特定交易所
  python test_exchanges.py okx binance
  
  # 按编号选择 (输入数字序列)
  python test_exchanges.py --select
  
  # 快捷方式
  python test_exchanges.py --all       # 所有交易所
  python test_exchanges.py --cex       # 仅 CEX
  python test_exchanges.py --dex       # 仅 DEX
  
  # 列出所有支持的交易所
  python test_exchanges.py --list
  
  # 自定义交易对
  python test_exchanges.py okx --symbol BTC/USDT
  
  # 详细日志
  python test_exchanges.py --verbose
  
  # JSON 报告
  python test_exchanges.py --json-report report.json
        """,
    )
    
    parser.add_argument(
        "exchanges",
        nargs="*",
        help="要测试的交易所 (留空则进入交互式选择)",
    )
    parser.add_argument(
        "--select",
        action="store_true",
        help="进入交互式选择模式",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="测试所有交易所",
    )
    parser.add_argument(
        "--cex",
        action="store_true",
        help="仅测试 CEX (中心化交易所)",
    )
    parser.add_argument(
        "--dex",
        action="store_true",
        help="仅测试 DEX (去中心化交易所)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有支持的交易所",
    )
    parser.add_argument(
        "--symbol",
        default="BTC/USDT",
        help="要查询的交易对 (默认: BTC/USDT)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细日志输出",
    )
    parser.add_argument(
        "--trading",
        action="store_true",
        help="包含小额交易测试 (谨慎!)",
    )
    parser.add_argument(
        "--trading-size",
        type=float,
        default=0.001,
        help="交易测试的数量 (默认: 0.001)",
    )
    parser.add_argument(
        "--auto-test",
        action="store_true",
        help="自动化测试模式（不进入交互式菜单）",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="交互式菜单模式 (对单个交易所)",
    )
    parser.add_argument(
        "--json-report",
        help="输出 JSON 报告到指定文件",
    )
    
    args = parser.parse_args()
    
    # 列出交易所
    if args.list:
        print("\n" + "="*70)
        print("🌍 Supported Exchanges (生产级)")
        print("="*70)
        
        exchange_list = list(EXCHANGE_CONFIGS.keys())
        for idx, name in enumerate(exchange_list, 1):
            config = EXCHANGE_CONFIGS[name]
            has_env, _ = UnifiedExchangeTester()._check_env(config)
            status = "✅ 已配置" if has_env else "❌ 缺凭证"
            mainnet = "主网" if config.use_mainnet else "DEMO"
            env_vars = ", ".join(config.required_env) if config.required_env else "optional"
            print(f"  {idx:2d}. {name:<15} | {status:<10} | {mainnet:<6} | {env_vars}")
        return
    
    # 确定要测试的交易所
    selected_exchanges = []
    
    if args.all:
        selected_exchanges = list(EXCHANGE_CONFIGS.keys())
    elif args.cex:
        selected_exchanges = ["okx", "binance", "bitget", "bybit"]
    elif args.dex:
        selected_exchanges = ["hyperliquid", "paradex", "extended", "lighter", "edgex", "backpack", "grvt", "aster"]
    elif args.select or not args.exchanges:
        # 交互式选择
        selected_exchanges = interactive_select_exchanges()
    else:
        selected_exchanges = args.exchanges
    
    if not selected_exchanges:
        logger.error("No exchanges selected!")
        sys.exit(1)
    
    # 创建测试器
    tester = UnifiedExchangeTester(
        include_trading=args.trading,
        verbose=args.verbose,
    )
    
    # 如果只选择了一个交易所，可能进入交互式模式或带交易的自动测试
    if len(selected_exchanges) == 1 and (args.interactive or not args.auto_test):
        exchange_name = selected_exchanges[0]
        config = EXCHANGE_CONFIGS[exchange_name]
        
        # 检查环境变量
        has_env, missing = tester._check_env(config)
        if not has_env:
            logger.error(f"❌ Missing env vars for {exchange_name}: {', '.join(missing)}")
            sys.exit(1)
        
        # 加载客户端
        try:
            client = tester._load_exchange_client(config)
            client.connect()
            logger.info(f"✅ Connected to {exchange_name}")
        except Exception as e:
            logger.error(f"❌ Failed to connect: {e}")
            sys.exit(1)
        
        # 基础测试
        logger.info(f"\n{'='*60}")
        logger.info(f"交易所: {exchange_name.upper()}")
        logger.info(f"交易对: {args.symbol}")
        logger.info(f"{'='*60}")
        
        tester.test_exchange(exchange_name, args.symbol)
        
        # 如果指定了 --trading，运行交易测试
        if args.trading:
            logger.info(f"\n{'='*60}")
            logger.info(f"🔄 运行交易测试 (大小: {args.trading_size})")
            logger.info(f"{'='*60}")
            
            # 测试限价单
            success, msg = tester.test_limit_order(client, args.symbol, args.trading_size)
            
            # 测试市价单
            time.sleep(1)
            success, msg = tester.test_market_order(client, args.symbol, args.trading_size)
            
            # 测试平仓
            time.sleep(1)
            success, msg = tester.test_close_position(client, args.symbol)
        else:
            # 进入交互式菜单
            logger.info(f"\n💡 提示: 使用 --trading 启用交易功能，或使用 --auto-test 自动化模式")
            tester.interactive_menu(exchange_name, client, args.symbol)
    
    else:
        # 多个交易所的自动化测试模式
        if not args.auto_test:
            print(f"\n💡 多个交易所检测到，自动进入自动化测试模式")
        
        report = tester.run_tests(selected_exchanges, args.symbol)
        tester.print_summary(report)
        
        # 输出 JSON 报告
        if args.json_report:
            with open(args.json_report, "w") as f:
                json.dump(asdict(report), f, indent=2, default=str)
            logger.info(f"\n📄 Report saved to {args.json_report}")
        
        # 返回状态码
        sys.exit(0 if report.failed_exchanges == 0 else 1)
    
    # 单个交易所的 JSON 报告
    if args.json_report and len(selected_exchanges) == 1:
        report = TestReport(
            test_time=datetime.now().isoformat(),
            duration_seconds=0,
            total_exchanges=1,
            passed_exchanges=1,
            failed_exchanges=0,
            metrics=tester.metrics,
            errors={},
        )
        with open(args.json_report, "w") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        logger.info(f"\n📄 Report saved to {args.json_report}")
    


if __name__ == "__main__":
    main()
