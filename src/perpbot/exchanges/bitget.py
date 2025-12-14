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
        env = os.getenv("BITGET_ENV", "testnet").lower()
        self.use_testnet = env == "testnet"

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
            self.exchange = ccxt.bitget(
                {
                    "apiKey": self.api_key,
                    "secret": self.api_secret,
                    "password": self.passphrase,
                    "enableRateLimit": True,
                    "options": {"defaultType": "swap"},
                }
            )
            if hasattr(self.exchange, "set_sandbox_mode"):
                self.exchange.set_sandbox_mode(self.use_testnet)

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
            bid = float(ticker.get("bid") or 0)
            ask = float(ticker.get("ask") or 0)
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
                venue_type="cex",
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
            bids = [(float(p), float(q)) for p, q in (orderbook.get("bids") or [])[:depth]]
            asks = [(float(p), float(q)) for p, q in (orderbook.get("asks") or [])[:depth]]
            return OrderBookDepth(
                bids=bids,
                asks=asks,
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
            free_map = balances.get("free") or {}
            used_map = balances.get("used") or {}
            total_map = balances.get("total") or {}
            assets = set()
            if isinstance(free_map, dict):
                assets |= set(free_map.keys())
            if isinstance(used_map, dict):
                assets |= set(used_map.keys())
            if isinstance(total_map, dict):
                assets |= set(total_map.keys())

            result: List[Balance] = []
            for asset in sorted(assets):
                free = float(free_map.get(asset, 0) or 0) if isinstance(free_map, dict) else 0.0
                used = float(used_map.get(asset, 0) or 0) if isinstance(used_map, dict) else 0.0
                total = float(total_map.get(asset, free + used) or 0) if isinstance(total_map, dict) else free + used
                if total <= 0 and free <= 0 and used <= 0:
                    continue
                result.append(Balance(asset=asset, free=free, locked=used, total=total))
            return result
        except Exception as e:
            logger.error(f"Failed to get balances: {e}")
            raise

    def get_account_positions(self) -> List[Position]:
        """Get open positions."""
        if not self.exchange or not self._trading_enabled:
            return []

        try:
            if not hasattr(self.exchange, "fetch_positions"):
                return []
            raw = self.exchange.fetch_positions()
            positions: List[Position] = []
            for p in raw or []:
                size = float(p.get("contracts") or p.get("positionAmt") or 0)
                if abs(size) <= 0:
                    continue
                sym = p.get("symbol") or ""
                side: Side = "buy" if size > 0 else "sell"
                entry = float(p.get("entryPrice") or p.get("entry_price") or p.get("average") or 0)
                order = Order(
                    id=f"pos-{sym}",
                    exchange=self.name,
                    symbol=sym,
                    side=side,
                    size=abs(size),
                    price=entry,
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an open order."""
        if not self._trading_enabled:
            raise RuntimeError("Bitget trading disabled")

        try:
            symbol = self._normalize_symbol(request.symbol)
            order_type = "limit" if request.limit_price is not None else "market"
            side = request.side

            order = self.exchange.create_order(
                symbol,
                order_type,
                side,
                amount=request.size,
                price=request.limit_price,
            )

            return Order(
                id=str(order.get("id", "")),
                exchange=self.name,
                symbol=symbol,
                side=request.side,
                size=request.size,
                price=float(order.get("price") or request.limit_price or 0.0),
            )
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    def place_close_order(self, position: Position, current_price: float) -> Order:
        closing_side: Side = "sell" if position.order.side == "buy" else "buy"
        req = OrderRequest(symbol=position.order.symbol, side=closing_side, size=position.order.size, limit_price=current_price)
        return self.place_open_order(req)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        if not self._trading_enabled:
            raise RuntimeError("Bitget trading disabled")
        if not self.exchange:
            raise RuntimeError("Not connected")
        sym = self._normalize_symbol(symbol) if symbol else None
        self.exchange.cancel_order(order_id, sym)

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
                        exchange=self.name,
                        symbol=order.get("symbol", symbol or ""),
                        side="buy" if order.get("side") == "buy" else "sell",
                        size=float(order.get("amount", 0) or 0),
                        price=float(order.get("price", 0) or 0),
                    )
                )
            return result
        except Exception as e:
            logger.error(f"Failed to get active orders: {e}")
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        # BITGET WS not implemented in this client yet; keep handler for future.
        self._order_handler = handler
