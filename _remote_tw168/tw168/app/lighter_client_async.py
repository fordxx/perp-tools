"""Lighter DEX Native Async Client - 最强模式 🔥

完全原生 async/await 实现，无 threading 开销。
基于 lighter-sdk 1.0.0 (aiohttp)。

环境变量：
- LIGHTER_API_KEY_PRIVATE_KEY: API Key 私钥 (0x前缀)
- LIGHTER_ACCOUNT_INDEX: 账户索引 (十进制)
- LIGHTER_API_KEY_INDEX: API Key 索引 (十进制)
- LIGHTER_ENV: mainnet/testnet (默认 mainnet)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from lighter import ApiClient, Configuration, AccountApi, OrderApi, SignerClient, CandlestickApi, WsClient

logger = logging.getLogger("uvicorn.error")


class LighterClient:
    """Lighter DEX 原生异步客户端"""

    MAINNET_API = "https://mainnet.zklighter.elliot.ai"
    TESTNET_API = "https://testnet.zklighter.elliot.ai"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "lighter"
        self.use_testnet = use_testnet
        
        # Credentials
        self.api_key_private_key: Optional[str] = None
        self.account_index: Optional[int] = None
        self.api_key_index: Optional[int] = None
        
        # Connection state
        self._connected = False
        self._trading_enabled = False
        
        # API clients
        self._api_client: Optional[ApiClient] = None
        self._order_api: Optional[OrderApi] = None
        self._account_api: Optional[AccountApi] = None
        self._signer_client: Optional[SignerClient] = None
        self._candlestick_api: Optional[CandlestickApi] = None
        
        # WebSocket
        self._ws_client: Optional[WsClient] = None
        self._ws_enabled = False
        self._ws_task: Optional[asyncio.Task] = None
        self._ws_orderbook_handlers: Dict[int, Any] = {}
        self._ws_trade_handlers: Dict[int, Any] = {}
        
        # Market cache: symbol -> market_id
        self._markets: Dict[str, int] = {}
        self._market_meta: Dict[str, Dict[str, Any]] = {}
        
        # Orderbook cache (TTL 250ms)
        self._orderbook_cache: Dict[int, Tuple[float, List[Tuple[float, float]], List[Tuple[float, float]]]] = {}
        self._cache_ttl_ms = 250
        # Algo order dedupe guard
        self._algo_guard: Dict[str, float] = {}
        self._algo_guard_ttl_s = 120

    async def connect(self) -> None:
        """连接 Lighter (公开行情 + 可选交易)"""
        load_dotenv()
        
        # Determine endpoint
        env = os.getenv("LIGHTER_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        
        # Initialize API client
        config = Configuration(host=base_url)
        self._api_client = ApiClient(configuration=config)
        self._order_api = OrderApi(api_client=self._api_client)
        self._account_api = AccountApi(api_client=self._api_client)
        self._candlestick_api = CandlestickApi(api_client=self._api_client)
        
        # Load trading credentials (optional)
        self.api_key_private_key = os.getenv("LIGHTER_API_KEY_PRIVATE_KEY", "").strip() or None
        self.account_index = self._parse_int_env("LIGHTER_ACCOUNT_INDEX")
        self.api_key_index = self._parse_int_env("LIGHTER_API_KEY_INDEX")

        if self.api_key_private_key:
            key = self.api_key_private_key.strip()
            if key and not key.startswith("0x"):
                is_hex = all(c in "0123456789abcdefABCDEF" for c in key)
                if is_hex and len(key) % 2 == 0:
                    self.api_key_private_key = "0x" + key
        
        # Initialize SignerClient if credentials available
        if self.api_key_private_key and self.account_index is not None and self.api_key_index is not None:
            self._signer_client = SignerClient(
                url=base_url,
                account_index=self.account_index,
                api_private_keys={self.api_key_index: self.api_key_private_key}
            )
            self._trading_enabled = True
            logger.info("✅ Lighter trading mode enabled")
        
        # Load market mappings
        await self._load_markets()
        
        self._connected = True
        logger.info("✅ Lighter connected (%s, %d markets)", env, len(self._markets))

    async def disconnect(self) -> None:
        """断开连接"""
        if self._api_client:
            await self._api_client.close()
        if self._signer_client:
            try:
                await self._signer_client.close()
            except Exception:
                pass
        self._connected = False
        logger.info("👋 Lighter disconnected")

    def _parse_int_env(self, name: str) -> Optional[int]:
        """解析整数环境变量"""
        value = os.getenv(name, "").strip()
        if not value:
            return None
        try:
            return int(value, 0)  # Support 0x prefix
        except ValueError:
            return None

    async def _load_markets(self) -> None:
        """加载市场 ID 映射"""
        try:
            resp = await self._order_api.order_books()
            order_books = resp.order_books or []
            
            for book in order_books:
                market_id = book.market_id if hasattr(book, "market_id") else None
                symbol = book.symbol if hasattr(book, "symbol") else None
                if market_id is None or not symbol:
                    continue
                lighter_symbol = self._to_lighter_symbol(symbol)
                self._markets[lighter_symbol] = market_id
                self._market_meta[lighter_symbol] = {
                    "market_id": market_id,
                    "size_decimals": getattr(book, "supported_size_decimals", 0),
                    "price_decimals": getattr(book, "supported_price_decimals", 0),
                    "min_base_amount": getattr(book, "min_base_amount", None),
                    "min_quote_amount": getattr(book, "min_quote_amount", None),
                }
            
            logger.info("📊 Loaded %d markets", len(self._markets))
        except Exception as e:
            logger.error("Failed to load markets: %s", str(e))

    def _to_lighter_symbol(self, symbol: str) -> str:
        if not symbol:
            return ""
        normalized = symbol.replace("-USDT-SWAP", "").replace("-USDC-SWAP", "")
        normalized = normalized.replace("-", "/")
        if "/" in normalized:
            normalized = normalized.split("/", 1)[0]
        return normalized.strip().upper()

    async def _get_market_id(self, symbol: str) -> Optional[int]:
        """获取 market_id"""
        lighter_symbol = self._to_lighter_symbol(symbol)
        market_id = self._markets.get(lighter_symbol)
        if market_id is None:
            # Refresh cache
            await self._load_markets()
            market_id = self._markets.get(lighter_symbol)
        
        return market_id

    async def _get_market_config(self, symbol: str) -> Tuple[int, int, int]:
        lighter_symbol = self._to_lighter_symbol(symbol)
        meta = self._market_meta.get(lighter_symbol)
        if meta is None:
            await self._load_markets()
            meta = self._market_meta.get(lighter_symbol)
        if meta is None:
            raise ValueError(f"Market not found for symbol: {symbol}")
        market_id = int(meta.get("market_id"))
        size_decimals = int(meta.get("size_decimals") or 0)
        price_decimals = int(meta.get("price_decimals") or 0)
        return market_id, pow(10, size_decimals), pow(10, price_decimals)

    def _scale_value(self, value: str | float | Decimal, multiplier: int) -> int:
        return int((Decimal(str(value)) * Decimal(multiplier)).to_integral_value(rounding=ROUND_DOWN))

    def _get_okx_store(self) -> Dict[str, Dict[str, Any]]:
        store = getattr(self, "_okx_compat_state", None)
        if store is None:
            store = {"cl_to_order": {}, "order_to_cl": {}, "order_meta": {}, "protective_by_key": {}}
            setattr(self, "_okx_compat_state", store)
        return store

    # ========== Public Market Data (OKX-compatible interface) ==========

    async def get_last_price(self, *, inst_id: str) -> Optional[float]:
        """获取最新价格"""
        price_data = await self.get_current_price(inst_id.replace("-USDT-SWAP", "").replace("-", "/"))
        if price_data and price_data.get("last"):
            return price_data["last"]
        return None

    async def get_current_price(self, symbol: str) -> Optional[Dict[str, float]]:
        """获取当前价格 (bid/ask/last)"""
        market_id = await self._get_market_id(symbol)
        if market_id is None:
            return None
        
        try:
            # Use cached orderbook for price
            now = time.time() * 1000
            if market_id in self._orderbook_cache:
                cached_ts, bids, asks = self._orderbook_cache[market_id]
                if (now - cached_ts) < self._cache_ttl_ms:
                    bid = bids[0][0] if bids else 0.0
                    ask = asks[0][0] if asks else 0.0
                    last = (bid + ask) / 2 if bid and ask else (bid or ask)
                    return {"bid": bid, "ask": ask, "last": last}
            
            # Fetch fresh data
            resp = await self._order_api.order_book_orders(market_id=market_id, limit=1)
            bids_raw = resp.bids or []
            asks_raw = resp.asks or []
            
            # Parse orders - handle different attribute names
            bids = []
            for b in bids_raw:
                price = float(b.price)
                # Try different attribute names for size
                size = float(getattr(b, "remaining_base_amount", None) or getattr(b, "size", None) or getattr(b, "amount", None) or getattr(b, "quantity", None) or 0)
                if price > 0 and size > 0:
                    bids.append((price, size))
            
            asks = []
            for a in asks_raw:
                price = float(a.price)
                size = float(getattr(a, "remaining_base_amount", None) or getattr(a, "size", None) or getattr(a, "amount", None) or getattr(a, "quantity", None) or 0)
                if price > 0 and size > 0:
                    asks.append((price, size))
            
            # Cache
            self._orderbook_cache[market_id] = (now, bids, asks)
            
            bid = bids[0][0] if bids else 0.0
            ask = asks[0][0] if asks else 0.0
            last = (bid + ask) / 2 if bid and ask else (bid or ask)
            
            return {"bid": bid, "ask": ask, "last": last}
            
        except Exception as e:
            logger.error("Failed to get price for %s: %s", symbol, str(e))
            return None

    async def get_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict[str, Any]]:
        """获取订单簿"""
        market_id = await self._get_market_id(symbol)
        if market_id is None:
            return None
        
        try:
            resp = await self._order_api.order_book_orders(market_id=market_id, limit=depth)
            bids_raw = resp.bids or []
            asks_raw = resp.asks or []
            
            # Parse orders - handle different attribute names
            bids = []
            for b in bids_raw:
                price = float(b.price)
                size = float(getattr(b, "remaining_base_amount", None) or getattr(b, "size", None) or getattr(b, "amount", None) or getattr(b, "quantity", None) or 0)
                if price > 0 and size > 0:
                    bids.append((price, size))
            
            asks = []
            for a in asks_raw:
                price = float(a.price)
                size = float(getattr(a, "remaining_base_amount", None) or getattr(a, "size", None) or getattr(a, "amount", None) or getattr(a, "quantity", None) or 0)
                if price > 0 and size > 0:
                    asks.append((price, size))
            
            return {
                "bids": bids,
                "asks": asks,
                "timestamp": int(time.time() * 1000)
            }
        except Exception as e:
            logger.error("Failed to get orderbook for %s: %s", symbol, str(e))
            return None

    async def get_instrument_info(self, *, inst_id: str) -> Optional[Dict[str, Any]]:
        """获取合约信息 (OKX 格式兼容)"""
        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        lighter_symbol = self._to_lighter_symbol(symbol)
        meta = self._market_meta.get(lighter_symbol)
        if meta is None:
            await self._load_markets()
            meta = self._market_meta.get(lighter_symbol)
        if not meta:
            return None

        size_decimals = int(meta.get("size_decimals") or 0)
        price_decimals = int(meta.get("price_decimals") or 0)
        lot_step = Decimal("1") / (Decimal(10) ** size_decimals) if size_decimals >= 0 else Decimal("1")
        tick_size = Decimal("1") / (Decimal(10) ** price_decimals) if price_decimals >= 0 else Decimal("1")
        lot_sz = meta.get("min_base_amount") or str(lot_step)
        min_quote = meta.get("min_quote_amount")
        return {
            "instId": inst_id,
            "ctVal": "1",
            "lotSz": str(lot_sz),
            "lotStep": str(lot_step),
            "tickSz": str(tick_size),
            "minQuote": str(min_quote) if min_quote is not None else None,
        }

    async def fetch_candles(self, *, inst_id: str, tf: str, limit: int = 300) -> list:
        """获取K线数据 (OKX-compatible interface)
        
        Args:
            inst_id: 合约ID (e.g., "EIGEN-USDT-SWAP")
            tf: 时间周期 (e.g., "1m", "5m", "15m", "1h", "4h", "1d")
            limit: 数量限制 (默认300)
            
        Returns:
            List of Candle objects with ts_ms, o, h, l, c
            
        Note:
            Lighter的K线API需要认证(403 Forbidden)，因此回退到OKX公开API获取数据
        """
        from app.risk import Candle, fetch_candles_paged
        
        # Fallback to OKX public API (same data, no auth required)
        # Convert EIGEN-USDT-SWAP -> EIGEN-USDT-SWAP (keep OKX format)
        try:
            logger.info("fetch_candles: using OKX fallback for %s %s", inst_id, tf)
            # Use asyncio.to_thread for sync function
            candles = await asyncio.to_thread(
                fetch_candles_paged,
                base_url="https://www.okx.com",
                inst_id=inst_id,
                bar=tf,
                limit=limit
            )
            logger.info("fetch_candles: %s %s -> %d candles (OKX)", inst_id, tf, len(candles))
            return candles
        except Exception as e:
            logger.error("fetch_candles failed: %s %s - %s", inst_id, tf, str(e))
            return []

    # ========== Trading Operations ==========

    async def place_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        px: Optional[str],
        cl_ord_id: str,
        sl_trigger_px: Optional[str],
        tp_trigger_px: Optional[str],
        reduce_only: bool = False,
    ) -> Dict[str, Any]:
        """下单 (OKX 接口兼容)"""
        if not self._trading_enabled or not self._signer_client:
            return {"code": "1", "msg": "Trading not enabled (missing credentials)"}
        
        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        try:
            market_id, base_multiplier, price_multiplier = await self._get_market_config(symbol)
        except Exception as e:
            return {"code": "1", "msg": str(e)}
        
        try:
            # Determine order type
            is_limit = (ord_type == "limit")
            
            # Get order price
            if is_limit and px:
                order_price = float(px)
            else:
                # Market order: use best bid/ask
                price_data = await self.get_current_price(symbol)
                if not price_data:
                    return {"code": "1", "msg": "No market price available"}
                if side == "buy":
                    order_price = price_data.get("ask") or price_data.get("last")
                else:
                    order_price = price_data.get("bid") or price_data.get("last")
                if not order_price:
                    return {"code": "1", "msg": "No market price available"}
            
            # Determine side
            is_ask = (side == "sell")
            
            # Order parameters
            order_type = self._signer_client.ORDER_TYPE_LIMIT if is_limit else self._signer_client.ORDER_TYPE_MARKET
            time_in_force = (
                self._signer_client.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME
                if is_limit
                else self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL
            )
            
            # Generate unique client order index
            client_order_index = int(time.time() * 1000) % 1000000
            
            # Convert size to chain integer (Lighter uses 6 decimals for both size and price)
            base_amount = self._scale_value(sz, base_multiplier)
            price_int = self._scale_value(order_price, price_multiplier)
            if base_amount <= 0:
                return {"code": "1", "msg": "Order size too small"}
            lighter_symbol = self._to_lighter_symbol(symbol)
            meta = self._market_meta.get(lighter_symbol)
            if meta and meta.get("min_base_amount") is not None:
                try:
                    min_base_units = self._scale_value(meta["min_base_amount"], base_multiplier)
                    if base_amount < min_base_units:
                        return {"code": "1", "msg": "Order size below min_base_amount"}
                except Exception:
                    pass
            if meta and meta.get("min_quote_amount") is not None:
                try:
                    min_quote = Decimal(str(meta["min_quote_amount"]))
                    order_value = Decimal(str(order_price)) * Decimal(str(sz))
                    if order_value < min_quote:
                        return {"code": "1", "msg": "Order value below min_quote_amount"}
                except Exception:
                    pass
            
            # Place order
            logger.info("📤 Placing %s order: %s %.4f %s @ %.4f",
                       "LIMIT" if is_limit else "MARKET",
                       side.upper(), float(sz), symbol, order_price)
            
            # Order expiry: 
            # - For limit orders (GTT): must use 0 for Lighter (no expiry)
            # - For market orders (IOC): use 0 (immediate execution)
            # Lighter validation requires expiry=0, unlike SDK default of -1
            order_expiry = -1 if is_limit else 0
            
            # For Lighter: trigger_price defaults to NIL_TRIGGER_PRICE=0 in SDK
            # Explicitly passing it for clarity, but SDK uses 0 as default (no trigger)
            order_params = {
                "market_index": market_id,
                "client_order_index": client_order_index,
                "base_amount": base_amount,
                "price": price_int,
                "is_ask": is_ask,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "reduce_only": reduce_only,
                "order_expiry": order_expiry,
            }
            
            # Only add trigger_price if not a regular order (for TP/SL orders)
            # For regular orders, don't pass it at all - let SDK use default NIL_TRIGGER_PRICE
            # This avoids "TriggerPrice is invalid" error
            
            logger.info("📤 Placing %s order: %s %.4f %s @ %.4f (params: type=%s tif=%s expiry=%s)",
                       "LIMIT" if is_limit else "MARKET",
                       "SELL" if is_ask else "BUY",
                       float(sz), symbol.replace("/", ""),
                       order_price,
                       order_type, time_in_force, order_expiry)
            
            create_order, tx_response, error = await self._signer_client.create_order(**order_params)
            
            if error is not None:
                logger.error("❌ Order failed: %s", error)
                logger.error("  Order params: market_id=%s base_amount=%s price=%s side=%s type=%s tif=%s",
                           market_id, base_amount, price_int, "SELL" if is_ask else "BUY",
                           order_type, time_in_force)
                return {"code": "1", "msg": str(error)}

            tx_code = getattr(tx_response, "code", None)
            tx_message = getattr(tx_response, "message", None)
            tx_hash = getattr(tx_response, "tx_hash", None)
            logger.info("✅ Order tx response: code=%s message=%s tx_hash=%s", tx_code, tx_message, tx_hash)
            if tx_code not in (0, 200, None):
                return {"code": "1", "msg": f"order rejected: code={tx_code} message={tx_message}"}
            
            store = self._get_okx_store()
            if cl_ord_id:
                store["cl_to_order"][cl_ord_id] = str(client_order_index)
                store["order_to_cl"][str(client_order_index)] = cl_ord_id
            store["order_meta"][str(client_order_index)] = {
                "inst_id": inst_id,
                "symbol": symbol,
                "side": side,
                "pos_side": pos_side,
                "ord_type": ord_type,
                "sz": str(sz),
                "px": str(order_price),
                "reduce_only": reduce_only,
                "ts": time.time(),
            }

            return {
                "code": "0",
                "msg": "",
                "data": [{
                    "ordId": str(client_order_index),
                    "clOrdId": cl_ord_id,
                    "sCode": "0",
                    "sMsg": "",
                }]
            }
            
        except Exception as e:
            logger.error("Order placement failed: %s", str(e))
            return {"code": "1", "msg": str(e)}

    async def place_algo_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        sl_trigger_px: Optional[str] = None,
        sl_ord_px: Optional[str] = None,
        tp_trigger_px: Optional[str] = None,
        tp_ord_px: Optional[str] = None,
    ) -> Dict[str, Any]:
        """下算法单 (止损/止盈)"""
        if not self._trading_enabled or not self._signer_client:
            return {"code": "1", "msg": "Trading not enabled (missing credentials)"}

        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        try:
            market_id, base_multiplier, price_multiplier = await self._get_market_config(symbol)
        except Exception as e:
            return {"code": "1", "msg": str(e)}

        try:
            is_ask = (side == "sell")
            client_order_index = int(time.time() * 1000) % 1000000
            base_amount = self._scale_value(sz, base_multiplier)
            if base_amount <= 0:
                return {"code": "1", "msg": "Order size too small"}

            is_sl = sl_trigger_px is not None
            is_tp = tp_trigger_px is not None
            if not is_sl and not is_tp:
                return {"code": "1", "msg": "Missing trigger price"}

            trigger_px = sl_trigger_px if is_sl else tp_trigger_px
            trigger_price_int = self._scale_value(trigger_px, price_multiplier)
            guard_key = f"{inst_id}:{pos_side}:{side}:{'sl' if is_sl else 'tp'}:{trigger_px}:{sz}"
            last_guard = self._algo_guard.get(guard_key)
            if last_guard and (time.time() - last_guard) < self._algo_guard_ttl_s:
                return {
                    "code": "0",
                    "msg": "",
                    "data": [{
                        "algoId": str(client_order_index),
                        "sCode": "0",
                        "sMsg": "",
                    }]
                }

            # Avoid duplicating reduce-only protective orders.
            try:
                existing_orders = await self.get_open_orders(inst_id=inst_id)
            except Exception:
                existing_orders = []
            if existing_orders:
                try:
                    target_trigger = Decimal(str(trigger_px))
                except Exception:
                    target_trigger = None
                try:
                    target_sz = Decimal(str(sz))
                except Exception:
                    target_sz = None
                for order in existing_orders:
                    if not order.get("reduce_only"):
                        continue
                    if order.get("side") != side:
                        continue
                    if target_trigger is None or target_sz is None:
                        break
                    try:
                        order_trigger = Decimal(str(order.get("trigger_price")))
                    except Exception:
                        continue
                    try:
                        order_sz = Decimal(str(order.get("size") or order.get("sz") or "0"))
                    except Exception:
                        continue
                    if abs(order_trigger - target_trigger) <= Decimal("0.00000001") and abs(order_sz - target_sz) <= Decimal("0.00000001"):
                        existing_id = order.get("ordId") or order.get("clOrdId") or client_order_index
                        return {
                            "code": "0",
                            "msg": "",
                            "data": [{
                                "algoId": str(existing_id),
                                "sCode": "0",
                                "sMsg": "",
                            }]
                        }

            limit_price = None
            if is_sl:
                limit_price = sl_ord_px if sl_ord_px and sl_ord_px != "-1" else None
            if is_tp:
                limit_price = tp_ord_px if tp_ord_px and tp_ord_px != "-1" else None

            if limit_price is None:
                price_int = trigger_price_int
                if is_sl:
                    create_order, tx_response, error = await self._signer_client.create_sl_order(
                        market_index=market_id,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        trigger_price=trigger_price_int,
                        price=price_int,
                        is_ask=is_ask,
                        reduce_only=True,
                    )
                else:
                    create_order, tx_response, error = await self._signer_client.create_tp_order(
                        market_index=market_id,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        trigger_price=trigger_price_int,
                        price=price_int,
                        is_ask=is_ask,
                        reduce_only=True,
                    )
            else:
                price_int = self._scale_value(limit_price, price_multiplier)
                if is_sl:
                    create_order, tx_response, error = await self._signer_client.create_sl_limit_order(
                        market_index=market_id,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        trigger_price=trigger_price_int,
                        price=price_int,
                        is_ask=is_ask,
                        reduce_only=True,
                    )
                else:
                    create_order, tx_response, error = await self._signer_client.create_tp_limit_order(
                        market_index=market_id,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        trigger_price=trigger_price_int,
                        price=price_int,
                        is_ask=is_ask,
                        reduce_only=True,
                    )

            fallback_used = False
            if error is not None:
                fallback_used = True
            tx_code = getattr(tx_response, "code", None)
            tx_message = getattr(tx_response, "message", None)
            if tx_code not in (0, 200, None):
                fallback_used = True

            if fallback_used:
                try:
                    if is_sl:
                        order_type = (
                            self._signer_client.ORDER_TYPE_STOP_LOSS_LIMIT
                            if limit_price is not None
                            else self._signer_client.ORDER_TYPE_STOP_LOSS
                        )
                    else:
                        order_type = (
                            self._signer_client.ORDER_TYPE_TAKE_PROFIT_LIMIT
                            if limit_price is not None
                            else self._signer_client.ORDER_TYPE_TAKE_PROFIT
                        )
                    tif = self._signer_client.ORDER_TIME_IN_FORCE_IMMEDIATE_OR_CANCEL
                    create_order, tx_response, error = await self._signer_client.create_order(
                        market_index=market_id,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        price=price_int,
                        is_ask=is_ask,
                        order_type=order_type,
                        time_in_force=tif,
                        reduce_only=True,
                        trigger_price=trigger_price_int,
                    )
                except Exception as fallback_err:
                    return {"code": "1", "msg": f"fallback failed: {fallback_err}"}

                if error is not None:
                    return {"code": "1", "msg": str(error)}

                tx_code = getattr(tx_response, "code", None)
                tx_message = getattr(tx_response, "message", None)
                if tx_code not in (0, 200, None):
                    return {"code": "1", "msg": f"order rejected: code={tx_code} message={tx_message}"}

            store = self._get_okx_store()
            key = f"{inst_id}:{pos_side}"
            protect = store["protective_by_key"].setdefault(key, {"sl": [], "tp": []})
            if is_sl:
                protect["sl"] = [str(client_order_index)]
            else:
                protect["tp"].append(str(client_order_index))
            self._algo_guard[guard_key] = time.time()

            return {
                "code": "0",
                "msg": "",
                "data": [{
                    "algoId": str(client_order_index),
                    "sCode": "0",
                    "sMsg": "",
                }]
            }
        except Exception as e:
            return {"code": "1", "msg": str(e)}

    async def cancel_order(
        self,
        *,
        inst_id: str,
        ord_id: Optional[str] = None,
        cl_ord_id: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """取消订单"""
        if not self._trading_enabled or not self._signer_client:
            return {"code": "1", "msg": "Trading not enabled"}
        
        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        market_id = await self._get_market_id(symbol)
        
        if ord_id is None and order_id is not None:
            ord_id = order_id
        if ord_id is None and cl_ord_id:
            store = self._get_okx_store()
            ord_id = store.get("cl_to_order", {}).get(cl_ord_id)
        if market_id is None or not ord_id:
            return {"code": "1", "msg": "Invalid parameters"}
        
        try:
            result, tx_hash, error = await self._signer_client.cancel_order(
                market_index=market_id,
                order_index=int(ord_id)
            )
            
            if error is not None:
                return {"code": "1", "msg": str(error)}
            store = self._get_okx_store()
            store["order_meta"].pop(str(ord_id), None)
            store["order_to_cl"].pop(str(ord_id), None)
            if cl_ord_id:
                store["cl_to_order"].pop(cl_ord_id, None)
            return {"code": "0", "msg": ""}
            
        except Exception as e:
            return {"code": "1", "msg": str(e)}

    async def get_position(self, *, inst_id: str, pos_side: str) -> Optional[Dict[str, Any]]:
        """获取仓位"""
        if not self._account_api or self.account_index is None:
            return None
        
        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        market_id = await self._get_market_id(symbol)
        
        if market_id is None:
            return None
        
        try:
            resp = await self._account_api.account(by="index", value=str(int(self.account_index)))
            accounts = getattr(resp, "accounts", None) or []
            if not accounts:
                return None
            account = accounts[0]
            positions = getattr(account, "positions", None) or []

            for pos in positions:
                if getattr(pos, "market_id", None) != market_id:
                    continue

                try:
                    position_val = float(getattr(pos, "position", 0) or 0)
                except (TypeError, ValueError):
                    continue

                if position_val == 0:
                    continue

                sign = int(getattr(pos, "sign", 1) or 1)
                size = position_val * (1 if sign >= 0 else -1)
                is_long = size > 0
                if (is_long and pos_side != "long") or (not is_long and pos_side != "short"):
                    continue

                try:
                    avg_entry = float(getattr(pos, "avg_entry_price", 0) or 0)
                except (TypeError, ValueError):
                    avg_entry = 0.0

                return {
                    "instId": inst_id,
                    "posSide": pos_side,
                    "pos": str(abs(size)),
                    "avgPx": str(avg_entry),
                }
        except Exception as e:
            logger.error("Failed to get position: %s", str(e))
        
        return None

    async def get_order(self, *, inst_id: str, cl_ord_id: str) -> Optional[Dict[str, Any]]:
        """查询订单 (简化版)"""
        store = self._get_okx_store()
        order_id = store.get("cl_to_order", {}).get(cl_ord_id)
        meta = store.get("order_meta", {}).get(order_id or "")
        if not meta:
            return None

        state = "live"
        avg_px = meta.get("px")
        acc_fill_sz = "0"
        try:
            symbol = meta.get("symbol") or inst_id.replace("-USDT-SWAP", "").replace("-", "/")
            market_id = await self._get_market_id(symbol)
            if market_id is not None and self._order_api and self.account_index is not None:
                auth_token = None
                if self._signer_client:
                    auth_token, err = self._signer_client.create_auth_token_with_expiry()
                    if err is not None:
                        auth_token = None

                # Active orders
                resp = await self._order_api.account_active_orders(
                    account_index=int(self.account_index),
                    market_id=market_id,
                    authorization=auth_token,
                    auth=auth_token,
                )
                orders = getattr(resp, "orders", None) or []
                found = None
                for order in orders:
                    if getattr(order, "client_order_index", None) == int(order_id or -1):
                        found = order
                        break

                # Inactive orders (filled/canceled)
                if found is None:
                    resp = await self._order_api.account_inactive_orders(
                        account_index=int(self.account_index),
                        market_id=market_id,
                        authorization=auth_token,
                        auth=auth_token,
                    )
                    orders = getattr(resp, "orders", None) or []
                    for order in orders:
                        if getattr(order, "client_order_index", None) == int(order_id or -1):
                            found = order
                            break

                if found is not None:
                    state = (getattr(found, "status", "") or "live").lower()
                    filled_base = getattr(found, "filled_base_amount", None)
                    filled_quote = getattr(found, "filled_quote_amount", None)
                    if filled_base:
                        try:
                            acc_fill_sz = str(float(filled_base))
                        except Exception:
                            acc_fill_sz = filled_base
                    if filled_base and filled_quote:
                        try:
                            base = float(filled_base)
                            quote = float(filled_quote)
                            if base > 0:
                                avg_px = str(quote / base)
                        except Exception:
                            pass
        except Exception:
            pass

        return {
            "instId": inst_id,
            "clOrdId": cl_ord_id,
            "ordId": order_id,
            "state": state,
            "avgPx": avg_px,
            "accFillSz": acc_fill_sz,
            "sz": meta.get("sz"),
        }

    async def get_open_orders(self, *, inst_id: str) -> List[Dict[str, Any]]:
        """获取未成交订单"""
        if not self._order_api or self.account_index is None:
            return []
        
        symbol = inst_id.replace("-USDT-SWAP", "").replace("-", "/")
        market_id = await self._get_market_id(symbol)
        
        if market_id is None:
            return []
        
        try:
            auth_token = None
            if self._signer_client:
                auth_token, err = self._signer_client.create_auth_token_with_expiry()
                if err is not None:
                    logger.warning("⚠️ Lighter auth token error: %s", err)
                    auth_token = None

            resp = await self._order_api.account_active_orders(
                account_index=int(self.account_index),
                market_id=market_id,
                authorization=auth_token,
                auth=auth_token,
            )
            orders = getattr(resp, "orders", None) or []
            store = self._get_okx_store()

            result = []
            for order in orders:
                status = (getattr(order, "status", "") or "").lower()
                if status not in ["open", "pending", "in-progress"]:
                    continue

                raw_price = getattr(order, "price", 0) or 0
                raw_size = getattr(order, "remaining_base_amount", 0) or 0
                if not raw_size:
                    raw_size = getattr(order, "initial_base_amount", 0) or 0
                filled_base = getattr(order, "filled_base_amount", 0) or 0

                try:
                    price = float(raw_price)
                except (TypeError, ValueError):
                    price = 0.0
                try:
                    size = float(raw_size)
                except (TypeError, ValueError):
                    size = 0.0
                try:
                    filled_sz = float(filled_base)
                except (TypeError, ValueError):
                    filled_sz = 0.0

                side = getattr(order, "side", None)
                if not side:
                    side = "sell" if (getattr(order, "is_ask", False)) else "buy"

                order_id = getattr(order, "client_order_index", None)
                if order_id is None:
                    order_id = getattr(order, "order_index", "")
                cl_ord_id = store.get("order_to_cl", {}).get(str(order_id))

                result.append({
                    "ordId": str(order_id),
                    "clOrdId": cl_ord_id,
                    "price": price,
                    "size": size,
                    "side": side,
                    "state": status,
                    "accFillSz": str(filled_sz),
                    "reduce_only": getattr(order, "reduce_only", False),
                    "trigger_price": getattr(order, "trigger_price", None),
                    "type": getattr(order, "type", None),
                    "created_at": getattr(order, "created_at", None),
                })

            return result
        except Exception as exc:
            self._open_orders_error_ts = time.time()
            logger.warning("⚠️ Lighter get_open_orders failed: %s", exc)
            return []

    async def get_order_fills(self, *, inst_id: str, order_id: str) -> Optional[Tuple[float, float]]:
        """获取订单成交均价与数量"""
        if not self._order_api or self.account_index is None:
            return None
        store = self._get_okx_store()
        mapped_id = store.get("cl_to_order", {}).get(order_id)
        if mapped_id:
            order_id = mapped_id
        try:
            symbol = inst_id.replace("-SWAP", "").replace("-", "/")
            market_id = await self._get_market_id(symbol)
            if market_id is None:
                return None

            auth_token = None
            if self._signer_client:
                auth_token, err = self._signer_client.create_auth_token_with_expiry()
                if err is not None:
                    auth_token = None

            resp = await self._order_api.trades(
                sort_by="timestamp",
                limit=100,
                market_id=market_id,
                account_index=int(self.account_index),
                order_index=int(order_id),
                authorization=auth_token,
                auth=auth_token,
            )
            trades = getattr(resp, "trades", None) or []
            total_sz = 0.0
            total_val = 0.0
            for trade in trades:
                try:
                    ask_id = int(getattr(trade, "ask_client_id", -1) or -1)
                    bid_id = int(getattr(trade, "bid_client_id", -1) or -1)
                    if int(order_id) not in (ask_id, bid_id):
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
                return total_sz, (total_val / total_sz)
        except Exception:
            return None

    # ========== WebSocket Methods ==========

    def enable_websocket(self, auto_subscribe_account: bool = False) -> None:
        """启用 WebSocket (初始化，不自动连接)"""
        self._ws_enabled = True
        logger.info("✅ Lighter WebSocket enabled (lazy init)")

    async def subscribe_orderbook_stream(self, symbol: str, handler: Any) -> None:
        """订阅orderbook流 (async)"""
        market_id = await self._get_market_id(symbol)
        if market_id is not None:
            self._ws_orderbook_handlers[market_id] = handler
            logger.info(f"📖 Subscribed: {symbol} (market_id={market_id})")

    def subscribe_trades_stream(self, symbol: str, handler: Any) -> None:
        """订阅trades流 (目前Lighter SDK不支持独立的trades流)"""
        # Lighter WsClient only has orderbook updates
        logger.debug(f"💹 Trade stream not available for {symbol} (using orderbook)")

    async def start_websocket(self) -> None:
        """启动 WebSocket 连接"""
        if not self._ws_enabled:
            return
        
        if self._ws_client is not None:
            logger.warning("WebSocket already started")
            return
        
        # Prepare market IDs for subscription
        market_ids = list(self._ws_orderbook_handlers.keys())
        if not market_ids:
            logger.warning("No markets to subscribe")
            return
        
        # Determine host
        host = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        
        # Orderbook update handler
        def on_orderbook_update(message):
            logger.info(f"🔔 WS message received: type={type(message)} keys={list(message.keys()) if isinstance(message, dict) else 'N/A'}")
            try:
                market_id = message.get("market_id") if isinstance(message, dict) else getattr(message, "market_id", None)
                logger.info(f"🔔 WS market_id={market_id} handlers={list(self._ws_orderbook_handlers.keys())[:5]}")
                if market_id and market_id in self._ws_orderbook_handlers:
                    handler = self._ws_orderbook_handlers[market_id]
                    handler(message)
                else:
                    logger.debug(f"WS market_id={market_id} not in handlers")
            except Exception as e:
                logger.error(f"WebSocket orderbook handler error: {e}", exc_info=True)
        
        # Create WsClient
        self._ws_client = WsClient(
            host=host,
            order_book_ids=market_ids,
            on_order_book_update=on_orderbook_update,
        )
        
        # Run WebSocket in background task
        self._ws_task = asyncio.create_task(self._run_websocket())
        logger.info(f"🔌 Lighter WebSocket started ({len(market_ids)} markets)")

    async def _run_websocket(self) -> None:
        """运行 WebSocket (异步模式)"""
        if self._ws_client:
            try:
                logger.info("🔄 Starting WsClient.run_async()...")
                await self._ws_client.run_async()
                logger.info("🔄 WsClient.run_async() completed")
            except asyncio.CancelledError:
                logger.info("🔄 WsClient.run_async() cancelled")
                raise
            except Exception as e:
                logger.error(f"🔄 WsClient.run_async() error: {e}", exc_info=True)

    async def stop_websocket(self) -> None:
        """停止 WebSocket"""
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
            self._ws_task = None
        self._ws_client = None
        logger.info("👋 Lighter WebSocket stopped")
