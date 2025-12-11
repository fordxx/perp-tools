from __future__ import annotations

import asyncio
import logging
import os
import threading
from decimal import Decimal
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class ParadexClient(ExchangeClient):
    """Paradex DEX client using official SDK + L2 private key.

    ✅ 使用 Paradex SDK (paradex-py)
    ✅ L2 私钥签名（Starknet）
    ✅ LIMIT 和 MARKET 订单
    ✅ 主网和测试网支持

    环境变量：
    - PARADEX_L2_PRIVATE_KEY: L2 私钥（必需）
    - PARADEX_ACCOUNT_ADDRESS: Starknet 账户地址（必需）
    - PARADEX_ENV: mainnet 或 testnet（可选，默认 testnet）
    """

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "paradex"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        # L2 credentials
        self.l2_private_key: Optional[str] = None
        self.account_address: Optional[str] = None

        # SDK client
        self.client = None  # Will be ParadexSubkey from SDK
        self._trading_enabled = False

        # WebSocket 管理
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_loop: Optional[asyncio.AbstractEventLoop] = None
        self._ws_connected = False

        # Handlers (WebSocket callbacks)
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to Paradex using SDK + L2 private key."""
        load_dotenv()

        self.l2_private_key = os.getenv("PARADEX_L2_PRIVATE_KEY")
        self.account_address = os.getenv("PARADEX_ACCOUNT_ADDRESS")

        # 🔒 Safety: Check credentials
        if not self.l2_private_key or not self.account_address:
            logger.warning("⚠️ Paradex trading DISABLED: PARADEX_L2_PRIVATE_KEY or PARADEX_ACCOUNT_ADDRESS missing")
            self._trading_enabled = False
            return

        try:
            # Import Paradex SDK (使用 ParadexSubkey 类 - 仅需 L2 凭证)
            from paradex_py import ParadexSubkey
            from paradex_py.environment import TESTNET, PROD

            # Select environment (使用官方环境常量)
            env = TESTNET if self.use_testnet else PROD

            # Initialize SDK with L2 private key (使用 ParadexSubkey)
            self.client = ParadexSubkey(
                env=env,
                l2_private_key=self.l2_private_key,
                l2_address=self.account_address,
            )

            self._trading_enabled = True
            logger.info("✅ Paradex SDK connected (testnet=%s, trading=%s, account=%s)",
                       self.use_testnet, self._trading_enabled, self.account_address[:10] + "...")

            # 启动 WebSocket 连接（后台线程）
            self._start_websocket_thread()

        except ImportError:
            logger.error("❌ Paradex SDK not installed. Run: pip install paradex-py")
            self._trading_enabled = False
        except Exception as e:
            logger.error("❌ Paradex SDK initialization failed: %s", e)
            self._trading_enabled = False

    def _start_websocket_thread(self) -> None:
        """在后台线程启动 WebSocket 连接"""
        if not self.client:
            logger.warning("⚠️ Cannot start WebSocket: client not initialized")
            return

        def run_async_loop():
            """后台线程的 asyncio 事件循环"""
            self._ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._ws_loop)
            try:
                self._ws_loop.run_until_complete(self._connect_websocket())
                self._ws_loop.run_forever()
            except Exception as e:
                logger.error("❌ WebSocket event loop error: %s", e)
            finally:
                self._ws_loop.close()

        self._ws_thread = threading.Thread(target=run_async_loop, daemon=True, name="ParadexWS")
        self._ws_thread.start()
        logger.info("🚀 Started WebSocket background thread")

    async def _connect_websocket(self) -> None:
        """异步连接 WebSocket 并订阅频道"""
        try:
            logger.info("🔌 Connecting to Paradex WebSocket...")
            await self.client.ws_client.connect()
            self._ws_connected = True
            logger.info("✅ Paradex WebSocket connected")

            # 订阅频道
            await self._subscribe_channels()

        except Exception as e:
            logger.error("❌ WebSocket connection failed: %s", e)
            self._ws_connected = False

    async def _subscribe_channels(self) -> None:
        """订阅 WebSocket 频道（ORDERS 和 POSITIONS）"""
        from paradex_py.api.ws_client import ParadexWebsocketChannel

        try:
            # 订阅订单更新
            if self._order_handler:
                await self.client.ws_client.subscribe(
                    ParadexWebsocketChannel.ORDERS,
                    callback=self._on_order_update,
                    params={"market": "ALL"}
                )
                logger.info("📡 Subscribed to ORDERS channel")

            # 订阅持仓更新
            if self._position_handler:
                await self.client.ws_client.subscribe(
                    ParadexWebsocketChannel.POSITIONS,
                    callback=self._on_position_update,
                )
                logger.info("📡 Subscribed to POSITIONS channel")

        except Exception as e:
            logger.error("❌ Channel subscription failed: %s", e)

    async def _on_order_update(self, channel, message: dict) -> None:
        """处理订单更新消息"""
        try:
            if self._order_handler:
                # 调用用户注册的 handler
                self._order_handler(message)
        except Exception as e:
            logger.error("❌ Order handler error: %s", e)

    async def _on_position_update(self, channel, message: dict) -> None:
        """处理持仓更新消息"""
        try:
            if self._position_handler:
                # 调用用户注册的 handler
                self._position_handler(message)
        except Exception as e:
            logger.error("❌ Position handler error: %s", e)

    def disconnect(self) -> None:
        """断开 WebSocket 连接并清理资源"""
        if self._ws_connected and self._ws_loop:
            try:
                # 在事件循环中关闭 WebSocket
                future = asyncio.run_coroutine_threadsafe(
                    self.client.ws_client.close(),
                    self._ws_loop
                )
                future.result(timeout=5.0)  # 等待最多 5 秒
                
                self._ws_loop.stop()
                self._ws_connected = False
                logger.info("🔌 Paradex WebSocket disconnected")
            except Exception as e:
                logger.error("❌ WebSocket disconnect error: %s", e)


    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC-USD-PERP (Paradex format)."""
        if "PERP" in symbol or "-" in symbol:
            return symbol
        # BTC/USDT -> BTC-USD-PERP
        base = symbol.split("/")[0]
        return f"{base}-USD-PERP"

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Paradex using SDK."""
        if not self.client:
            raise RuntimeError("Client not connected")

        market = self._normalize_symbol(symbol)

        try:
            # Use SDK to get BBO (Best Bid/Offer)
            bbo = self.client.api_client.fetch_bbo(market)

            # Paradex SDK returns: {'bid': '...', 'ask': '...', ...}
            bid = float(bbo.get("bid", 0))
            ask = float(bbo.get("ask", 0))

            if bid == 0 or ask == 0:
                logger.warning("⚠️ Paradex %s: Invalid bid/ask (bid=%.2f, ask=%.2f)",
                             symbol, bid, ask)

            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="dex",
            )

        except Exception as e:
            logger.error("❌ Paradex price fetch failed for %s: %s", symbol, e)
            raise RuntimeError(f"Paradex price fetch failed for {symbol}: {e}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book from Paradex using SDK."""
        if not self.client:
            raise RuntimeError("Client not connected")

        market = self._normalize_symbol(symbol)

        try:
            # Use SDK to get orderbook
            orderbook = self.client.api_client.fetch_orderbook(market)

            # Paradex SDK format: {"bids": [[price, size], ...], "asks": [[price, size], ...]}
            bids = [(float(p), float(s)) for p, s in orderbook.get("bids", [])]
            asks = [(float(p), float(s)) for p, s in orderbook.get("asks", [])]

            return OrderBookDepth(bids=bids, asks=asks)

        except Exception as e:
            logger.error("❌ Paradex orderbook fetch failed: %s", e)
            raise RuntimeError(f"Paradex orderbook fetch failed: {e}")

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order on Paradex using SDK (LIMIT or MARKET).

        ✅ 支持 LIMIT 和 MARKET 订单
        ✅ 自动 L2 签名

        Args:
            request: OrderRequest with symbol, side, size, limit_price (optional)

        Returns:
            Order object with order ID
        """
        # Safety check
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

        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            # Import Paradex SDK Order classes
            from paradex_py.common.order import Order as ParadexOrder, OrderType, OrderSide

            market = self._normalize_symbol(request.symbol)

            # Determine order type and side (using SDK enums)
            is_limit = request.limit_price is not None
            order_type = OrderType.Limit if is_limit else OrderType.Market
            order_side = OrderSide.Buy if request.side.lower() == "buy" else OrderSide.Sell

            # Round price to tick_size (0.01 for Paradex)
            if is_limit:
                # Round to 2 decimal places (tick_size = 0.01)
                price_decimal = Decimal(str(request.limit_price)).quantize(Decimal("0.01"))
            else:
                price_decimal = Decimal("0")

            # Create Paradex Order object
            paradex_order = ParadexOrder(
                market=market,
                order_type=order_type,
                order_side=order_side,
                size=Decimal(str(request.size)),
                limit_price=price_decimal,
            )

            # Place order using SDK (SDK handles L2 signing automatically)
            order_response = self.client.api_client.submit_order(paradex_order)

            # Extract order info
            order_id = order_response.get("id", "unknown")
            filled_price = float(order_response.get("price", request.limit_price or 0))

            logger.info("✅ Paradex %s order placed: %s %.4f %s @ %.2f - ID: %s",
                       order_type.value, request.side.upper(), request.size,
                       request.symbol, filled_price, order_id)

            return Order(
                id=str(order_id),
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=filled_price,
            )

        except Exception as e:
            logger.exception("❌ Paradex order failed: %s", e)
            return Order(
                id=f"error-{int(os.urandom(4).hex(), 16)}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close a position with a MARKET order using SDK.

        Args:
            position: Position to close
            current_price: Current market price (for reference)

        Returns:
            Order object
        """
        # Safety check
        if not self._trading_enabled:
            logger.warning("❌ Close order REJECTED: Trading disabled")
            return Order(
                id="rejected-close",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

        # Create reverse MARKET order
        closing_side = "sell" if position.order.side == "buy" else "buy"

        close_request = OrderRequest(
            symbol=position.order.symbol,
            side=closing_side,
            size=position.order.size,
            limit_price=None,  # MARKET order
        )

        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an order on Paradex using SDK.

        Args:
            order_id: Order ID to cancel
            symbol: Optional symbol (not used by Paradex SDK)
        """
        if not self._trading_enabled:
            logger.warning("❌ Cancel REJECTED: Trading disabled")
            return

        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            # Use SDK to cancel order
            self.client.api_client.cancel_order(order_id)
            logger.info("✅ Paradex order cancelled: %s", order_id)

        except Exception as e:
            logger.error("❌ Paradex cancel failed for %s: %s", order_id, e)
            raise RuntimeError(f"Cancel failed: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders on Paradex using SDK.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of Order objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Active orders query skipped: Trading disabled")
            return []

        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            # Use SDK to get orders
            filters = {}
            if symbol:
                filters["market"] = self._normalize_symbol(symbol)

            orders_response = self.client.api_client.fetch_orders(**filters)

            orders: List[Order] = []
            for order_data in orders_response.get("results", []):
                # Only include open orders
                if order_data.get("status") != "OPEN":
                    continue

                market = order_data.get("market", "")
                # Convert BTC-USD-PERP back to BTC/USDT
                symbol_clean = market.replace("-USD-PERP", "/USDT")

                orders.append(Order(
                    id=str(order_data.get("id")),
                    exchange=self.name,
                    symbol=symbol_clean,
                    side=order_data.get("side", "").lower(),
                    size=float(order_data.get("size", 0)),
                    price=float(order_data.get("price", 0)),
                ))

            if orders:
                logger.info("📊 Paradex: %d active orders", len(orders))

            return orders

        except Exception as e:
            logger.error("❌ Paradex active orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get all positions on Paradex using SDK.

        Returns:
            List of Position objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Positions query skipped: Trading disabled")
            return []

        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            # Use SDK to get positions
            positions_response = self.client.api_client.fetch_positions()

            positions: List[Position] = []
            for pos_data in positions_response.get("results", []):
                size = float(pos_data.get("size", 0))
                if size == 0:
                    continue

                # Determine side
                side = "buy" if size > 0 else "sell"
                size = abs(size)

                market = pos_data.get("market", "")
                symbol = market.replace("-USD-PERP", "/USDT")

                entry_price = float(pos_data.get("avg_entry_price", 0))

                order = Order(
                    id=f"pos-{market}",
                    exchange=self.name,
                    symbol=symbol,
                    side=side,
                    size=size,
                    price=entry_price,
                )

                position = Position(
                    id=order.id,
                    order=order,
                    target_profit_pct=0.0,
                )

                positions.append(position)

            if positions:
                logger.info("📊 Paradex: %d open positions", len(positions))

            return positions

        except Exception as e:
            logger.error("❌ Paradex positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get account balances on Paradex using SDK.

        Returns:
            List of Balance objects
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Balances query skipped: Trading disabled")
            return []

        if not self.client:
            raise RuntimeError("Client not connected")

        try:
            # Use SDK to get account summary
            summary = self.client.api_client.fetch_account_summary()

            balances: List[Balance] = []

            # Paradex AccountSummary object attributes
            total_equity = float(summary.account_value)
            available = float(summary.free_collateral)
            locked = total_equity - available

            if total_equity > 0:
                balances.append(Balance(
                    asset="USDC",
                    free=available,
                    locked=locked,
                    total=total_equity,
                ))

            if balances:
                logger.info("💰 Paradex balance: %.2f USDC (available: %.2f)",
                           total_equity, available)

            return balances

        except Exception as e:
            logger.error("❌ Paradex balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """设置订单更新回调并订阅 ORDERS 频道"""
        self._order_handler = handler
        logger.info("✅ Registered Paradex order update handler")

        # 如果 WebSocket 已连接，立即订阅
        if self._ws_connected and self._ws_loop:
            import asyncio
            from paradex_py.api.ws_client import ParadexWebsocketChannel
            
            asyncio.run_coroutine_threadsafe(
                self.client.ws_client.subscribe(
                    ParadexWebsocketChannel.ORDERS,
                    callback=self._on_order_update,
                    params={"market": "ALL"}
                ),
                self._ws_loop
            )
            logger.info("📡 Dynamically subscribed to ORDERS channel")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """设置持仓更新回调并订阅 POSITIONS 频道"""
        self._position_handler = handler
        logger.info("✅ Registered Paradex position update handler")

        # 如果 WebSocket 已连接，立即订阅
        if self._ws_connected and self._ws_loop:
            import asyncio
            from paradex_py.api.ws_client import ParadexWebsocketChannel
            
            asyncio.run_coroutine_threadsafe(
                self.client.ws_client.subscribe(
                    ParadexWebsocketChannel.POSITIONS,
                    callback=self._on_position_update,
                ),
                self._ws_loop
            )
            logger.info("📡 Dynamically subscribed to POSITIONS channel")
