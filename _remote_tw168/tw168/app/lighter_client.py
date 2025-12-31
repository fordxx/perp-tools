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

        # WebSocket support
        self._ws_client = None
        self._ws_enabled = False

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
            # Lighter API Key 格式：0x + 80 hex = 82 字符（不同于标准 ETH 私钥的 66 字符）
            if isinstance(self.api_key_private_key, str) and self.api_key_private_key.startswith("0x"):
                key_len = len(self.api_key_private_key)
                # 接受 66 字符（ETH私钥）或 82 字符（Lighter API Key）
                if key_len not in (66, 82):
                    logger.warning(
                        "⚠️ Lighter 私钥长度异常（期望 66 或 82 字符，实际=%s）。请确认填的是 Lighter 前端生成的 API Key Private Key。",
                        key_len,
                    )
        if self.account_index is not None and self.account_index < 0:
            logger.warning("⚠️ LIGHTER_ACCOUNT_INDEX=%s 无效（必须 >= 0），SignerClient 可能校验失败", self.account_index)

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
            # Disconnect WebSocket
            if self._ws_client and self._loop and self._loop.is_running():
                try:
                    self._run_coro(self._ws_client.disconnect(), timeout=5.0)
                except Exception:
                    pass

            if self._api_client and self._loop and self._loop.is_running():
                try:
                    self._run_coro(self._api_client.close(), timeout=5.0)
                except Exception:
                    pass
        finally:
            self._ws_client = None
            self._ws_enabled = False
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
        account_index_ok = self.account_index is not None and int(self.account_index) >= 0
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

    async def _get_market_config_async(self, symbol: str) -> Tuple[int, int, int]:
        """Get market configuration (market_id, base_multiplier, price_multiplier).

        Returns multipliers needed to convert human-readable values to chain integers:
        - base_amount = size * base_multiplier
        - price = price * price_multiplier
        """
        if not self._order_api:
            raise RuntimeError("Lighter not connected")

        lighter_symbol = self._to_lighter_symbol(symbol)

        # Get order books to find market info
        resp = await self._order_api.order_books()
        order_books = getattr(resp, "order_books", None) or []

        for market in order_books:
            if getattr(market, "symbol", "") == lighter_symbol:
                market_id = getattr(market, "market_id", None)
                size_decimals = getattr(market, "supported_size_decimals", 0)
                price_decimals = getattr(market, "supported_price_decimals", 0)

                base_multiplier = pow(10, size_decimals)
                price_multiplier = pow(10, price_decimals)

                logger.info("📊 Lighter market config: %s (ID=%d) base_mult=%d price_mult=%d",
                           symbol, market_id, base_multiplier, price_multiplier)

                return market_id, base_multiplier, price_multiplier

        raise ValueError(f"Market not found for symbol {symbol} (lighter_symbol={lighter_symbol})")

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

    def get_instrument_info(self, inst_id: str) -> Optional[dict]:
        """Get instrument information compatible with OKX format.

        Returns dict with keys:
        - ctVal: Contract value (always 1 for Lighter, trades in base currency)
        - lotSz: Minimum order size
        - lotStep: Order size step
        - tickSz: Price tick size
        """
        try:
            # Convert OKX format to Lighter base symbol
            # e.g., "PUMP-USDT-SWAP" -> "PUMP"
            lighter_symbol = self._to_lighter_symbol(inst_id.replace("-SWAP", "").replace("-", "/"))

            # Get market config
            if not self._order_api:
                logger.warning("Lighter not connected, cannot get instrument info for %s", inst_id)
                return None

            # Get order books to find market info
            resp = self._run_coro(self._order_api.order_books(), timeout=10.0)
            order_books = getattr(resp, "order_books", None) or []

            for market in order_books:
                if getattr(market, "symbol", "") == lighter_symbol:
                    size_decimals = getattr(market, "supported_size_decimals", 0)
                    price_decimals = getattr(market, "supported_price_decimals", 0)

                    # Calculate minimum sizes based on decimals
                    # For example, if size_decimals=2, min size is 0.01
                    lot_sz = pow(10, -size_decimals) if size_decimals > 0 else 0.001
                    lot_step = lot_sz  # Same as minimum size
                    tick_sz = pow(10, -price_decimals) if price_decimals > 0 else 0.01

                    info = {
                        "ctVal": "1",  # Lighter trades in base currency, not contracts
                        "lotSz": str(lot_sz),
                        "lotStep": str(lot_step),
                        "tickSz": str(tick_sz),
                        "instId": inst_id,
                        "symbol": lighter_symbol,
                        "sizeDecimals": size_decimals,
                        "priceDecimals": price_decimals,
                    }

                    logger.debug("📊 Lighter instrument info: %s -> %s", inst_id, info)
                    return info

            logger.warning("Market not found for %s (mapped=%s)", inst_id, lighter_symbol)
            return None

        except Exception as e:
            logger.error("Failed to get instrument info for %s: %s", inst_id, e)
            return None

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
        """Place an order on Lighter (market or limit)."""
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

        try:
            # Get market configuration
            market_id, base_multiplier, price_multiplier = self._run_coro(
                self._get_market_config_async(request.symbol),
                timeout=10.0
            )

            # Determine order type and price
            is_limit = request.limit_price is not None

            if is_limit:
                # Limit order
                order_price = float(request.limit_price)
                order_type = self._signer_client.ORDER_TYPE_LIMIT
                time_in_force = self._signer_client.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME
            else:
                # Market order: use best bid/ask
                bids, asks = self._get_orderbook_cached(market_id, depth=1)
                if request.side == "buy":
                    order_price = float(asks[0][0]) if asks else 0.0
                else:
                    order_price = float(bids[0][0]) if bids else 0.0

                if order_price <= 0:
                    raise ValueError(f"No valid market price for {request.symbol}")

                order_type = self._signer_client.ORDER_TYPE_MARKET
                time_in_force = self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL

            # Determine side (is_ask)
            is_ask = (request.side == "sell")

            # Generate unique client order index
            client_order_index = int(time.time() * 1000) % 1000000

            # Convert size and price to chain integers
            base_amount = int(float(request.size) * base_multiplier)
            price_int = int(order_price * price_multiplier)

            # Create order via SignerClient
            logger.info("📤 Lighter placing %s order: %s %.4f %s @ %.4f (market_id=%d)",
                       "LIMIT" if is_limit else "MARKET",
                       request.side.upper(), request.size, request.symbol, order_price, market_id)

            # For IOC market orders, order_expiry must be 0 (no expiry)
            # For GTT limit orders, use -1 (SDK default, will be set by exchange)
            order_expiry = -1 if is_limit else 0

            create_order, tx_hash, error = self._run_coro(
                self._signer_client.create_order(
                    market_index=market_id,
                    client_order_index=client_order_index,
                    base_amount=base_amount,
                    price=price_int,
                    is_ask=is_ask,
                    order_type=order_type,
                    time_in_force=time_in_force,
                    reduce_only=False,
                    trigger_price=0,
                    order_expiry=order_expiry,
                ),
                timeout=15.0
            )

            if error is not None:
                logger.error("❌ Lighter order failed: %s", error)
                return Order(
                    id=f"error-{client_order_index}",
                    exchange=self.name,
                    symbol=request.symbol,
                    side=request.side,
                    size=request.size,
                    price=0.0,
                )

            order_id = str(client_order_index)
            logger.info("✅ Lighter order placed: %s %.4f %s @ %.4f - ID: %s, TxHash: %s",
                       request.side.upper(), request.size, request.symbol,
                       order_price, order_id, tx_hash)

            return Order(
                id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=order_price,
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
        """Close a position with a market order (reduce_only)."""
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

        try:
            # Get market configuration
            market_id, base_multiplier, price_multiplier = self._run_coro(
                self._get_market_config_async(position.order.symbol),
                timeout=10.0
            )

            # Market order to close: use best bid/ask
            bids, asks = self._get_orderbook_cached(market_id, depth=1)
            if closing_side == "buy":
                order_price = float(asks[0][0]) if asks else current_price
            else:
                order_price = float(bids[0][0]) if bids else current_price

            is_ask = (closing_side == "sell")
            client_order_index = int(time.time() * 1000) % 1000000

            base_amount = int(float(position.order.size) * base_multiplier)
            price_int = int(order_price * price_multiplier)

            logger.info("📤 Lighter closing position: %s %.4f %s @ %.4f",
                       closing_side.upper(), position.order.size, position.order.symbol, order_price)

            create_order, tx_hash, error = self._run_coro(
                self._signer_client.create_order(
                    market_index=market_id,
                    client_order_index=client_order_index,
                    base_amount=base_amount,
                    price=price_int,
                    is_ask=is_ask,
                    order_type=self._signer_client.ORDER_TYPE_MARKET,
                    time_in_force=self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL,
                    reduce_only=True,  # Important: close order must be reduce-only
                    trigger_price=0,
                    order_expiry=0,  # IOC market order requires 0
                ),
                timeout=15.0
            )

            if error is not None:
                logger.error("❌ Lighter close failed: %s", error)
                return Order(
                    id=f"error-{client_order_index}",
                    exchange=self.name,
                    symbol=position.order.symbol,
                    side=closing_side,
                    size=position.order.size,
                    price=0.0,
                )

            order_id = str(client_order_index)
            logger.info("✅ Lighter position closed: %s %.4f %s @ %.4f - ID: %s",
                       closing_side.upper(), position.order.size, position.order.symbol,
                       order_price, order_id)

            return Order(
                id=order_id,
                exchange=self.name,
                symbol=position.order.symbol,
                side=closing_side,
                size=position.order.size,
                price=order_price,
            )

        except Exception as e:
            logger.exception("❌ Lighter close order failed: %s", e)
            return Order(
                id=f"error-{os.urandom(4).hex()}",
                exchange=self.name,
                symbol=position.order.symbol,
                side=closing_side,
                size=position.order.size,
                price=0.0,
            )

    def place_stop_loss(self, symbol: str, side: str, size: float, trigger_price: float, limit_price: Optional[float] = None) -> Order:
        """Place a stop-loss order on Lighter.

        Args:
            symbol: Trading pair symbol (e.g., "ETH/USDT")
            side: "buy" or "sell" (closing side)
            size: Order size
            trigger_price: Stop loss trigger price
            limit_price: Optional limit price (if None, uses market order after trigger)
        """
        if not self._trading_enabled:
            logger.warning("❌ Stop-loss REJECTED: Trading disabled")
            return Order(
                id="rejected-sl",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

        try:
            # Get market configuration
            market_id, base_multiplier, price_multiplier = self._run_coro(
                self._get_market_config_async(symbol),
                timeout=10.0
            )

            is_ask = (side == "sell")
            client_order_index = int(time.time() * 1000) % 1000000

            base_amount = int(float(size) * base_multiplier)
            trigger_price_int = int(trigger_price * price_multiplier)

            # Choose order type
            if limit_price is not None:
                order_type = self._signer_client.ORDER_TYPE_STOP_LOSS_LIMIT
                price_int = int(limit_price * price_multiplier)
            else:
                order_type = self._signer_client.ORDER_TYPE_STOP_LOSS
                # For stop-loss market, use trigger price as execution price
                price_int = trigger_price_int

            logger.info("📤 Lighter placing SL: %s %.4f %s @ trigger=%.4f limit=%s",
                       side.upper(), size, symbol, trigger_price, limit_price or "market")

            tif = self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL
            create_order, tx_hash, error = self._run_coro(
                self._signer_client.create_order(
                    market_index=market_id,
                    client_order_index=client_order_index,
                    base_amount=base_amount,
                    price=price_int,
                    is_ask=is_ask,
                    order_type=order_type,
                    time_in_force=tif,
                    reduce_only=True,  # SL should be reduce-only
                    trigger_price=trigger_price_int,
                ),
                timeout=15.0
            )

            if error is not None:
                logger.error("❌ Lighter SL failed: %s", error)
                return Order(
                    id=f"error-sl-{client_order_index}",
                    exchange=self.name,
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=0.0,
                )

            order_id = str(client_order_index)
            logger.info("✅ Lighter SL placed: %s %.4f %s @ trigger=%.4f - ID: %s",
                       side.upper(), size, symbol, trigger_price, order_id)

            return Order(
                id=order_id,
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=trigger_price,
            )

        except Exception as e:
            logger.exception("❌ Lighter stop-loss failed: %s", e)
            return Order(
                id=f"error-{os.urandom(4).hex()}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

    def place_take_profit(self, symbol: str, side: str, size: float, trigger_price: float, limit_price: Optional[float] = None) -> Order:
        """Place a take-profit order on Lighter.

        Args:
            symbol: Trading pair symbol (e.g., "ETH/USDT")
            side: "buy" or "sell" (closing side)
            size: Order size
            trigger_price: Take profit trigger price
            limit_price: Optional limit price (if None, uses market order after trigger)
        """
        if not self._trading_enabled:
            logger.warning("❌ Take-profit REJECTED: Trading disabled")
            return Order(
                id="rejected-tp",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

        try:
            # Get market configuration
            market_id, base_multiplier, price_multiplier = self._run_coro(
                self._get_market_config_async(symbol),
                timeout=10.0
            )

            is_ask = (side == "sell")
            client_order_index = int(time.time() * 1000) % 1000000

            base_amount = int(float(size) * base_multiplier)
            trigger_price_int = int(trigger_price * price_multiplier)

            # Choose order type
            if limit_price is not None:
                order_type = self._signer_client.ORDER_TYPE_TAKE_PROFIT_LIMIT
                price_int = int(limit_price * price_multiplier)
            else:
                order_type = self._signer_client.ORDER_TYPE_TAKE_PROFIT
                # For TP market, use trigger price as execution price
                price_int = trigger_price_int

            logger.info("📤 Lighter placing TP: %s %.4f %s @ trigger=%.4f limit=%s",
                       side.upper(), size, symbol, trigger_price, limit_price or "market")

            tif = self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL
            create_order, tx_hash, error = self._run_coro(
                self._signer_client.create_order(
                    market_index=market_id,
                    client_order_index=client_order_index,
                    base_amount=base_amount,
                    price=price_int,
                    is_ask=is_ask,
                    order_type=order_type,
                    time_in_force=tif,
                    reduce_only=True,  # TP should be reduce-only
                    trigger_price=trigger_price_int,
                ),
                timeout=15.0
            )

            if error is not None:
                logger.error("❌ Lighter TP failed: %s", error)
                return Order(
                    id=f"error-tp-{client_order_index}",
                    exchange=self.name,
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=0.0,
                )

            order_id = str(client_order_index)
            logger.info("✅ Lighter TP placed: %s %.4f %s @ trigger=%.4f - ID: %s",
                       side.upper(), size, symbol, trigger_price, order_id)

            return Order(
                id=order_id,
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=trigger_price,
            )

        except Exception as e:
            logger.exception("❌ Lighter take-profit failed: %s", e)
            return Order(
                id=f"error-{os.urandom(4).hex()}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

    def cancel_order(self, order_id: str, symbol: Optional[str] = None, market_id: Optional[int] = None) -> None:
        """Cancel an order on Lighter.

        Args:
            order_id: Client order index (order ID)
            symbol: Trading pair symbol (e.g., "EIGEN/USDT") - required if market_id not provided
            market_id: Market ID - if not provided, will be derived from symbol
        """
        if not self._trading_enabled:
            logger.warning("❌ Cancel REJECTED: Trading disabled")
            return

        try:
            # Get market_id if not provided
            if market_id is None:
                if symbol is None:
                    raise ValueError("Either symbol or market_id must be provided")
                market_id, _, _ = self._run_coro(
                    self._get_market_config_async(symbol),
                    timeout=10.0
                )

            # Convert order_id to int
            client_order_index = int(order_id)

            logger.info("📤 Lighter cancelling order: market_id=%d order_id=%s", market_id, order_id)

            # Cancel order via SignerClient
            cancel_result, tx_hash, error = self._run_coro(
                self._signer_client.cancel_order(
                    market_index=market_id,
                    order_index=client_order_index,
                ),
                timeout=15.0
            )

            if error:
                logger.error("❌ Lighter cancel failed for %s: %s", order_id, error)
                raise RuntimeError(f"Cancel failed: {error}")

            logger.info("✅ Lighter order cancelled: %s (TxHash: %s)", order_id, tx_hash)

        except Exception as e:
            logger.error("❌ Lighter cancel failed for %s: %s", order_id, e)
            raise RuntimeError(f"Cancel failed: {e}")

    def cancel_all_orders(self) -> bool:
        """
        Cancel all pending orders on Lighter using SignerClient.cancel_all_orders().

        Returns:
            True if successful (or no error reported), False otherwise
        """
        if not self._trading_enabled or not self._signer_client:
            logger.error("❌ cancel_all_orders requires SignerClient (trading enabled)")
            return False

        try:
            import time

            logger.info("📤 Lighter cancelling all orders...")

            # time_in_force=0 means cancel all orders immediately
            timestamp_ms = int(time.time() * 1000)

            cancel_result, tx_hash, error = self._run_coro(
                self._signer_client.cancel_all_orders(
                    time_in_force=0,  # CANCEL_ALL_TIF_IMMEDIATE
                    timestamp_ms=timestamp_ms
                ),
                timeout=15.0
            )

            if error:
                logger.warning("⚠️ Lighter cancel_all_orders returned error: %s", error)
                logger.warning("   This may mean there were no orders to cancel (which is OK)")
                # Don't treat this as failure - might just mean no orders exist
                return True

            logger.info("✅ Lighter cancel_all_orders submitted (TxHash: %s)", tx_hash)
            return True

        except Exception as e:
            logger.error("❌ Lighter cancel_all_orders failed: %s", e)
            return False

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders for a symbol using OrderApi.account_active_orders."""
        if not self._order_api or self.account_index is None:
            return []
        if not symbol:
            return []
        try:
            auth_token = None
            if self._signer_client:
                auth_token, err = self._signer_client.create_auth_token_with_expiry()
                if err is not None:
                    logger.warning("⚠️ Lighter auth token error: %s", err)
                    auth_token = None

            market_id, _, _ = self._run_coro(
                self._get_market_config_async(symbol),
                timeout=10.0,
            )
            resp = self._run_coro(
                self._order_api.account_active_orders(
                    account_index=int(self.account_index),
                    market_id=market_id,
                    authorization=auth_token,
                    auth=auth_token,
                ),
                timeout=15.0,
            )
            return getattr(resp, "orders", None) or []
        except Exception as e:
            logger.warning("⚠️ Lighter get_active_orders failed symbol=%s err=%s", symbol, e)
            return []

    def cancel_all_orders_for_symbol(self, symbol: str) -> tuple[int, int]:
        """Cancel all active orders for a given symbol."""
        canceled = 0
        failed = 0
        orders = self.get_active_orders(symbol)
        for order in orders:
            order_id = getattr(order, "client_order_index", None)
            fallback_id = getattr(order, "order_index", None)
            try:
                if order_id is not None:
                    self.cancel_order(order_id=str(order_id), symbol=symbol)
                elif fallback_id is not None:
                    self.cancel_order(order_id=str(fallback_id), symbol=symbol)
                else:
                    failed += 1
                    continue
                canceled += 1
            except Exception:
                failed += 1
        return canceled, failed

    def get_position(self, *, inst_id: str, pos_side: str) -> dict[str, Any] | None:
        """Get a specific position by inst_id and pos_side (compatible with OKX interface)."""
        all_positions = self.get_account_positions()

        # Convert inst_id from "TON-USDT-SWAP" to "TON/USDT"
        symbol = inst_id.replace("-USDT-SWAP", "/USDT")

        for pos in all_positions:
            if pos.order.symbol == symbol:
                # pos_side: "long" means buy, "short" means sell
                expected_side = "buy" if pos_side.lower() == "long" else "sell"
                if pos.order.side == expected_side:
                    # Return OKX-compatible format
                    return {
                        "instId": inst_id,
                        "posSide": pos_side,
                        "pos": str(pos.order.size),
                        "avgPx": str(pos.order.price),
                    }
        return None

    def get_order_fills(self, *, inst_id: str, order_id: str) -> tuple[float, float] | None:
        """Fetch filled size and average price for a specific order via trade history."""
        if not self._account_api or self.account_index is None:
            return None
        try:
            symbol = inst_id.replace("-SWAP", "").replace("-", "/")
            market_id, _, _ = self._run_coro(
                self._get_market_config_async(symbol),
                timeout=10.0,
            )
            order_index = int(order_id)
            resp = self._run_coro(
                self._account_api.trades(
                    sort_by="timestamp",
                    limit=100,
                    market_id=market_id,
                    account_index=int(self.account_index),
                    order_index=order_index,
                ),
                timeout=15.0,
            )
            trades = getattr(resp, "trades", None) or []
            total_sz = 0.0
            total_val = 0.0
            for trade in trades:
                try:
                    ask_id = int(getattr(trade, "ask_client_id", -1) or -1)
                    bid_id = int(getattr(trade, "bid_client_id", -1) or -1)
                    if order_index not in (ask_id, bid_id):
                        continue
                    size = float(getattr(trade, "size", 0) or 0)
                    price = float(getattr(trade, "price", 0) or 0)
                    if size <= 0 or price <= 0:
                        continue
                    total_sz += size
                    total_val += size * price
                except Exception:
                    continue
            if total_sz > 0:
                logger.info("✅ Lighter fills fetched order=%s sz=%.4f px=%.6f", order_id, total_sz, total_val / total_sz)
                return total_sz, (total_val / total_sz)
        except Exception as e:
            logger.warning("⚠️ Lighter trade fetch failed for order=%s: %s", order_id, e)
        return None

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

    # ==================== WebSocket Support ====================

    def enable_websocket(self, auto_subscribe_account: bool = True) -> None:
        """Enable WebSocket streaming for real-time data.

        Args:
            auto_subscribe_account: Automatically subscribe to account updates (positions, orders)
        """
        if not self._connected:
            raise RuntimeError("Lighter not connected. Call connect() first.")

        if self._ws_enabled and self._ws_client:
            logger.info("ℹ️ Lighter WebSocket already enabled")
            return

        try:
            from perpbot.exchanges.lighter_websocket import LighterWebSocketClient

            # Create WebSocket client
            self._ws_client = LighterWebSocketClient(
                ws_url=self.ws_url,
                account_id=self.account_index if self._trading_enabled else None,
                auth_token=None,  # Auth token is managed separately if needed
            )

            # Connect WebSocket
            self._run_coro(self._ws_client.connect(), timeout=10.0)
            self._ws_enabled = True

            logger.info("✅ Lighter WebSocket enabled")

            # Auto-subscribe to account updates if trading is enabled
            if auto_subscribe_account and self._trading_enabled and self.account_index:
                self._run_coro(self._setup_account_subscriptions(), timeout=10.0)

        except Exception as e:
            logger.error("❌ Failed to enable Lighter WebSocket: %s", e)
            self._ws_client = None
            self._ws_enabled = False
            raise

    def disable_websocket(self) -> None:
        """Disable WebSocket streaming."""
        if self._ws_client and self._loop and self._loop.is_running():
            try:
                self._run_coro(self._ws_client.disconnect(), timeout=5.0)
            except Exception as e:
                logger.error("Error disconnecting WebSocket: %s", e)

        self._ws_client = None
        self._ws_enabled = False
        logger.info("✅ Lighter WebSocket disabled")

    async def _setup_account_subscriptions(self) -> None:
        """Setup default account-level WebSocket subscriptions."""
        if not self._ws_client:
            return

        try:
            # Subscribe to all account updates (positions, orders, trades, balances)
            await self._ws_client.subscribe_account_all(
                callback=self._on_account_update,
            )
            logger.info("✅ Subscribed to Lighter account updates")

            # Subscribe to position updates
            await self._ws_client.subscribe_account_positions(
                callback=self._on_position_update,
            )
            logger.info("✅ Subscribed to Lighter position updates")

            # Subscribe to order updates
            await self._ws_client.subscribe_account_orders(
                callback=self._on_order_update,
            )
            logger.info("✅ Subscribed to Lighter order updates")

        except Exception as e:
            logger.error("❌ Failed to setup account subscriptions: %s", e)

    async def _on_account_update(self, data: dict) -> None:
        """Handle account update from WebSocket."""
        try:
            msg_type = data.get("type")
            logger.debug("📥 Lighter account update: %s", msg_type)
        except Exception as e:
            logger.error("Error handling account update: %s", e)

    async def _on_position_update(self, data: dict) -> None:
        """Handle position update from WebSocket."""
        try:
            if self._position_handler:
                self._position_handler(data)
            else:
                logger.debug("📥 Lighter position update (no handler): %s", data.get("type"))
        except Exception as e:
            logger.error("Error handling position update: %s", e)

    async def _on_order_update(self, data: dict) -> None:
        """Handle order update from WebSocket."""
        try:
            if self._order_handler:
                self._order_handler(data)
            else:
                logger.debug("📥 Lighter order update (no handler): %s", data.get("type"))
        except Exception as e:
            logger.error("Error handling order update: %s", e)

    def subscribe_orderbook_stream(self, symbol: str, callback: Callable[[dict], None]) -> None:
        """Subscribe to real-time orderbook updates for a symbol.

        Args:
            symbol: Trading symbol (e.g., "ETH/USDT", "BTC/USDC")
            callback: Callback function to handle orderbook updates
        """
        if not self._ws_enabled or not self._ws_client:
            raise RuntimeError("WebSocket not enabled. Call enable_websocket() first.")

        market_id = self._get_market_id(symbol)
        if market_id is None:
            raise ValueError(f"Market not found for symbol: {symbol}")

        async def async_subscribe():
            await self._ws_client.subscribe_orderbook(market_id, callback)

        self._run_coro(async_subscribe(), timeout=5.0)
        logger.info("✅ Subscribed to Lighter orderbook stream: %s (market_id=%d)", symbol, market_id)

    def subscribe_trades_stream(self, symbol: str, callback: Callable[[dict], None]) -> None:
        """Subscribe to real-time trade executions for a symbol.

        Args:
            symbol: Trading symbol (e.g., "ETH/USDT", "BTC/USDC")
            callback: Callback function to handle trade data
        """
        if not self._ws_enabled or not self._ws_client:
            raise RuntimeError("WebSocket not enabled. Call enable_websocket() first.")

        market_id = self._get_market_id(symbol)
        if market_id is None:
            raise ValueError(f"Market not found for symbol: {symbol}")

        async def async_subscribe():
            await self._ws_client.subscribe_trades(market_id, callback)

        self._run_coro(async_subscribe(), timeout=5.0)
        logger.info("✅ Subscribed to Lighter trades stream: %s (market_id=%d)", symbol, market_id)

    def subscribe_market_stats_stream(self, symbol: str, callback: Callable[[dict], None]) -> None:
        """Subscribe to real-time market statistics for a symbol.

        Args:
            symbol: Trading symbol (e.g., "ETH/USDT") or "all" for all markets
            callback: Callback function to handle market stats
        """
        if not self._ws_enabled or not self._ws_client:
            raise RuntimeError("WebSocket not enabled. Call enable_websocket() first.")

        if symbol.lower() == "all":
            market_id = "all"
        else:
            market_id = self._get_market_id(symbol)
            if market_id is None:
                raise ValueError(f"Market not found for symbol: {symbol}")

        async def async_subscribe():
            await self._ws_client.subscribe_market_stats(market_id, callback)

        self._run_coro(async_subscribe(), timeout=5.0)
        logger.info("✅ Subscribed to Lighter market stats stream: %s", symbol)


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
