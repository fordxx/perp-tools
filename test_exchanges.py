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
import random
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from importlib import import_module
from pathlib import Path
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

_ACCOUNT_OPTIONAL_EXCHANGES = {"binance"}

def configure_noisy_loggers(verbose: bool) -> None:
    """Reduce wire-level noise unless explicitly requested.

    Set `PERPBOT_VERBOSE_WIRE_LOGS=1` to keep websockets/httpcore debug logs.
    """
    wire_verbose = os.getenv("PERPBOT_VERBOSE_WIRE_LOGS", "0").strip().lower() in {"1", "true", "yes", "y"}
    # `--verbose` should not automatically enable wire-level logs (can leak auth headers and drown signal).
    if wire_verbose:
        return

    for name in [
        "websockets",
        "websockets.client",
        "websockets.server",
        "httpcore",
        "httpx",
        "urllib3",
        "aiohttp",
        "asyncio",
    ]:
        logging.getLogger(name).setLevel(logging.WARNING)

def log_diag_env() -> None:
    keys = [
        "PERPBOT_HTTP_RETRY_ATTEMPTS",
        "PERPBOT_HTTP_RETRY_STATUS_CODES",
        "PERPBOT_WS_STALE_SEC",
        "PERPBOT_WS_RECONNECT_BACKOFF_MAX_SEC",
        "PERPBOT_VERBOSE_WIRE_LOGS",
    ]
    parts = []
    for k in keys:
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            parts.append(f"{k}={v}")
    if parts:
        logger.info("[diag-env] %s", " ".join(parts))


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
    default_symbol: str = "ETH/USDT"  # 默认交易对


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
        required_env=[],  # Bybit 支持公共行情接口（无凭证也可跑只读测试）
        optional_env=["BYBIT_API_KEY", "BYBIT_API_SECRET", "BYBIT_ENV", "BYBIT_UID"],
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
        default_symbol="BTC",  # Hyperliquid 使用 BTC 而不是 BTC/USDT
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
        default_symbol="BTC/USD",  # Extended 市场通常为 BTC-USD / ETH-USD
    ),
    "lighter": ExchangeConfig(
        name="lighter",
        class_name="LighterClient",
        module_name="perpbot.exchanges.lighter",
        required_env=[],  # 支持只读模式（无需凭证）
        optional_env=[
            "LIGHTER_API_KEY_PRIVATE_KEY",  # 推荐：API Key 私钥（0x 前缀）
            "LIGHTER_PRIVATE_KEY",  # 兼容旧命名
            "LIGHTER_ACCOUNT_INDEX",
            "LIGHTER_API_KEY_INDEX",
            "LIGHTER_ENV",
            "LIGHTER_API_BASE_URL",
        ],
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
        required_env=["GRVT_API_KEY", "GRVT_PRIVATE_KEY", "GRVT_TRADING_ACCOUNT_ID"],
        use_mainnet=True,
    ),
    "aster": ExchangeConfig(
        name="aster",
        class_name="AsterClient",
        module_name="perpbot.exchanges.aster",
        required_env=["ASTER_API_KEY", "ASTER_API_SECRET"],
        use_mainnet=True,
    ),
}


# ============================================================
# 核心测试器
# ============================================================

class UnifiedExchangeTester:
    """统一交易所测试器"""
    
    def __init__(self, include_trading: bool = False, verbose: bool = False, skip_account: bool = False):
        self.include_trading = include_trading
        self.verbose = verbose
        self.skip_account = skip_account
        load_dotenv()
        
        if verbose:
            logging.getLogger().setLevel(logging.DEBUG)
        configure_noisy_loggers(verbose=verbose)
        log_diag_env()
        
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

    def _record_step_error(self, exchange_name: str, metrics: TestMetrics, label: str, error: str):
        """记录当前步骤的错误信息"""
        if not error:
            return
        entry = f"{label}: {error}"
        if metrics.error:
            metrics.error = f"{metrics.error}; {entry}"
        else:
            metrics.error = entry
        self.errors[exchange_name] = metrics.error

    def _is_optional_account_error(self, exchange_name: str, error: Optional[str]) -> bool:
        if not error:
            return False
        if exchange_name not in _ACCOUNT_OPTIONAL_EXCHANGES:
            return False
        msg = error.lower()
        return "reference-only" in msg or "trading is disabled" in msg

    def _validate_quote(self, exchange_name: str, symbol: str, metrics: TestMetrics, quote: Any) -> bool:
        bid_ok = bool(quote) and getattr(quote, "bid", 0) and float(quote.bid) > 0
        ask_ok = bool(quote) and getattr(quote, "ask", 0) and float(quote.ask) > 0
        if not (bid_ok and ask_ok):
            metrics.price_ok = False
            self._record_step_error(
                exchange_name,
                metrics,
                "Invalid price",
                f"bid/ask is 0 (symbol={symbol}); check symbol mapping or exchange connectivity",
            )
            logger.warning(
                "   ⚠️ Price invalid (bid=%s, ask=%s)",
                getattr(quote, "bid", None),
                getattr(quote, "ask", None),
            )
            return False
        return True

    def _validate_orderbook(self, exchange_name: str, symbol: str, metrics: TestMetrics, orderbook: Any) -> bool:
        metrics.orderbook_bids = len(orderbook.bids) if orderbook else 0
        metrics.orderbook_asks = len(orderbook.asks) if orderbook else 0
        if metrics.orderbook_bids <= 0 or metrics.orderbook_asks <= 0:
            metrics.orderbook_ok = False
            self._record_step_error(
                exchange_name,
                metrics,
                "Invalid orderbook",
                f"empty bids/asks (symbol={symbol}); check symbol mapping or exchange connectivity",
            )
            logger.warning(
                "   ⚠️ Orderbook invalid: %s bids, %s asks",
                metrics.orderbook_bids,
                metrics.orderbook_asks,
            )
            return False
        return True

    def test_exchange(self, exchange_name: str, symbol: Optional[str] = None) -> Optional[TestMetrics]:
        """测试单个交易所"""
        if exchange_name not in EXCHANGE_CONFIGS:
            logger.error(f"Unknown exchange: {exchange_name}")
            return None
        
        config = EXCHANGE_CONFIGS[exchange_name]

        # 使用配置的默认交易对（如果没有指定）
        if symbol is None:
            try:
                from perpbot.exchanges.runtime_config import load_exchange_runtime_config

                runtime_cfg = load_exchange_runtime_config(exchange_name)
            except Exception:
                runtime_cfg = None

            symbol = (
                (runtime_cfg.default_symbol if runtime_cfg and runtime_cfg.default_symbol else None)
                or config.default_symbol
            )

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
            self._record_step_error(exchange_name, metrics, "Price fetch failed", error)
            logger.warning(f"   ⚠️ Price fetch failed: {error}")
        else:
            metrics.price_value = quote.mid if quote else None
            if self._validate_quote(exchange_name, symbol, metrics, quote):
                logger.info(f"   ✅ Price: {quote.bid:.2f}-{quote.ask:.2f} ({duration:.0f}ms)")
        
        # 测试 3: 订单簿
        logger.info(f"3️⃣ Testing orderbook ({symbol})...")
        def _get_orderbook():
            return client.get_orderbook(symbol, depth=5)
        orderbook, duration, error = self._time_operation(_get_orderbook)
        metrics.orderbook_ok = error is None
        metrics.orderbook_time_ms = duration
        if error:
            self._record_step_error(exchange_name, metrics, "Orderbook fetch failed", error)
            logger.warning(f"   ⚠️ Orderbook fetch failed: {error}")
        else:
            if self._validate_orderbook(exchange_name, symbol, metrics, orderbook):
                logger.info(f"   ✅ Orderbook: {metrics.orderbook_bids} bids, {metrics.orderbook_asks} asks ({duration:.0f}ms)")
        
        # 测试 4: 账户余额
        if self.skip_account:
            logger.info("4️⃣ Testing account balances... (skipped)")
            metrics.balance_ok = True
        else:
            logger.info("4️⃣ Testing account balances...")
            def _get_balances():
                return client.get_account_balances()
            balances, duration, error = self._time_operation(_get_balances)
            if error and self._is_optional_account_error(exchange_name, error):
                metrics.balance_ok = True
                metrics.balance_time_ms = duration
                logger.info("   ⏭️ Balances skipped (%s)", error)
            else:
                metrics.balance_ok = error is None
                metrics.balance_time_ms = duration
            if error and not self._is_optional_account_error(exchange_name, error):
                self._record_step_error(exchange_name, metrics, "Balance fetch failed", error)
                logger.warning(f"   ⚠️ Balance fetch failed: {error}")
            else:
                metrics.balance_count = len(balances) if balances else 0
                logger.info(f"   ✅ Found {metrics.balance_count} balances ({duration:.0f}ms)")
                if balances and len(balances) > 0:
                    for balance in balances[:3]:
                        logger.info(f"      - {balance.asset}: {balance.free} free")
        
        # 测试 5: 持仓
        if self.skip_account:
            logger.info("5️⃣ Testing positions... (skipped)")
            metrics.positions_ok = True
        else:
            logger.info("5️⃣ Testing positions...")
            def _get_positions():
                return client.get_account_positions()
            positions, duration, error = self._time_operation(_get_positions)
            if error and self._is_optional_account_error(exchange_name, error):
                metrics.positions_ok = True
                metrics.positions_time_ms = duration
                logger.info("   ⏭️ Positions skipped (%s)", error)
            else:
                metrics.positions_ok = error is None
                metrics.positions_time_ms = duration
            if error and not self._is_optional_account_error(exchange_name, error):
                self._record_step_error(exchange_name, metrics, "Positions fetch failed", error)
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
        # 预设的下单大小和价格偏差
        SIZE_OPTIONS = [0.0001, 0.0005, 0.001, 0.005, 0.01]
        OFFSET_OPTIONS = [0.005, 0.01, 0.02, 0.05, 0.1]
        
        while True:
            print(f"\n{'='*60}")
            print(f"🔄 {exchange_name.upper()} - 交互式菜单")
            print(f"{'='*60}")
            print(f"交易对: {symbol}")
            print()
            print("📊 查询功能:")
            print("  1️⃣  查询价格")
            print("  2️⃣  查询订单簿")
            print("  3️⃣  查询账户余额")
            print("  4️⃣  查询持仓")
            print()
            print("💰 交易功能:")
            print("  5️⃣  下限价单 (买)")
            print("  6️⃣  下市价单 (买)")
            print("  7️⃣  平仓")
            print()
            print("⚙️  其他:")
            print("  8️⃣  切换交易对")
            print("  0️⃣  返回")
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
                        print(f"      {ask[0]:.2f} x {ask[1]}")
                    print(f"   买盘 (Bids):")
                    for bid in (ob.bids[:3] if ob.bids else []):
                        print(f"      {bid[0]:.2f} x {bid[1]}")
                except Exception as e:
                    print(f"❌ 获取订单簿失败: {e}")
            
            elif choice == "3":
                try:
                    balances = client.get_account_balances()
                    print(f"\n💰 账户余额 ({len(balances)} 种资产)")
                    for b in balances[:5]:
                        print(f"   {b.asset}: 可用={b.free}, 锁定={b.locked}")
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
                # 下限价单 - 用数字选择
                self._order_with_selection(client, symbol, SIZE_OPTIONS, OFFSET_OPTIONS, "limit")
            
            elif choice == "6":
                # 下市价单 - 用数字选择
                self._order_with_selection(client, symbol, SIZE_OPTIONS, None, "market")
            
            elif choice == "7":
                # 平仓
                try:
                    success, msg = self.test_close_position(client, symbol)
                    if success:
                        print(f"✅ {msg}")
                    else:
                        print(f"ℹ️  {msg}")
                except Exception as e:
                    print(f"❌ 平仓失败: {e}")
            
            elif choice == "8":
                symbol = input("请输入新交易对 (e.g., BTC/USDT): ").strip()
                if symbol:
                    print(f"✅ 已切换到 {symbol}")
            
            else:
                print("❌ 无效选择")
    
    def _order_with_selection(self, client: Any, symbol: str, size_options: List[float], offset_options: Optional[List[float]], order_type: str) -> None:
        """通过数字选择来下单"""
        try:
            # 第 1 步: 选择下单数量
            print(f"\n{'='*50}")
            print(f"📊 选择下单数量")
            print(f"{'='*50}")
            for i, size in enumerate(size_options, 1):
                print(f"  {i}️⃣  {size}")
            print(f"  0️⃣  自定义")
            
            size_choice = input("请选择 (0-5): ").strip()
            
            if size_choice == "0":
                size = float(input("请输入自定义数量: ").strip())
            elif size_choice in [str(i) for i in range(1, len(size_options) + 1)]:
                size = size_options[int(size_choice) - 1]
            else:
                print("❌ 无效选择")
                return
            
            # 第 2 步: 如果是限价单，选择价格偏差
            if order_type == "limit" and offset_options:
                print(f"\n{'='*50}")
                print(f"📊 选择限价偏差（距离当前价格的百分比）")
                print(f"{'='*50}")
                for i, offset in enumerate(offset_options, 1):
                    print(f"  {i}️⃣  {offset*100:.1f}%")
                print(f"  0️⃣  自定义")
                
                offset_choice = input("请选择 (0-5): ").strip()
                
                if offset_choice == "0":
                    offset = float(input("请输入自定义偏差 (例如 0.02 表示 2%): ").strip())
                elif offset_choice in [str(i) for i in range(1, len(offset_options) + 1)]:
                    offset = offset_options[int(offset_choice) - 1]
                else:
                    print("❌ 无效选择")
                    return
                
                success, msg = self.test_limit_order(client, symbol, size, offset)
            else:
                success, msg = self.test_market_order(client, symbol, size)
            
            if success:
                print(f"\n✅ {msg}")
            else:
                print(f"\n❌ {msg}")
        
        except ValueError:
            print("❌ 输入格式错误")
        except Exception as e:
            print(f"❌ 下单失败: {e}")
    
    def run_tests(self, exchanges: Optional[List[str]] = None, symbol: Optional[str] = None) -> TestReport:
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

    def soak_exchange(
        self,
        exchange_name: str,
        duration_sec: float,
        symbols: List[str],
        interval_sec: float,
        jitter_sec: float,
        account_every: int,
        max_fail_rate: float,
    ) -> int:
        """长时间 Soak 测试，用于暴露间歇性失败/断连/限频/符号映射问题。

        - 单进程长连接：connect 一次，循环多次请求
        - 每轮输出一条 `[soak]` 行，方便 grep/统计
        - 失败率超过阈值直接退出（暴露问题优先）
        """
        if exchange_name not in EXCHANGE_CONFIGS:
            logger.error("Unknown exchange: %s", exchange_name)
            return 2

        config = EXCHANGE_CONFIGS[exchange_name]
        has_env, missing = self._check_env(config)
        if not has_env:
            logger.error("❌ Missing env vars for %s: %s", exchange_name, ", ".join(missing))
            return 2

        client = self._load_exchange_client(config)
        client.connect()

        start = time.time()
        end = start + duration_sec if duration_sec > 0 else float("inf")
        symbols = [s for s in symbols if s]
        if not symbols:
            symbols = [config.default_symbol]

        total = 0
        failures = 0

        logger.info(
            "[soak] exchange=%s duration=%ss interval=%ss jitter=%ss symbols=%s account_every=%s max_fail_rate=%s",
            exchange_name,
            duration_sec,
            interval_sec,
            jitter_sec,
            symbols,
            account_every,
            max_fail_rate,
        )

        if self.skip_account:
            account_every = 0

        i = 0
        while time.time() < end:
            i += 1
            symbol = symbols[(i - 1) % len(symbols)]

            metrics = TestMetrics(
                exchange=exchange_name,
                timestamp=datetime.now().isoformat(),
                connection_ok=True,
                connection_time_ms=0,
                price_ok=False,
                orderbook_ok=False,
                balance_ok=False,
                positions_ok=False,
            )

            quote, dt_price, err_price = self._time_operation(lambda: client.get_current_price(symbol))
            metrics.price_time_ms = dt_price
            metrics.price_ok = err_price is None and self._validate_quote(exchange_name, symbol, metrics, quote)

            ob, dt_ob, err_ob = self._time_operation(lambda: client.get_orderbook(symbol, depth=5))
            metrics.orderbook_time_ms = dt_ob
            metrics.orderbook_ok = err_ob is None and self._validate_orderbook(exchange_name, symbol, metrics, ob)

            if account_every > 0 and (i % account_every == 0):
                _, dt_bal, err_bal = self._time_operation(lambda: client.get_account_balances())
                metrics.balance_time_ms = dt_bal
                metrics.balance_ok = err_bal is None or self._is_optional_account_error(exchange_name, err_bal)

                _, dt_pos, err_pos = self._time_operation(lambda: client.get_account_positions())
                metrics.positions_time_ms = dt_pos
                metrics.positions_ok = err_pos is None or self._is_optional_account_error(exchange_name, err_pos)
            else:
                metrics.balance_ok = True
                metrics.positions_ok = True

            ok = metrics.price_ok and metrics.orderbook_ok and metrics.balance_ok and metrics.positions_ok
            total += 1
            if not ok:
                failures += 1

            fail_rate = failures / max(total, 1)
            logger.info(
                "[soak] i=%d symbol=%s ok=%s fail_rate=%.4f price_ms=%.0f ob_ms=%.0f err=%s",
                i,
                symbol,
                "1" if ok else "0",
                fail_rate,
                metrics.price_time_ms,
                metrics.orderbook_time_ms,
                metrics.error or "",
            )

            if max_fail_rate >= 0 and fail_rate > max_fail_rate:
                logger.error("[soak] abort: fail_rate %.4f > max_fail_rate %.4f", fail_rate, max_fail_rate)
                return 1

            sleep_for = max(interval_sec, 0.0)
            if jitter_sec > 0:
                sleep_for += random.uniform(0, jitter_sec)
            time.sleep(sleep_for)

        logger.info("[soak] done: total=%d failures=%d fail_rate=%.4f", total, failures, failures / max(total, 1))
        return 0 if failures == 0 else 1
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
        default=None,
        help="要查询的交易对 (默认: 根据交易所自动选择)",
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
    parser.add_argument(
        "--soak",
        type=float,
        default=0.0,
        help="Soak 测试持续秒数（>0 启用；仅支持单交易所单进程长跑）",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Soak 模式每轮间隔秒数（默认 5）",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.5,
        help="Soak 模式随机抖动秒数（每轮额外 sleep 0..jitter）",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Soak 模式轮换的交易对列表（逗号分隔），如 BTC/USDT,ETH/USDT",
    )
    parser.add_argument(
        "--account-every",
        type=int,
        default=12,
        help="Soak 模式每 N 轮做一次余额/持仓查询（默认 12；0 表示关闭）",
    )
    parser.add_argument(
        "--max-fail-rate",
        type=float,
        default=0.0,
        help="Soak 模式失败率阈值，超过就退出（默认 0 = 任意失败都退出）",
    )
    parser.add_argument(
        "--skip-account",
        action="store_true",
        help="跳过余额/持仓查询（仅测连接+行情；适合 reference-only 或凭证不完整时）",
    )
    
    args = parser.parse_args()
    
    # 列出交易所
    if args.list:
        print("\n" + "="*70)
        print("🌍 Supported Exchanges (生产级)")
        print("="*70)

        tester_for_list = UnifiedExchangeTester()
        exchange_list = list(EXCHANGE_CONFIGS.keys())
        for idx, name in enumerate(exchange_list, 1):
            config = EXCHANGE_CONFIGS[name]
            has_env, _ = tester_for_list._check_env(config)
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

    # 如果只选了一个交易所，且还未由 wrapper 调用，交给 run_exchange_test.sh 自动激活虚拟环境
    wrapper_script = Path(__file__).resolve().parent / "run_exchange_test.sh"
    if (
        len(selected_exchanges) == 1
        and os.environ.get("USE_VENV_WRAPPER") != "1"
        and wrapper_script.exists()
    ):
        script_args = sys.argv[1:]
        env = os.environ.copy()
        env["USE_VENV_WRAPPER"] = "1"
        logger.info("Detected single-exchange run, delegating to %s for venv handling", wrapper_script)
        return_code = subprocess.call([str(wrapper_script)] + script_args, env=env)
        sys.exit(return_code)
    
    # 创建测试器
    tester = UnifiedExchangeTester(
        include_trading=args.trading,
        verbose=args.verbose,
        skip_account=args.skip_account,
    )

    # Soak 模式：单交易所长跑，专门用来暴露间歇性问题
    if args.soak and args.soak > 0:
        if len(selected_exchanges) != 1:
            logger.error("--soak only supports a single exchange per run")
            sys.exit(2)

        exchange_name = selected_exchanges[0]
        config = EXCHANGE_CONFIGS[exchange_name]

        from perpbot.exchanges.runtime_config import load_exchange_runtime_config

        runtime_cfg = load_exchange_runtime_config(exchange_name)
        cfg_symbols: List[str] = []
        if runtime_cfg and runtime_cfg.symbols:
            cfg_symbols = list(runtime_cfg.symbols)

        if args.symbols.strip():
            cfg_symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]

        # `--symbol` 优先，放在轮换列表开头（更快暴露符号映射问题）
        preferred_symbol = args.symbol if args.symbol is not None else (runtime_cfg.default_symbol if runtime_cfg and runtime_cfg.default_symbol else None)
        if preferred_symbol:
            cfg_symbols = [preferred_symbol] + [s for s in cfg_symbols if s != preferred_symbol]

        rc = tester.soak_exchange(
            exchange_name=exchange_name,
            duration_sec=float(args.soak),
            symbols=cfg_symbols or [config.default_symbol],
            interval_sec=float(args.interval),
            jitter_sec=float(args.jitter),
            account_every=int(args.account_every),
            max_fail_rate=float(args.max_fail_rate),
        )
        sys.exit(rc)
    
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
        
        # 使用配置的默认交易对（如果没有指定）
        symbol = args.symbol if args.symbol is not None else config.default_symbol

        # 基础测试
        logger.info(f"\n{'='*60}")
        logger.info(f"交易所: {exchange_name.upper()}")
        logger.info(f"交易对: {symbol}")
        logger.info(f"{'='*60}")

        tester.test_exchange(exchange_name, symbol)

        # 如果指定了 --trading，运行交易测试
        if args.trading:
            logger.info(f"\n{'='*60}")
            logger.info(f"🔄 运行交易测试 (大小: {args.trading_size})")
            logger.info(f"{'='*60}")

            # 测试限价单
            success, msg = tester.test_limit_order(client, symbol, args.trading_size)

            # 测试市价单
            time.sleep(1)
            success, msg = tester.test_market_order(client, symbol, args.trading_size)

            # 测试平仓
            time.sleep(1)
            success, msg = tester.test_close_position(client, symbol)
        else:
            # 进入交互式菜单
            logger.info(f"\n💡 提示: 使用 --trading 启用交易功能，或使用 --auto-test 自动化模式")
            tester.interactive_menu(exchange_name, client, symbol)
    
    else:
        # 多个交易所的自动化测试模式
        if not args.auto_test:
            print(f"\n💡 多个交易所检测到，自动进入自动化测试模式")

        # 使用默认交易对（如果没有指定）
        # 注意：多交易所测试时，每个交易所会使用自己的默认交易对
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
