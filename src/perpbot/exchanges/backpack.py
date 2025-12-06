from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class BackpackClient(RESTWebSocketExchangeClient):
    """Backpack perpetual connector with REST and WebSocket control."""

    def __init__(self) -> None:
        super().__init__(
            name="backpack",
            env_prefix="BACKPACK",
            default_base_url="https://api.backpack.exchange",
            default_testnet_url="https://testnet-api.backpack.exchange",
            default_ws_url="wss://stream.backpack.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.backpack.exchange/ws",
        )
