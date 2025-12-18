from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class OKXClient(ExchangeClient):
    """OKX SWAP (perpetual) client using CCXT.

    ⚠️ Supports both Demo Trading and Mainnet (use with caution).
    ✅ Demo mode uses ccxt.okx with demo trading mode (x-simulated-trading: 1).
    ✅ Mainnet mode for small position testing (real funds).
    ✅ Auto-disables trading if credentials are missing.
    """

    def __init__(self, use_testnet: bool = True, allow_mainnet: bool = False) -> None:
        # 🔒 Safety: Require explicit mainnet confirmation
        if not use_testnet and not allow_mainnet:
            raise ValueError(
                "❌ Mainnet requires explicit confirmation. "
                "Set allow_mainnet=True to enable real money trading."
            )

        self.name = "okx"
        self.venue_type = "cex"
        self.use_testnet = use_testnet
        self.allow_mainnet = allow_mainnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.exchange: Optional[object] = None  # Will be ccxt.okx
        self._trading_enabled = False
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to OKX (Demo Trading or Mainnet) and validate configuration."""
        import ccxt

        load_dotenv()
        self.api_key = os.getenv("OKX_API_KEY")
        self.api_secret = os.getenv("OKX_API_SECRET")
        self.passphrase = os.getenv("OKX_PASSPHRASE")

        # 🔒 Safety: Disable trading if credentials missing
        if not self.api_key or not self.api_secret or not self.passphrase:
            logger.warning("⚠️ OKX trading DISABLED: OKX_API_KEY, OKX_API_SECRET or OKX_PASSPHRASE not found")
            self._trading_enabled = False
            # Still create exchange for price data
            self.exchange = ccxt.okx()
            return

        # Build config based on testnet/mainnet
        config = {
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.passphrase,  # OKX uses 'password' for passphrase
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            },
        }

        # Add Demo Trading header if testnet mode
        if self.use_testnet:
            config['headers'] = {'x-simulated-trading': '1'}
            logger.info("🧪 Connecting to OKX Demo Trading (x-simulated-trading=1)")
        else:
            logger.warning("⚠️ ⚠️ ⚠️ MAINNET MODE - REAL MONEY TRADING ⚠️ ⚠️ ⚠️")

        # Create CCXT exchange instance
        self.exchange = ccxt.okx(config)

        # 🔒 Safety: Verify mode matches expectation
        demo_header = self.exchange.headers.get('x-simulated-trading')
        if self.use_testnet and demo_header != '1':
            raise RuntimeError(f"❌ SAFETY ABORT: Demo trading not enabled (x-simulated-trading={demo_header})")

        if not self.use_testnet and demo_header == '1':
            raise RuntimeError(f"❌ SAFETY ABORT: Mainnet expected but demo header found")

        self._trading_enabled = True

        if self.use_testnet:
            logger.info("✅ OKX Demo Trading connected (trading=%s)", self._trading_enabled)
        else:
            logger.warning("✅ OKX MAINNET connected (trading=%s) - REAL FUNDS!", self._trading_enabled)

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC/USDT:USDT (CCXT swap format)."""
        if "/" not in symbol:
            return symbol
        if ":USDT" in symbol:
            return symbol
        # BTC/USDT -> BTC/USDT:USDT (swap perpetual)
        base, quote = symbol.split("/")
        return f"{base}/{quote}:{quote}"

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from OKX Demo Trading.

        二层兜底机制：
        1. Demo Trading fetch_ticker 的 bid/ask
        2. 主网 REST API 直接获取 (https://www.okx.com/api/v5/market/ticker)

        严禁返回 bid=0 或 ask=0
        """
        if not self.exchange:
            raise RuntimeError("Client not connected")

        ccxt_symbol = self._normalize_symbol(symbol)

        # 第一层：尝试 Demo Trading fetch_ticker
        ticker = self.exchange.fetch_ticker(ccxt_symbol)

        bid = ticker.get('bid')
        ask = ticker.get('ask')

        # 检查 bid/ask 是否有效
        bid_valid = bid is not None and bid > 0
        ask_valid = ask is not None and ask > 0

        if bid_valid and ask_valid:
            # 第一层成功
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=float(bid),
                ask=float(ask),
                venue_type="cex",
            )

        # 第二层：直接请求主网 REST API
        logger.warning("⚠️ OKX Demo Trading %s: bid/ask invalid, fetching mainnet REST API", symbol)

        # 转换 symbol: BTC/USDT -> BTC-USDT-SWAP
        rest_symbol = symbol.replace("/", "-").upper() + "-SWAP"

        try:
            import httpx

            url = "https://www.okx.com/api/v5/market/ticker"
            response = httpx.get(url, params={"instId": rest_symbol}, timeout=5)
            response.raise_for_status()

            data = response.json()

            # OKX API 返回格式: {"code": "0", "data": [{"bidPx": "...", "askPx": "..."}]}
            if data.get('code') == '0' and data.get('data'):
                ticker_data = data['data'][0]

                bid = float(ticker_data.get('bidPx'))
                ask = float(ticker_data.get('askPx'))

                # 严格验证
                if bid > 0 and ask > 0:
                    logger.info("✅ OKX %s: using mainnet REST API bid=%.2f ask=%.2f",
                               symbol, bid, ask)
                    return PriceQuote(
                        exchange=self.name,
                        symbol=symbol,
                        bid=bid,
                        ask=ask,
                        venue_type="cex",
                    )
                else:
                    logger.error("❌ OKX %s: mainnet REST API returned invalid prices bid=%.2f ask=%.2f",
                               symbol, bid, ask)
            else:
                logger.error("❌ OKX %s: mainnet REST API returned error code: %s",
                           symbol, data.get('code'))

        except Exception as e:
            logger.error("❌ OKX %s: mainnet REST API failed: %s", symbol, e)

        # 所有兜底全部失败
        raise RuntimeError(f"🚨 OKX PRICE REST API FAILED for {symbol}")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book depth from OKX."""
        if not self.exchange:
            raise RuntimeError("Client not connected")

        ccxt_symbol = self._normalize_symbol(symbol)
        book = self.exchange.fetch_order_book(ccxt_symbol, limit=depth)

        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q in book.get('bids', [])],
            asks=[(float(p), float(q)) for p, q in book.get('asks', [])],
        )

    def place_open_order(self, request: OrderRequest, hedge_mode: bool = True, extra_params: Optional[dict] = None) -> Order:
        """Place a MARKET order to open a position (Demo Trading only).

        ✅ Only supports MARKET orders.
        ❌ Limit orders are forbidden.

        Args:
            request: Order request with symbol, side, size
            hedge_mode: Enable hedge mode (dual position) - requires OKX account setting
            extra_params: Additional CCXT params (e.g., for stop-loss)

        Returns:
            Order object if successful, Order with id="rejected*" if disabled.
        """
        # 🔒 Safety: Check if trading is enabled
        if not self._trading_enabled:
            logger.warning("❌ Order REJECTED: Trading disabled (missing credentials)")
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

        # 🔒 Safety: Only allow MARKET orders
        if request.limit_price is not None:
            logger.error("❌ Order REJECTED: Limit orders are forbidden (use MARKET only)")
            return Order(
                id="rejected-limit",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

        if not self.exchange:
            raise RuntimeError("Client not connected")

        try:
            ccxt_symbol = self._normalize_symbol(request.symbol)

            # Build params for hedge mode
            params = extra_params.copy() if extra_params else {}
            if hedge_mode:
                # OKX hedge mode: tdMode=cross, posSide=long/short
                params["tdMode"] = "cross"
                params["posSide"] = "long" if request.side == "buy" else "short"
                logger.info("🔄 OKX hedge mode: tdMode=cross posSide=%s", params["posSide"])

            # Place MARKET order
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=request.side,
                amount=request.size,
                params=params
            )

            logger.info("✅ OKX MARKET %s %.4f %s - OrderID: %s (hedge=%s)",
                       request.side.upper(), request.size, request.symbol, order['id'], hedge_mode)

            # Parse order response safely
            order_size = float(order.get('amount') or order.get('filled') or request.size)
            order_price = float(order.get('average') or order.get('price') or 0)

            # If price is 0, try to fetch order details for actual fill price
            if order_price == 0:
                try:
                    logger.debug("Fetching order details for accurate fill price...")
                    order_detail = self.exchange.fetch_order(order['id'], symbol=ccxt_symbol)
                    order_price = float(order_detail.get('average') or order_detail.get('price') or 0)
                    order_size = float(order_detail.get('filled') or order_detail.get('amount') or order_size)
                    logger.info("📊 Fetched fill price: %.2f (filled: %.4f)", order_price, order_size)
                except Exception as fetch_err:
                    logger.warning("⚠️ Could not fetch order details: %s", fetch_err)

            # Log raw order for debugging
            logger.debug("OKX order response: %s", order)

            return Order(
                id=str(order['id']),
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=order_size,
                price=order_price,
            )

        except Exception as e:
            logger.exception("❌ OKX order failed: %s", e)
            return Order(
                id=f"error-{int(os.urandom(4).hex(), 16)}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=0.0,
            )

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Place a MARKET order to close a position with reduceOnly=True (Demo Trading only).

        ✅ Only supports MARKET orders with reduceOnly.
        ❌ Limit orders are forbidden.

        Returns:
            Order object if successful, Order with id="rejected*" if disabled.
        """
        # 🔒 Safety: Check if trading is enabled
        if not self._trading_enabled:
            logger.warning("❌ Close order REJECTED: Trading disabled (missing credentials)")
            return Order(
                id="rejected-close",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

        if not self.exchange:
            raise RuntimeError("Client not connected")

        try:
            ccxt_symbol = self._normalize_symbol(position.order.symbol)
            closing_side = "sell" if position.order.side == "buy" else "buy"

            # Place MARKET order with reduceOnly=True
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=closing_side,
                amount=position.order.size,
                params={'reduceOnly': True}
            )

            logger.info("✅ OKX CLOSE %s %.4f %s (reduceOnly) - OrderID: %s",
                       closing_side.upper(), position.order.size, position.order.symbol, order['id'])

            return Order(
                id=str(order['id']),
                exchange=self.name,
                symbol=position.order.symbol,
                side=closing_side,
                size=float(order['amount']),
                price=float(order.get('average') or order.get('price', current_price)),
            )

        except Exception as e:
            logger.exception("❌ OKX close order failed: %s", e)
            return Order(
                id=f"error-close-{int(os.urandom(4).hex(), 16)}",
                exchange=self.name,
                symbol=position.order.symbol,
                side="sell" if position.order.side == "buy" else "buy",
                size=position.order.size,
                price=0.0,
            )

    def place_close_order_partial(
        self,
        symbol: str,
        side: str,
        size: float,
        hedge_mode: bool = True
    ) -> Order:
        """分批平仓：关闭指定数量的持仓

        Args:
            symbol: 交易对（如 SOL/USDT）
            side: 平仓方向（buy 平空仓，sell 平多仓）
            size: 平仓数量
            hedge_mode: 双向持仓模式

        Returns:
            Order object
        """
        if not self._trading_enabled:
            logger.warning("❌ Partial close REJECTED: Trading disabled")
            return Order(
                id="rejected-partial-close",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

        if not self.exchange:
            raise RuntimeError("Client not connected")

        try:
            ccxt_symbol = self._normalize_symbol(symbol)

            # Build params for hedge mode + reduceOnly
            params = {"reduceOnly": True}
            if hedge_mode:
                params["tdMode"] = "cross"
                # 平仓方向：sell 平多仓（posSide=long），buy 平空仓（posSide=short）
                params["posSide"] = "long" if side == "sell" else "short"

            logger.info(
                "🔄 OKX 分批平仓: symbol=%s side=%s size=%.4f hedge=%s posSide=%s",
                symbol, side, size, hedge_mode, params.get("posSide")
            )

            # Place MARKET order
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=side,
                amount=size,
                params=params
            )

            # Parse response safely
            order_size = float(order.get('amount') or order.get('filled') or size)
            order_price = float(order.get('average') or order.get('price') or 0)

            # Fetch order detail if price is 0
            if order_price == 0:
                try:
                    order_detail = self.exchange.fetch_order(order['id'], symbol=ccxt_symbol)
                    order_price = float(order_detail.get('average') or order_detail.get('price') or 0)
                    order_size = float(order_detail.get('filled') or order_detail.get('amount') or order_size)
                except Exception:
                    pass

            logger.info(
                "✅ OKX 分批平仓成功: order_id=%s symbol=%s side=%s size=%.4f price=%.2f",
                order['id'], symbol, side, order_size, order_price
            )

            return Order(
                id=str(order['id']),
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=order_size,
                price=order_price,
            )

        except Exception as e:
            logger.exception("❌ OKX 分批平仓失败: symbol=%s size=%.4f error=%s", symbol, size, e)
            return Order(
                id=f"error-partial-close-{int(os.urandom(4).hex(), 16)}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

    def get_account_positions(self) -> List[Position]:
        """Fetch real positions from OKX Demo Trading.

        Returns:
            List of Position objects with real Demo Trading data.
        """
        if not self._trading_enabled:
            logger.warning("⚠️ Positions query skipped: Trading disabled")
            return []

        if not self.exchange:
            raise RuntimeError("Client not connected")

        try:
            # Fetch all positions
            positions_data = self.exchange.fetch_positions()

            positions: List[Position] = []
            for pos in positions_data:
                contracts = float(pos.get('contracts', 0))
                if contracts == 0:
                    continue

                # Determine side from contracts (positive = long, negative = short)
                side = "buy" if contracts > 0 else "sell"
                size = abs(contracts)

                symbol = pos['symbol']
                # Convert BTC/USDT:USDT back to BTC/USDT
                if ":USDT" in symbol:
                    symbol = symbol.replace(":USDT", "")

                entry_price = float(pos.get('entryPrice', 0))

                # Create Order object for Position
                order = Order(
                    id=f"pos-{symbol.replace('/', '')}",
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
                logger.info("📊 OKX positions: %d open", len(positions))

            return positions

        except Exception as e:
            logger.exception("❌ Failed to fetch OKX positions: %s", e)
            return []

    def place_stop_loss_order(
        self,
        symbol: str,
        side: str,
        size: float,
        stop_price: float,
        hedge_mode: bool = True,
    ) -> Order:
        """Place a stop-loss order (conditional order) on OKX.

        Args:
            symbol: Symbol in canonical format (e.g., "BTC/USDT")
            side: Order side ("buy" or "sell")
            size: Order size
            stop_price: Stop-loss trigger price
            hedge_mode: Enable hedge mode (dual position)

        Returns:
            Order object with algo order ID
        """
        if not self._trading_enabled:
            logger.warning("❌ Stop-loss REJECTED: Trading disabled")
            return Order(
                id="rejected-sl",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=stop_price,
            )

        if not self.exchange:
            raise RuntimeError("Client not connected")

        try:
            ccxt_symbol = self._normalize_symbol(symbol)

            # OKX algo order params
            # For stop-market orders, orderPx must be -1 (market price execution)
            params = {
                "slTriggerPx": str(stop_price),  # Stop-loss trigger price
                "slOrdPx": "-1",  # -1 = market price
                "reduceOnly": True,
                "ordType": "conditional",  # Conditional order
            }
            if hedge_mode:
                params["tdMode"] = "cross"
                # For stop-loss, posSide is opposite of entry
                # If we're placing a sell stop, we're closing a long position
                params["posSide"] = "short" if side == "buy" else "long"

            logger.info(
                "🛑 Placing OKX stop-loss: symbol=%s side=%s size=%s stop_price=%.4f hedge=%s posSide=%s",
                symbol, side, size, stop_price, hedge_mode, params.get("posSide")
            )

            # Use CCXT create_order with conditional order params
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type="market",  # Order type is market
                side=side,
                amount=size,
                price=None,  # No price for market order
                params=params
            )

            logger.info("✅ OKX stop-loss placed: order_id=%s symbol=%s side=%s stop=%.4f",
                       order.get('id'), symbol, side, stop_price)

            return Order(
                id=str(order.get('id', 'sl-unknown')),
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=stop_price,
            )

        except Exception as e:
            logger.exception("❌ OKX stop-loss failed: %s", e)
            return Order(
                id=f"error-sl-{int(os.urandom(4).hex(), 16)}",
                exchange=self.name,
                symbol=symbol,
                side=side,
                size=size,
                price=0.0,
            )

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an order (not implemented for this phase)."""
        raise NotImplementedError("Order cancellation not required for MARKET-only phase")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders (not implemented for this phase)."""
        raise NotImplementedError("Active orders query not required for MARKET-only phase")

    def get_account_balances(self) -> List[Balance]:
        """Get account balances (not implemented for this phase)."""
        raise NotImplementedError("Balance query not required for MARKET-only phase")

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup order update handler (not implemented for this phase)."""
        self._order_handler = handler
        logger.info("Registered OKX order update handler (WebSocket not active)")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup position update handler (not implemented for this phase)."""
        self._position_handler = handler
        logger.info("Registered OKX position update handler (WebSocket not active)")
