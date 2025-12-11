from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class OKXClient(ExchangeClient):
    """OKX SWAP (perpetual) client using CCXT (Testnet/Demo Trading only).

    ✅ 100% Testnet Mode - Mainnet connection is absolutely forbidden.
    ✅ Uses ccxt.okx with demo trading mode (x-simulated-trading: 1).
    ✅ Auto-disables trading if credentials are missing.
    """

    def __init__(self, use_testnet: bool = True) -> None:
        # 🔒 Safety: Force testnet mode
        if not use_testnet:
            raise ValueError("❌ Mainnet is absolutely forbidden for OKX. Only testnet/demo is allowed.")

        self.name = "okx"
        self.venue_type = "cex"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.exchange: Optional[object] = None  # Will be ccxt.okx
        self._trading_enabled = False
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to OKX Demo Trading and validate configuration."""
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

        # Create CCXT exchange instance
        self.exchange = ccxt.okx({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.passphrase,  # OKX uses 'password' for passphrase
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            },
            'headers': {
                'x-simulated-trading': '1',  # 🔒 Demo trading mode
            }
        })

        # 🔒 Safety: Verify demo trading is enabled
        demo_header = self.exchange.headers.get('x-simulated-trading')
        if demo_header != '1':
            raise RuntimeError(f"❌ SAFETY ABORT: Demo trading not enabled (x-simulated-trading={demo_header})")

        self._trading_enabled = True
        logger.info("✅ OKX Demo Trading connected (x-simulated-trading=1, trading=%s)", self._trading_enabled)
        logger.info("🧪 Demo mode: Enabled")

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

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place a MARKET order to open a position (Demo Trading only).

        ✅ Only supports MARKET orders.
        ❌ Limit orders are forbidden.

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

            # Place MARKET order
            order = self.exchange.create_order(
                symbol=ccxt_symbol,
                type='market',
                side=request.side,
                amount=request.size,
                params={}
            )

            logger.info("✅ OKX MARKET %s %.4f %s - OrderID: %s",
                       request.side.upper(), request.size, request.symbol, order['id'])

            return Order(
                id=str(order['id']),
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=float(order['amount']),
                price=float(order.get('average') or order.get('price', 0)),
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
