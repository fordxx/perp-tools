"""BITGET perpetual futures client."""
from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote, Side

logger = logging.getLogger(__name__)


class BitgetClient(ExchangeClient):
    """BITGET perpetual futures client using REST API.

    ✅ Testnet Mode - No real funds at risk
    ✅ BITGET API via ccxt or custom HTTP client
    ✅ Market data, account info, and order management
    """

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "bitget"
        self.venue_type = "cex"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.exchange: Optional[object] = None  # Will be ccxt.bitget or custom client
        self._trading_enabled = False
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to BITGET and validate configuration."""
        load_dotenv()
        self.api_key = os.getenv("BITGET_API_KEY")
        self.api_secret = os.getenv("BITGET_API_SECRET")
        self.passphrase = os.getenv("BITGET_PASSPHRASE")

        # Try CCXT first
        try:
            import ccxt

            # 🔒 Safety: Disable trading if credentials missing
            if not all([self.api_key, self.api_secret, self.passphrase]):
                logger.warning("⚠️ BITGET trading DISABLED: credentials not found")
                self._trading_enabled = False
                self.exchange = ccxt.bitget()
                return

            # Create CCXT exchange instance
            self.exchange = ccxt.bitget({
                'apiKey': self.api_key,
                'secret': self.api_secret,
                'password': self.passphrase,
                'enableRateLimit': True,
                'sandbox': self.use_testnet,
                'options': {
                    'defaultType': 'swap',
                },
            })

            self._trading_enabled = True
            logger.info("✅ BITGET connected via CCXT (trading=%s)", self._trading_enabled)

        except ImportError:
            logger.warning("CCXT not available for BITGET - read-only mode only")
            if not self.api_key or not self.api_secret:
                logger.warning("BITGET credentials not configured")

    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to appropriate BITGET format."""
        return symbol if "/" in symbol else symbol.replace("USDT", "/USDT")

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Get current bid/ask prices."""
        if not self.exchange:
            raise RuntimeError("Not connected")

        symbol = self._normalize_symbol(symbol)
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return PriceQuote(
                symbol=symbol,
                bid=float(ticker.get("bid", 0)),
                ask=float(ticker.get("ask", 0)),
                mid=(float(ticker.get("bid", 0)) + float(ticker.get("ask", 0))) / 2,
                timestamp=ticker.get("timestamp"),
            )
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            raise

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Get order book with specified depth."""
        if not self.exchange:
            raise RuntimeError("Not connected")

        symbol = self._normalize_symbol(symbol)
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit=depth)
            return OrderBookDepth(
                symbol=symbol,
                bids=orderbook.get("bids", [])[:depth],
                asks=orderbook.get("asks", [])[:depth],
                timestamp=orderbook.get("timestamp"),
            )
        except Exception as e:
            logger.error(f"Failed to get orderbook for {symbol}: {e}")
            raise

    def get_account_balances(self) -> List[Balance]:
        """Get account balances."""
        if not self.exchange or not self._trading_enabled:
            return []

        try:
            balances = self.exchange.fetch_balance()
            result = []
            for currency, balance in balances.items():
                if currency not in ["free", "used", "total"]:
                    result.append(
                        Balance(
                            currency=currency,
                            free=float(balance.get("free", 0)),
                            used=float(balance.get("used", 0)),
                            total=float(balance.get("total", 0)),
                        )
                    )
            return result
        except Exception as e:
            logger.error(f"Failed to get balances: {e}")
            raise

    def get_account_positions(self) -> List[Position]:
        """Get open positions."""
        if not self.exchange or not self._trading_enabled:
            return []

        try:
            positions = []
            # Implement position fetching based on BITGET API
            # This is a placeholder
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an open order."""
        if not self._trading_enabled:
            logger.warning("Trading disabled - returning rejected order")
            return Order(id="rejected", status="rejected")

        try:
            symbol = self._normalize_symbol(request.symbol)
            order_type = "limit" if request.limit_price else "market"
            side = "buy" if request.side == Side.BUY else "sell"

            order = self.exchange.create_order(
                symbol,
                order_type,
                side,
                amount=request.quantity,
                price=request.limit_price,
            )

            return Order(
                id=str(order.get("id", "")),
                symbol=symbol,
                side=request.side,
                quantity=request.quantity,
                price=order.get("price"),
                status="open",
                timestamp=order.get("timestamp"),
            )
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return Order(id=f"error-{str(e)}", status="error")

    def place_close_order(self, request: OrderRequest) -> Order:
        """Close an existing position with an order."""
        return self.place_open_order(request)

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        if not self._trading_enabled:
            logger.warning("Trading disabled - cannot cancel order")
            return False

        try:
            symbol = self._normalize_symbol(symbol)
            self.exchange.cancel_order(order_id, symbol)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all active orders."""
        if not self.exchange or not self._trading_enabled:
            return []

        try:
            if symbol:
                symbol = self._normalize_symbol(symbol)
                orders = self.exchange.fetch_open_orders(symbol)
            else:
                orders = self.exchange.fetch_open_orders()

            result = []
            for order in orders:
                result.append(
                    Order(
                        id=str(order.get("id", "")),
                        symbol=order.get("symbol", symbol or ""),
                        side=Side.BUY if order.get("side") == "buy" else Side.SELL,
                        quantity=float(order.get("amount", 0)),
                        price=float(order.get("price", 0)),
                        status=order.get("status", ""),
                        timestamp=order.get("timestamp"),
                    )
                )
            return result
        except Exception as e:
            logger.error(f"Failed to get active orders: {e}")
            return []
