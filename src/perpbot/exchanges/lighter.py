"""Lighter DEX client.

说明（重要）：
- 本项目采用 `elliottech/lighter-python`（`lighter-sdk`）作为 SDK，直接对接
  `https://mainnet.zklighter.elliot.ai` / `https://testnet.zklighter.elliot.ai`。
- 早期使用过 `lighter-v1-python`（会强依赖 web3 RPC，例如 `rpc.lighter.xyz`），该域名在部分环境
  无法解析，会导致连接失败；现已切换为 `lighter-sdk`，不再依赖链上 RPC。

环境变量（兼容两套命名）：
- 只读模式（无需凭证）：可直接获取价格/盘口（基于公开 API）
- 交易/账户模式（建议使用）：
  - LIGHTER_API_KEY_PRIVATE_KEY: Lighter 前端生成的 API Key 私钥（0x 前缀）
  - LIGHTER_ACCOUNT_INDEX: 账户 index（十进制）
  - LIGHTER_API_KEY_INDEX: API Key index（十进制）

可选：
- LIGHTER_ENV: mainnet/testnet（默认 mainnet）
- LIGHTER_API_BASE_URL: 自定义 REST host（默认随 env）
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class LighterClient(ExchangeClient):
    """Lighter DEX client using official SDK.
    
    Features:
    - Ethereum L2 with zk-rollup technology
    - Zero-fee perpetuals trading
    - Verifiable order matching
    - Non-custodial (funds stay in wallet until execution)
    """

    # API endpoints
    MAINNET_API = "https://mainnet.zklighter.elliot.ai"
    TESTNET_API = "https://testnet.zklighter.elliot.ai"
    MAINNET_WS = "wss://mainnet.zklighter.elliot.ai/stream"
    TESTNET_WS = "wss://testnet.zklighter.elliot.ai/stream"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "lighter"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key_private_key: Optional[str] = None
        self.account_index: Optional[int] = None
        self.api_key_index: Optional[int] = None

        self.base_url: str = ""
        self.ws_url: str = ""

        self._connected = False
        self._trading_enabled = False  # 仅表示“已配置 SignerClient 能查账户/交易”，不代表一定允许真实下单

        self._api_client = None
        self._order_api = None
        self._account_api = None
        self._signer_client = None

        # symbol -> market_id
        self._markets: Dict[str, int] = {}

        # Reduce 429 rate-limit errors by caching orderbook snapshots briefly.
        self._orderbook_cache_lock = threading.Lock()
        # market_id -> (monotonic_ts, cached_depth, bids, asks)
        self._orderbook_cache: Dict[int, Tuple[float, int, List[Tuple[float, float]], List[Tuple[float, float]]]] = {}
        self._orderbook_cache_ttl_ms: int = 250

        # lighter-sdk 是异步 client（aiohttp），需要常驻 event loop；这里用后台线程托管
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """连接 Lighter（公开行情 + 可选账户能力）。"""
        load_dotenv()

        env = os.getenv("LIGHTER_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")

        try:
            self._orderbook_cache_ttl_ms = int(os.getenv("LIGHTER_ORDERBOOK_CACHE_MS", "250"))
        except Exception:
            self._orderbook_cache_ttl_ms = 250
        
        default_api = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.base_url = os.getenv("LIGHTER_API_BASE_URL", default_api)
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        # 读取新的 Lighter 凭证（三件套）
        self.api_key_private_key = _first_non_none(
            os.getenv("LIGHTER_API_KEY_PRIVATE_KEY"),
            os.getenv("LIGHTER_PRIVATE_KEY"),
        )
        self.account_index = _first_non_none(
            _parse_int_env("LIGHTER_ACCOUNT_INDEX"),
            _parse_int_env("LIGHTER_ACCOUNT_INDEX_DEC"),
        )
        self.api_key_index = _parse_int_env("LIGHTER_API_KEY_INDEX")

        # 归一化 private key（很多人会漏写 0x 前缀）
        if self.api_key_private_key:
            key = str(self.api_key_private_key).strip()
            if key and not key.startswith("0x"):
                is_hex = all(c in "0123456789abcdefABCDEF" for c in key)
                if is_hex and len(key) % 2 == 0:
                    self.api_key_private_key = "0x" + key
                else:
                    logger.warning(
                        "⚠️ LIGHTER_API_KEY_PRIVATE_KEY/LIGHTER_PRIVATE_KEY 看起来不是纯十六进制或长度异常（未自动补 0x），SignerClient 可能校验失败"
                    )
            # 典型私钥应为 32 bytes：0x + 64 hex = 66 字符
            if isinstance(self.api_key_private_key, str) and self.api_key_private_key.startswith("0x"):
                if len(self.api_key_private_key) != 66:
                    logger.warning(
                        "⚠️ Lighter 私钥长度异常（期望 66 字符形如 0x + 64hex，实际=%s）。请确认你填的是 Lighter 前端生成的 API Key Private Key，而不是其它密钥。",
                        len(self.api_key_private_key),
                    )
                    # 禁止继续走 SignerClient，避免无意义请求/报错
                    self.api_key_private_key = None
        if self.account_index is not None and self.account_index <= 0:
            logger.warning("⚠️ LIGHTER_ACCOUNT_INDEX=%s 可能无效（通常应为正整数），SignerClient 可能校验失败", self.account_index)

        try:
            self._ensure_loop()
            self._run_coro(self._async_initialize(), timeout=30.0)
            self._connected = True
            logger.info(
                "✅ Lighter connected (testnet=%s, trading=%s, markets=%d)",
                self.use_testnet,
                self._trading_enabled,
                len(self._markets),
            )
        except Exception as e:
            self._connected = False
            self._trading_enabled = False
            logger.exception("❌ Lighter connection failed: %s", e)
            try:
                self.disconnect()
            except Exception:
                pass
            raise

    def disconnect(self) -> None:
        """尽量释放 aiohttp session/connector，避免 test_exchanges 退出时告警。"""
        try:
            if self._api_client and self._loop and self._loop.is_running():
                try:
                    self._run_coro(self._api_client.close(), timeout=5.0)
                except Exception:
                    pass
        finally:
            self._api_client = None
            self._order_api = None
            self._account_api = None
            self._signer_client = None
            self._connected = False
            self._trading_enabled = False

            if self._loop and self._loop.is_running():
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass

    def __del__(self) -> None:
        try:
            self.disconnect()
        except Exception:
            pass

    def _ensure_loop(self) -> None:
        if self._loop and self._loop.is_running():
            return

        loop = asyncio.new_event_loop()

        def runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=runner, name="lighter-event-loop", daemon=True)
        thread.start()

        self._loop = loop
        self._loop_thread = thread

    def _run_coro(self, coro, timeout: float = 15.0):
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("Lighter event loop not running")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    async def _async_initialize(self) -> None:
        from lighter import ApiClient, Configuration
        from lighter.api import AccountApi, OrderApi
        from lighter.signer_client import SignerClient

        self._api_client = ApiClient(configuration=Configuration(host=self.base_url))
        self._order_api = OrderApi(self._api_client)
        self._account_api = AccountApi(self._api_client)

        # 加载 markets（公开接口）
        resp = await self._order_api.order_books()
        order_books = getattr(resp, "order_books", None) or []
        self._markets = {getattr(ob, "symbol", ""): getattr(ob, "market_id", None) for ob in order_books}
        self._markets = {k: v for k, v in self._markets.items() if k and isinstance(v, int)}

        # 账户/交易能力：SignerClient（可选）
        self._trading_enabled = False
        self._signer_client = None
        private_key_ok = bool(self.api_key_private_key) and str(self.api_key_private_key).strip().startswith("0x")
        account_index_ok = self.account_index is not None and int(self.account_index) > 0
        api_key_index_ok = self.api_key_index is not None and int(self.api_key_index) >= 0
        signer_ready = private_key_ok and account_index_ok and api_key_index_ok
        if not signer_ready:
            logger.info(
                "ℹ️ Lighter 以只读模式运行（SignerClient 未配置完整）：private_key=%s account_index=%s api_key_index=%s",
                "SET" if self.api_key_private_key else "MISSING",
                str(self.account_index) if self.account_index is not None else "MISSING",
                str(self.api_key_index) if self.api_key_index is not None else "MISSING",
            )

        if signer_ready:
            try:
                # lighter-sdk 1.x: SignerClient(url, account_index, api_private_keys={api_key_index: private_key})
                self._signer_client = SignerClient(
                    url=self.base_url,
                    account_index=int(self.account_index),
                    api_private_keys={int(self.api_key_index): str(self.api_key_private_key)},
                )

                err = self._signer_client.check_client()
                if err is not None:
                    logger.warning("⚠️ Lighter SignerClient 检查失败（将以只读模式运行）: %s", err)
                    logger.warning("⚠️ 请重点检查：1) account_index 是否正确 2) api_key_index 是否正确（常见为 0/1/2）3) 是否选对 mainnet/testnet 4) private_key 是否匹配该 api_key_index")
                    try:
                        await self._signer_client.api_client.close()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    self._signer_client = None
                else:
                    self._trading_enabled = True
            except Exception as e:
                logger.warning("⚠️ Lighter SignerClient 初始化异常（将以只读模式运行）: %s", e)
                try:
                    await self._signer_client.api_client.close()  # type: ignore[attr-defined]
                except Exception:
                    pass
                self._signer_client = None
                self._trading_enabled = False

    def _to_lighter_symbol(self, symbol: str) -> str:
        """
        将统一符号（如 ETH/USDT、BTC/USDC）映射为 Lighter 市场符号。

        观察：Lighter mainnet 的 `order_books()` 返回 `symbol` 为基础币种（如 ETH/BTC/SOL），不带 quote。
        """
        if not symbol:
            return ""
        if "/" in symbol:
            return symbol.split("/", 1)[0].strip().upper()
        return symbol.strip().upper()

    def _normalize_symbol(self, symbol: str) -> str:
        # 历史兼容：旧实现使用 market symbol；现统一映射为 Lighter 的基础币种 symbol
        return self._to_lighter_symbol(symbol)

    def _get_market_id(self, symbol: str) -> Optional[int]:
        lighter_symbol = self._to_lighter_symbol(symbol)
        market_id = self._markets.get(lighter_symbol)
        if market_id is None:
            logger.warning("⚠️ Lighter market not found for symbol=%s (mapped=%s)", symbol, lighter_symbol)
        return market_id

    def _get_orderbook_cached(self, market_id: int, depth: int) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        if not self._order_api:
            raise RuntimeError("Lighter not connected")

        now = time.monotonic()
        ttl_sec = max(self._orderbook_cache_ttl_ms, 0) / 1000.0

        with self._orderbook_cache_lock:
            cached = self._orderbook_cache.get(market_id)
            if cached:
                ts, cached_depth, bids, asks = cached
                if ttl_sec > 0 and (now - ts) <= ttl_sec and cached_depth >= depth and bids and asks:
                    return bids[:depth], asks[:depth]

        resp = self._run_coro(self._order_api.order_book_orders(market_id=market_id, limit=depth), timeout=10.0)
        bids_raw = getattr(resp, "bids", None) or []
        asks_raw = getattr(resp, "asks", None) or []

        bids: List[Tuple[float, float]] = []
        asks: List[Tuple[float, float]] = []

        for b in bids_raw[:depth]:
            price = float(getattr(b, "price", 0) or 0)
            size = float(getattr(b, "remaining_base_amount", 0) or 0)
            if price > 0 and size > 0:
                bids.append((price, size))

        for a in asks_raw[:depth]:
            price = float(getattr(a, "price", 0) or 0)
            size = float(getattr(a, "remaining_base_amount", 0) or 0)
            if price > 0 and size > 0:
                asks.append((price, size))

        with self._orderbook_cache_lock:
            if bids and asks:
                self._orderbook_cache[market_id] = (now, depth, bids, asks)

        return bids, asks

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Lighter."""
        try:
            market_id = self._get_market_id(symbol)
            if market_id is None:
                return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type="dex")

            bids, asks = self._get_orderbook_cached(market_id, depth=1)
            bid = float(bids[0][0]) if bids else 0.0
            ask = float(asks[0][0]) if asks else 0.0

            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )
            
        except Exception as e:
            logger.error("❌ Lighter price fetch failed for %s: %s", symbol, e)
            # Return zero quote on failure
            return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type="dex")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book from Lighter."""
        try:
            market_id = self._get_market_id(symbol)
            if market_id is None:
                return OrderBookDepth(bids=[], asks=[])

            bids, asks = self._get_orderbook_cached(market_id, depth=depth)
            
            return OrderBookDepth(bids=bids, asks=asks)
            
        except Exception as e:
            logger.error("❌ Lighter orderbook fetch failed: %s", e)
            # Return empty orderbook on failure
            return OrderBookDepth(bids=[], asks=[])

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order on Lighter."""
        if not self._trading_enabled:
            logger.warning("❌ Order REJECTED: Trading disabled")
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

        market = self._normalize_symbol(request.symbol)
        
        try:
            is_limit = request.limit_price is not None
            order_type = "LIMIT" if is_limit else "MARKET"
            
            raise NotImplementedError(
                "Lighter 下单尚未在 perp-tools 中接入（需要基于 SignerClient 的 create_order 流程）。"
            )
            
            logger.info("✅ Lighter %s order placed: %s %.4f %s @ %.2f - ID: %s",
                       order_type, request.side.upper(), request.size,
                       request.symbol, filled_price, order_id)
            
            return Order(
                id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=filled_price,
            )
            
        except Exception as e:
            logger.exception("❌ Lighter order failed: %s", e)
            return Order(
                id=f"error-{os.urandom(4).hex()}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close a position with a market order."""
        if not self._trading_enabled:
            return Order(
                id="rejected-close",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

        closing_side = "sell" if position.order.side == "buy" else "buy"
        
        close_request = OrderRequest(
            symbol=position.order.symbol,
            side=closing_side,
            size=position.order.size,
            limit_price=None,
        )
        
        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an order on Lighter."""
        if not self._trading_enabled:
            logger.warning("❌ Cancel REJECTED: Trading disabled")
            return

        try:
            if self._api:
                self._api.cancel_order(order_id=order_id)
            else:
                self._request("DELETE", f"/api/v1/order/{order_id}")
            logger.info("✅ Lighter order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ Lighter cancel failed for %s: %s", order_id, e)
            raise RuntimeError(f"Cancel failed: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if self._api:
                orders_data = self._api.get_open_orders()
            else:
                params = {}
                if symbol:
                    params["market"] = self._normalize_symbol(symbol)
                resp = self._request("GET", "/api/v1/orders", params=params)
                orders_data = resp.get("orders", resp) if isinstance(resp, dict) else resp
            
            orders: List[Order] = []
            for raw in orders_data or []:
                if hasattr(raw, 'market_symbol'):
                    # SDK object
                    market = raw.market_symbol
                    symbol_clean = market.replace("_", "/")
                    orders.append(Order(
                        id=str(raw.order_id),
                        exchange=self.name,
                        symbol=symbol_clean,
                        side=str(raw.side).lower(),
                        size=float(raw.size),
                        price=float(raw.price or 0),
                    ))
                else:
                    # Dict from REST API
                    market = raw.get("market", "")
                    symbol_clean = market.replace("_", "/")
                    orders.append(Order(
                        id=str(raw.get("orderId", raw.get("id", ""))),
                        exchange=self.name,
                        symbol=symbol_clean,
                        side=str(raw.get("side", "")).lower(),
                        size=float(raw.get("size", 0)),
                        price=float(raw.get("price", 0)),
                    ))
            
            if orders:
                logger.info("📊 Lighter: %d active orders", len(orders))
            
            return orders
            
        except Exception as e:
            logger.error("❌ Lighter active orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get all positions on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if not self._account_api or not self._signer_client or self.account_index is None:
                return []

            resp = self._run_coro(
                self._account_api.account(by="index", value=str(int(self.account_index))),
                timeout=15.0,
            )
            accounts = getattr(resp, "accounts", None) or []
            if not accounts:
                return []
            account = accounts[0]
            raw_positions = getattr(account, "positions", None) or []
            
            positions: List[Position] = []
            for p in raw_positions:
                symbol_base = getattr(p, "symbol", "") or ""
                position_raw = getattr(p, "position", 0)
                position_size = float(position_raw or 0)
                if position_size == 0:
                    continue
                side = "buy" if position_size > 0 else "sell"
                size = abs(position_size)
                symbol_norm = f"{symbol_base}/USDT" if symbol_base else ""
                entry_price = float(getattr(p, "entry_price", 0) or 0)
                
                order = Order(
                    id=f"pos-{symbol_base}",
                    exchange=self.name,
                    symbol=symbol_norm,
                    side=side,
                    size=size,
                    price=entry_price,
                )
                
                positions.append(Position(
                    id=order.id,
                    order=order,
                    target_profit_pct=0.0,
                ))
            
            if positions:
                logger.info("📊 Lighter: %d open positions", len(positions))
            
            return positions
            
        except Exception as e:
            logger.error("❌ Lighter positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get account balances on Lighter."""
        if not self._trading_enabled:
            return []

        try:
            if not self._account_api or not self._signer_client or self.account_index is None:
                return []

            resp = self._run_coro(
                self._account_api.account(by="index", value=str(int(self.account_index))),
                timeout=15.0,
            )
            accounts = getattr(resp, "accounts", None) or []
            if not accounts:
                return []
            account = accounts[0]

            total_equity = float(getattr(account, "collateral", 0) or 0)
            available = float(getattr(account, "available_balance", total_equity) or total_equity)
            
            balances: List[Balance] = []
            locked = total_equity - available
            
            if total_equity > 0:
                balances.append(Balance(
                    asset="USDC",
                    free=available,
                    locked=locked,
                    total=total_equity,
                ))
            
            if balances:
                logger.info("💰 Lighter balance: %.2f USDC (available: %.2f)",
                           total_equity, available)
            
            return balances
            
        except Exception as e:
            logger.error("❌ Lighter balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Set up order update callback."""
        self._order_handler = handler
        logger.info("✅ Registered Lighter order update handler")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Set up position update callback."""
        self._position_handler = handler
        logger.info("✅ Registered Lighter position update handler")


def _parse_int_env(key: str) -> Optional[int]:
    val = os.getenv(key)
    if val is None or val == "":
        return None
    try:
        return int(val, 10)
    except Exception:
        return None


def _first_non_none(*vals):
    for v in vals:
        if v is not None:
            return v
    return None
