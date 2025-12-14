"""Hyperliquid perpetual futures client."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import eth_account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, PriceQuote, Side

logger = logging.getLogger(__name__)


class HyperliquidClient(ExchangeClient):
    """Hyperliquid perpetual futures client.
    
    Uses hyperliquid-python-sdk for orders and account data.
    Supports real-time price updates and order management.
    
    API Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/api
    """

    BASE_URL = constants.MAINNET_API_URL
    TESTNET_BASE_URL = constants.TESTNET_API_URL

    def __init__(self, use_testnet: bool = True) -> None:
        self.name = "hyperliquid"
        self.venue_type = "dex"
        self.use_testnet = use_testnet
        self.base_url = self.TESTNET_BASE_URL if use_testnet else self.BASE_URL

        self.private_key: Optional[str] = None
        self.vault_address: Optional[str] = None
        self.account_address: Optional[str] = None

        self._trading_enabled = False
        self._info_client: Optional[Info] = None
        self._exchange_client: Optional[Exchange] = None
        self._price_cache: Dict[str, PriceQuote] = {}
        self._cache_time: Dict[str, float] = {}
        self._cache_ttl = 2.0  # 2 second cache for prices

        self._order_handler: Optional[Callable] = None
        self._position_handler: Optional[Callable] = None

    def connect(self) -> None:
        """Load credentials and initialize connection to Hyperliquid."""
        load_dotenv()

        # Environment variable overrides constructor's use_testnet setting
        hyperliquid_env_var = os.getenv("HYPERLIQUID_ENV")
        if hyperliquid_env_var:
            self.use_testnet = (hyperliquid_env_var.lower() == "testnet")

        self.base_url = self.TESTNET_BASE_URL if self.use_testnet else self.BASE_URL

        # Load credentials
        self.account_address = os.getenv("HYPERLIQUID_ACCOUNT_ADDRESS")
        self.private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
        self.vault_address = os.getenv("HYPERLIQUID_VAULT_ADDRESS") # Unused for now, but kept for completeness

        # Initialize SDK clients
        self._info_client = Info(base_url=self.base_url)

        if self.private_key:
            try:
                wallet = eth_account.Account.from_key(self.private_key)
                self._exchange_client = Exchange(wallet, base_url=self.base_url, account_address=self.account_address)
                self._trading_enabled = True
            except Exception as e:
                logger.error(f"Failed to initialize Hyperliquid Exchange client with private key: {e}")
                self._trading_enabled = False
        else:
            logger.warning("HYPERLIQUID_PRIVATE_KEY not set - trading disabled")
            self._trading_enabled = False

        if not self.account_address:
            logger.warning("HYPERLIQUID_ACCOUNT_ADDRESS not set - some read operations may fail")

        logger.info("✅ Hyperliquid client connected (testnet=%s, trading=%s)",
                   self.use_testnet, self._trading_enabled)



    def get_current_price(self, symbol: str) -> PriceQuote:
        """Fetch current bid/ask price from Hyperliquid using SDK."""
        # Check cache
        now = time.time()
        if symbol in self._price_cache:
            cache_age = now - self._cache_time.get(symbol, 0)
            if cache_age < self._cache_ttl:
                return self._price_cache[symbol]

        if not self._info_client:
            logger.warning("Hyperliquid info client not initialized for price fetch.")
            return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0)

        asset = symbol.split("/")[0].upper()
        try:
            mids = self._info_client.all_mids()
            if asset not in mids:
                logger.warning(f"No mid price found for {asset}")
                return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0)

            mid_price_raw = mids[asset]
            # Ensure mid_price is a float
            try:
                mid_price = float(mid_price_raw)
            except (ValueError, TypeError):
                logger.error(f"Received non-numeric mid_price for {asset}: {mid_price_raw}. Skipping price derivation.")
                return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0)

            # Hyperliquid SDK provides mid price directly, derive bid/ask for consistency
            bid = mid_price * 0.9999
            ask = mid_price * 1.0001

            quote = PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=bid,
                ask=ask,
            )
            self._price_cache[symbol] = quote
            self._cache_time[symbol] = now

            logger.debug(f"Price {symbol}: bid={bid:.2f}, ask={ask:.2f}")
            return quote

        except Exception as e:
            logger.error(f"Error fetching price for {symbol} using SDK: {e}")
            return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0)

    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        """Fetch orderbook snapshot from Hyperliquid using SDK."""
        if not self._info_client:
            logger.warning("Hyperliquid info client not initialized for orderbook fetch.")
            return OrderBookDepth(bids=[], asks=[])

        asset = symbol.split("/")[0].upper()
        try:
            book = self._info_client.l2_book(asset)

            bids = []
            asks = []

            if book and book.get("bids"):
                for bid_level in book["bids"][:depth]:
                    price = float(bid_level[0])
                    size = float(bid_level[1])
                    bids.append((price, size))

            if book and book.get("asks"):
                for ask_level in book["asks"][:depth]:
                    price = float(ask_level[0])
                    size = float(ask_level[1])
                    asks.append((price, size))

            return OrderBookDepth(bids=bids, asks=asks)

        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol} using SDK: {e}")
            return OrderBookDepth(bids=[], asks=[])

    def place_open_order(self, request: OrderRequest) -> Order:
        """Place a new order to open a position using SDK."""
        if not self._trading_enabled or not self._exchange_client:
            logger.error("Trading disabled or Exchange client not initialized - cannot place order.")
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                price=request.limit_price or 0.0,
                size=request.size,
                status="rejected",
            )

        asset = request.symbol.split("/")[0].upper()
        is_buy = (request.side == Side.BUY)
        sz = request.size
        px = request.limit_price

        # Default order type to market (IOC) for orders without a limit price
        order_type_sdk = {"market": {"tif": "Ioc"}}
        if request.limit_price is not None:
            order_type_sdk = {"limit": {"tif": "Gtc"}}

        try:
            response = self._exchange_client.order(
                coin=asset,
                is_buy=is_buy,
                sz=sz,
                px=px,
                order_type=order_type_sdk,
                reduce_only=request.reduce_only,
            )

            if response and response.get("status") == "ok":
                status_data = response.get("response", {}).get("data", {}).get("statuses", [{}])[0]
                order_id = ""
                actual_price = px or 0.0
                order_status = "pending" # Default status

                if "resting" in status_data: # Limit order
                    order_id = str(status_data["resting"].get("oid", ""))
                    actual_price = float(status_data["resting"].get("limitPx", px))
                    order_status = "open"
                elif "filled" in status_data: # Market order or filled limit order
                    order_id = str(status_data["filled"].get("oid", ""))
                    actual_price = float(status_data["filled"].get("avgPx", px))
                    order_status = "filled"
                elif "error" in status_data:
                    error_msg = status_data["error"]
                    logger.error(f"Order placement error: {error_msg}")
                    return Order(
                        id=f"error-{int(time.time() * 1000)}",
                        exchange=self.name,
                        symbol=request.symbol,
                        side=request.side,
                        price=px or 0.0,
                        size=sz,
                        status="rejected",
                        error_message=error_msg,
                    )
                else:
                    logger.warning(f"Unknown order response status: {status_data}")
                    order_id = f"unknown-{int(time.time() * 1000)}"
                    order_status = "unknown"

                order = Order(
                    id=order_id,
                    exchange=self.name,
                    symbol=request.symbol,
                    side=request.side,
                    price=actual_price,
                    size=sz,
                    status=order_status,
                )
                logger.info(f"✅ Order placed (SDK): ID={order.id}, Price={order.price}, Status={order.status}")
                if self._order_handler:
                    self._order_handler(order)
                return order
            else:
                error_msg_detail = "Unknown error"
                if response:
                    status_data_list = response.get("response", {}).get("data", {}).get("statuses", [])
                    if status_data_list and "error" in status_data_list[0]:
                        error_msg_detail = status_data_list[0]["error"]
                    else:
                        error_msg_detail = json.dumps(response) # Log full response if structured error not found
                
                logger.error(f"Failed to place order (SDK). Response: {error_msg_detail}")
                return Order(
                    id=f"error-{int(time.time() * 1000)}",
                    exchange=self.name,
                    symbol=request.symbol,
                    side=request.side,
                    price=px or 0.0,
                    size=sz,
                    status="rejected",
                    error_message=error_msg_detail,
                )

        except Exception as e:
            logger.error(f"Error placing order using SDK: {e}")
            return Order(
                id=f"error-{int(time.time() * 1000)}",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                price=px or 0.0,
                size=sz,
                status="rejected",
                error_message=str(e),
            )

    def place_close_order(self, position: Any, current_price: float) -> Order:
        """Place a close order for an existing position using SDK."""
        if not self._trading_enabled:
            logger.error("Trading disabled - cannot close position")
            close_side = "sell" if position.get("side") == "buy" else "buy"
            return Order(
                id="rejected",
                exchange=self.name,
                symbol=position.get("symbol", ""),
                side=close_side,
                price=current_price,
                size=position.get("size", 0),
            )

        # Determine the side to close the position
        close_side = "sell" if position.get("side") == "buy" else "buy"
        
        # Create an OrderRequest with reduce_only=True
        close_request = OrderRequest(
            symbol=position.get("symbol", ""),
            side=close_side,
            size=position.get("size", 0),
            limit_price=current_price, # Use current price as limit to ensure it closes as a market order
            reduce_only=True, # Mark as reduce-only
        )

        # Re-use place_open_order logic for execution
        return self.place_open_order(close_request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        """Cancel an open order using SDK."""
        if not self._trading_enabled or not self._exchange_client:
            logger.error("Trading disabled or Exchange client not initialized - cannot cancel order.")
            return

        if not symbol:
            logger.error("Symbol is required to cancel an order on Hyperliquid.")
            return

        asset = symbol.split("/")[0].upper()
        try:
            response = self._exchange_client.cancel(coin=asset, oid=int(order_id))
            if response and response.get("status") == "ok":
                logger.info(f"✅ Order {order_id} cancelled successfully.")
            else:
                error_msg_detail = "Unknown error"
                if response:
                    status_data_list = response.get("response", {}).get("data", {}).get("statuses", [])
                    if status_data_list and "error" in status_data_list[0]:
                        error_msg_detail = status_data_list[0]["error"]
                    else:
                        error_msg_detail = json.dumps(response) # Log full response if structured error not found
                logger.error(f"Failed to cancel order {order_id}: {error_msg_detail}")
        except Exception as e:
            logger.error(f"Error canceling order {order_id} using SDK: {e}")

    def get_active_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Fetch all active orders for an account using SDK."""
        if not self._info_client:
            logger.warning("Hyperliquid info client not initialized for active order fetch.")
            return []
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch active orders.")
            return []

        try:
            # SDK's open_orders expects a list of account addresses
            open_orders_data = self._info_client.open_orders([self.account_address])
            orders = []

            if open_orders_data and open_orders_data[0]: # open_orders returns a list of lists (one per account)
                for order_data in open_orders_data[0]: # first element corresponds to self.account_address
                    order_symbol = order_data.get("coin", "").replace("USDC", "/USDC")
                    
                    if symbol is None or order_symbol == symbol:
                        order = Order(
                            id=str(order_data.get("oid", "")), # Ensure ID is string
                            exchange=self.name,
                            symbol=order_symbol,
                            side="buy" if order_data.get("isBuy") else "sell",
                            price=float(order_data.get("limitPx", 0)),
                            size=float(order_data.get("sz", 0)),
                        )
                        orders.append(order)

            logger.debug(f"Fetched {len(orders)} active orders")
            return orders

        except Exception as e:
            logger.error(f"Error fetching active orders using SDK: {e}")
            return []

    def get_account_positions(self) -> List[Dict[str, Any]]:
        """Fetch all open positions for an account using SDK."""
        if not self._info_client:
            logger.warning("Hyperliquid info client not initialized for position fetch.")
            return []
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch positions.")
            return []

        try:
            user_state = self._info_client.user_state(self.account_address)
            positions = []

            if user_state and "assetPositions" in user_state:
                for position_data in user_state["assetPositions"]:
                    position_info = position_data.get("position", {})
                    
                    coin = position_data.get("coin", "")
                    size = float(position_info.get("szi", 0))
                    
                    if size == 0: # Only include open positions
                        continue

                    entry_price = float(position_info.get("entryPx", 0))
                    
                    position = {
                        "symbol": coin.replace("USDC", "/USDC"),
                        "side": "buy" if size > 0 else "sell",
                        "size": abs(size),
                        "entry_price": entry_price,
                    }
                    positions.append(position)

            logger.debug(f"Fetched {len(positions)} positions")
            return positions

        except Exception as e:
            logger.error(f"Error fetching positions using SDK: {e}")
            return []

    def get_account_balances(self) -> List[Balance]:
        """Fetch account balances using SDK."""
        if not self._info_client:
            logger.warning("Hyperliquid info client not initialized for balance fetch.")
            return []
        if not self.account_address:
            logger.warning("Account address not set - cannot fetch balances.")
            return []

        try:
            user_state = self._info_client.user_state(self.account_address)
            balances = []

            if user_state and "marginSummary" in user_state:
                margin_summary = user_state["marginSummary"]
                account_value = float(margin_summary.get("accountValue", 0))
                total_margin_used = float(margin_summary.get("totalMarginUsed", 0))

                balances.append(Balance(
                    asset="USDC",
                    free=account_value - total_margin_used,
                    locked=total_margin_used,
                    total=account_value,
                ))

                logger.debug(f"Account value: {account_value:.2f} USDC, "
                           f"Margin used: {total_margin_used:.2f}")

            return balances

        except Exception as e:
            logger.error(f"Error fetching balances using SDK: {e}")
            return []

    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup a handler to receive order updates."""
        self._order_handler = handler
        logger.debug(f"Order update handler registered: {handler}")

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        """Setup a handler to receive position updates."""
        self._position_handler = handler
        logger.debug(f"Position update handler registered: {handler}")


def initialize_client(use_testnet: bool = True) -> HyperliquidClient:
    """Factory function to create and connect a HyperliquidClient."""
    client = HyperliquidClient(use_testnet=use_testnet)
    client.connect()
    return client
