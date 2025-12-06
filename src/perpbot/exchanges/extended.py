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
