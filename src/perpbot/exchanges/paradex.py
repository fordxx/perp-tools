from __future__ import annotations

import logging
import os
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
        self.client = None  # Will be ParadexClient from SDK
        self._trading_enabled = False

        # Handlers (WebSocket 后置)
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

            # Select environment (使用字符串，不是枚举)
            env = 'testnet' if self.use_testnet else 'prod'

            # Initialize SDK with L2 private key (使用 ParadexSubkey)
            self.client = ParadexSubkey(
                env=env,
                l2_private_key=self.l2_private_key,
                l2_address=self.account_address,
            )

            self._trading_enabled = True
            logger.info("✅ Paradex SDK connected (testnet=%s, trading=%s, account=%s)",
                       self.use_testnet, self._trading_enabled, self.account_address[:10] + "...")

        except ImportError:
            logger.error("❌ Paradex SDK not installed. Run: pip install paradex-py")
            self._trading_enabled = False
        except Exception as e:
            logger.error("❌ Paradex SDK initialization failed: %s", e)
            self._trading_enabled = False

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
        """Setup order update handler (WebSocket 后置)."""
        self._order_handler = handler
        logger.info("Registered Paradex order update handler (WebSocket not active)")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup position update handler (WebSocket 后置)."""
        self._position_handler = handler
        logger.info("Registered Paradex position update handler (WebSocket not active)")
