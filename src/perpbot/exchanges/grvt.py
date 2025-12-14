"""GRVT Exchange DEX client.

GRVT (Gravity Markets) is a hybrid derivatives exchange on ZK-rollup.
API Documentation: https://api-docs.grvt.io/
SDK: pip install grvt-pysdk

Environment Variables:
- GRVT_API_KEY: API key
- GRVT_PRIVATE_KEY: Private key for EIP-712 signing
- GRVT_TRADING_ACCOUNT_ID: Trading account ID
- GRVT_ENV: mainnet or testnet (default: mainnet)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote
from perpbot.utils.retry import RetryConfig, retry_call

logger = logging.getLogger(__name__)

_GRVT_ALLOWED_BOOK_DEPTHS = (10, 50, 100)


class GRVTClient(ExchangeClient):
    """GRVT Exchange client.
    
    Features:
    - Hybrid exchange with ZK-rollup settlement
    - Crypto perpetual futures up to 50x leverage
    - EIP-712 signing for orders
    - Low latency order matching
    """

    MAINNET_API = "https://trades.grvt.io"
    TESTNET_API = "https://trades.testnet.grvt.io"
    MAINNET_WS = "wss://trades.grvt.io/ws"
    TESTNET_WS = "wss://trades.testnet.grvt.io/ws"

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "grvt"
        self.venue_type = "dex"
        self.use_testnet = use_testnet

        self.api_key: Optional[str] = None
        self.private_key: Optional[str] = None
        self.trading_account_id: Optional[str] = None
        
        self.base_url: str = ""
        self.ws_url: str = ""
        self._client = None
        self._sdk = None
        self._trading_enabled = False
        
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    def connect(self) -> None:
        """Connect to GRVT."""
        load_dotenv()

        self.api_key = os.getenv("GRVT_API_KEY")
        self.private_key = os.getenv("GRVT_PRIVATE_KEY")
        self.trading_account_id = os.getenv("GRVT_TRADING_ACCOUNT_ID")
        
        env = os.getenv("GRVT_ENV", "mainnet").lower()
        self.use_testnet = (env == "testnet")
        
        self.base_url = self.TESTNET_API if self.use_testnet else self.MAINNET_API
        self.ws_url = self.TESTNET_WS if self.use_testnet else self.MAINNET_WS

        self._trading_enabled = False # Reset trading status

        # Suppress SDK internal logs that may contain sensitive cookies/session details.
        if os.getenv("PERPBOT_VERBOSE_WIRE_LOGS", "0").strip().lower() not in {"1", "true", "yes", "y"}:
            logging.getLogger("pysdk").setLevel(logging.WARNING)
            logging.getLogger("pysdk.grvt_raw_base").setLevel(logging.WARNING)

        # --- SDK Initialization ---
        # If all mandatory credentials for SDK are provided, attempt to initialize the SDK
        if all([self.api_key, self.private_key, self.trading_account_id]):
            try:
                from pysdk.grvt_raw_sync import GrvtRawSync
                from pysdk.grvt_raw_base import GrvtApiConfig
                from pysdk.grvt_raw_env import GrvtEnv

                env_type = GrvtEnv.TESTNET if self.use_testnet else GrvtEnv.PROD
                config = GrvtApiConfig(
                    env=env_type,
                    trading_account_id=self.trading_account_id,
                    private_key=self.private_key,
                    api_key=self.api_key,
                    # Avoid logging sensitive cookies/session details from SDK internals.
                    logger=None,
                )
                self._sdk = GrvtRawSync(config=config)
                self._trading_enabled = True
                logger.info("✅ GRVT SDK initialized and connected (testnet=%s, trading=True)", self.use_testnet)

            except ImportError:
                logger.error("❌ GRVT SDK not installed. Please install 'grvt-pysdk' to enable GRVT trading and account queries.")
            except Exception as e:
                logger.exception("❌ GRVT SDK initialization failed: %s", e)
        else:
            logger.warning("⚠️ GRVT trading DISABLED: Missing GRVT_API_KEY, GRVT_PRIVATE_KEY, or GRVT_TRADING_ACCOUNT_ID. Running in read-only mode if possible.")
        
        # --- Fallback HTTP Client for Public Read-Only (if SDK is not used for trading) ---
        if not self._trading_enabled or not self._sdk: # If SDK didn't enable trading or wasn't initialized
            try:
                import httpx
                # For public market data, a different base_url might be needed.
                # Assuming `self.base_url` (trades.grvt.io) can handle some public info for now.
                self._client = httpx.Client(
                    base_url=self.base_url, 
                    headers={"Content-Type": "application/json"},
                    timeout=15.0
                )
                logger.info("✅ GRVT read-only HTTP client initialized.")
            except ImportError:
                logger.debug("httpx not available for public fallback mode.")
            except Exception as e:
                logger.warning("⚠️ Failed to initialize GRVT public HTTP client: %s", e)

        if not self._trading_enabled:
            logger.info("✅ GRVT connected (testnet=%s, trading=False - read-only or SDK issue)", self.use_testnet)





    def _normalize_symbol(self, symbol: str) -> str:
        """Convert BTC/USDT to BTC_USDT_Perp."""
        base = symbol.replace("/", "_").replace("-", "_")
        # Normalize any existing perp suffix, then re-append in the format GRVT expects.
        for suffix in ("_Perp", "_PERP", "_perp", "_PerP"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}_Perp"

    def _build_order_payload(self, request: OrderRequest, instrument: str) -> Dict[str, Any]:
        """Build the GRVT SDK payload from a shared OrderRequest."""
        payload: Dict[str, Any] = {
            "instrument": instrument,
            "side": request.side.upper(),
            "size": str(request.size),
        }
        if request.limit_price is not None:
            payload.update(
                {
                    "order_type": "LIMIT",
                    "price": str(request.limit_price),
                    "time_in_force": "GTC",
                }
            )
        else:
            payload["order_type"] = "MARKET"
        return payload

    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current price."""
        market = self._normalize_symbol(symbol)
        
        try:
            if not self._sdk:
                logger.warning("GRVT SDK not initialized for price fetch. Cannot fetch real-time prices.")
                return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type="dex")

            from pysdk.grvt_raw_base import GrvtError
            from pysdk.grvt_raw_types import ApiTickerRequest

            resp = self._sdk.ticker_v1(ApiTickerRequest(instrument=market))
            if isinstance(resp, GrvtError):
                raise RuntimeError(f"GRVT ticker error code={resp.code} status={resp.status} msg={resp.message}")
            ticker = resp.result
            bid = float(ticker.best_bid_price or 0)
            ask = float(ticker.best_ask_price or 0)
            
            return PriceQuote(exchange=self.name, symbol=symbol, bid=bid, ask=ask, venue_type="dex")
        except Exception as e:
            logger.error("❌ GRVT price fetch failed: %s", e)
            return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type="dex")

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch order book."""
        market = self._normalize_symbol(symbol)
        
        try:
            if not self._sdk:
                logger.warning("GRVT SDK not initialized for orderbook fetch. Cannot fetch orderbook data.")
                return OrderBookDepth(bids=[], asks=[])

            from pysdk.grvt_raw_base import GrvtError
            from pysdk.grvt_raw_types import ApiOrderbookLevelsRequest

            requested_depth = int(depth)
            api_depth = next((d for d in _GRVT_ALLOWED_BOOK_DEPTHS if d >= requested_depth), _GRVT_ALLOWED_BOOK_DEPTHS[-1])

            resp = self._sdk.orderbook_levels_v1(ApiOrderbookLevelsRequest(instrument=market, depth=api_depth))
            if isinstance(resp, GrvtError):
                raise RuntimeError(f"GRVT orderbook error code={resp.code} status={resp.status} msg={resp.message}")
            book = resp.result
            bids = [(float(l.price), float(l.size)) for l in book.bids[:requested_depth]]
            asks = [(float(l.price), float(l.size)) for l in book.asks[:requested_depth]]
            
            return OrderBookDepth(bids=bids, asks=asks)
        except Exception as e:
            logger.error("❌ GRVT orderbook fetch failed: %s", e)
            return OrderBookDepth(bids=[], asks=[])

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place an order."""
        if not self._trading_enabled or not self._sdk: # Ensure SDK is ready
            logger.error("GRVT trading disabled or SDK not initialized. Cannot place order.")
            return Order(id="rejected", exchange=self.name, symbol=request.symbol,
                        side=request.side, size=request.size, price=0.0, status="rejected", error_message="SDK not initialized or trading disabled")

        market = self._normalize_symbol(request.symbol)
        payload = self._build_order_payload(request, market)

        try:
            result = self._sdk.create_order(**payload)
            order_id = str(result.order_id)
            filled_price = float(result.price or request.limit_price or 0)

            logger.info("✅ GRVT order placed: %s - ID: %s", request.symbol, order_id)

            return Order(
                id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                size=request.size,
                price=filled_price,
            )
        except Exception as e:
            logger.exception("❌ GRVT order failed: %s", e)
            return Order(id=f"error-{os.urandom(4).hex()}", exchange=self.name,
                        symbol=request.symbol, side=request.side, size=request.size, price=0.0, status="rejected", error_message=str(e))

    def place_close_order(self, position: Position, current_price: float) -> Order:
        """Close position."""
        closing_side = "sell" if position.order.side == "buy" else "buy"
        return self.place_open_order(OrderRequest(
            symbol=position.order.symbol, side=closing_side,
            size=position.order.size, limit_price=None,
        ))

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel order."""
        if not self._trading_enabled or not self._sdk:
            logger.error("GRVT trading disabled or SDK not initialized. Cannot cancel order.")
            return
        try:
            self._sdk.cancel_order(order_id=order_id)
            logger.info("✅ GRVT order cancelled: %s", order_id)
        except Exception as e:
            logger.error("❌ GRVT cancel failed: %s", e)

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get active orders."""
        if not self._trading_enabled or not self._sdk:
            logger.warning("GRVT SDK not initialized or trading disabled. Cannot fetch active orders.")
            return []
        try:
            orders_data = self._sdk.open_orders_v1()
            
            orders = []
            for o in orders_data or []:
                sym = o.instrument.replace("_Perp", "").replace("_", "/")
                orders.append(Order(
                    id=str(o.order_id), exchange=self.name, symbol=sym,
                    side=str(o.side).lower(), size=float(o.size), price=float(o.price or 0),
                ))
            return orders
        except Exception as e:
            logger.error("❌ GRVT orders query failed: %s", e)
            return []

    def get_account_positions(self) -> List[Position]:
        """Get positions."""
        if not self._trading_enabled or not self._sdk:
            logger.warning("GRVT SDK not initialized or trading disabled. Cannot fetch positions.")
            return []
        try:
            from pysdk.grvt_raw_base import GrvtError
            from pysdk.grvt_raw_types import ApiPositionsRequest

            req = ApiPositionsRequest(sub_account_id=str(self.trading_account_id or ""))
            resp = self._sdk.positions_v1(req)
            if isinstance(resp, GrvtError):
                raise RuntimeError(f"GRVT positions error code={resp.code} status={resp.status} msg={resp.message}")
            positions_data = resp.result
            
            positions = []
            for p in positions_data or []:
                size = float(p.size)
                if size == 0:
                    continue
                side = "buy" if size > 0 else "sell"
                sym = str(p.instrument or "").replace("_PerP", "").replace("_Perp", "").replace("_", "/")
                entry = float(p.entry_price or 0)
                
                order = Order(
                    id=f"pos-{sym}", exchange=self.name, symbol=sym,
                    side=side, size=abs(size), price=entry,
                )
                positions.append(Position(id=order.id, order=order, target_profit_pct=0.0))
            return positions
        except Exception as e:
            logger.error("❌ GRVT positions query failed: %s", e)
            return []

    def get_account_balances(self) -> List[Balance]:
        """Get balances."""
        if not self._trading_enabled or not self._sdk:
            logger.warning("GRVT SDK not initialized or trading disabled. Cannot fetch balances.")
            return []
        try:
            from pysdk.grvt_raw_base import GrvtError
            from pysdk.grvt_raw_types import EmptyRequest

            def _do():
                return self._sdk.aggregated_account_summary_v1(EmptyRequest())

            def _is_retryable(exc: Exception) -> bool:
                # GRVT occasionally drops the connection during cookie refresh.
                msg = f"{exc!r}"
                return "RemoteDisconnected" in msg or "Connection aborted" in msg

            resp = retry_call(
                _do,
                config=RetryConfig(max_attempts=3, min_delay_sec=0.5, max_delay_sec=3.0, jitter_sec=0.25),
                is_retryable=_is_retryable,
                label="grvt aggregated_account_summary_v1",
                log=logger,
            )
            if isinstance(resp, GrvtError):
                raise RuntimeError(f"GRVT balance error code={resp.code} status={resp.status} msg={resp.message}")
            summary = resp.result

            balances: List[Balance] = []
            for b in getattr(summary, "spot_balances", []) or []:
                total = float(getattr(b, "balance", 0) or 0)
                asset = getattr(b, "currency", "USDC") or "USDC"
                if total <= 0:
                    continue
                balances.append(Balance(asset=asset, free=total, locked=0.0, total=total))

            if balances:
                return balances

            total_equity = float(getattr(summary, "total_equity", 0) or 0)
            if total_equity > 0:
                return [Balance(asset="USDC", free=total_equity, locked=0.0, total=total_equity)]
            return []
        except Exception as e:
            logger.error("❌ GRVT balance query failed: %s", e)
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
