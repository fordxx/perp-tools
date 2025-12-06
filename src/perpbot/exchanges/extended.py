from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class ExtendedClient(RESTWebSocketExchangeClient):
    """Extended exchange connector built on the unified base."""

    def __init__(self) -> None:
        super().__init__(
            name="extended",
            env_prefix="EXTENDED",
            default_base_url="https://api.extended.exchange",
            default_testnet_url="https://testnet-api.extended.exchange",
            default_ws_url="wss://stream.extended.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.extended.exchange/ws",
        )
        self.ticker_endpoint = "/v1/markets/ticker"
        self.orderbook_endpoint = "/v1/markets/depth"
        self.order_endpoint = "/v1/trade/order"
        self.cancel_endpoint = "/v1/trade/cancel"
        self.open_orders_endpoint = "/v1/trade/open-orders"
        self.positions_endpoint = "/v1/account/positions"
        self.balance_endpoint = "/v1/account/balances"
        self.ws_orders_channel = "orders"
        self.ws_positions_channel = "positions"

    def _format_symbol(self, symbol: str) -> str:
        return symbol.replace("-", "").upper()
