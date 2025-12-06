from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class ParadexClient(RESTWebSocketExchangeClient):
    """Paradex connector using the unified REST/WebSocket template."""

    def __init__(self) -> None:
        super().__init__(
            name="paradex",
            env_prefix="PARADEX",
            default_base_url="https://api.paradex.exchange",
            default_testnet_url="https://testnet-api.paradex.exchange",
            default_ws_url="wss://stream.paradex.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.paradex.exchange/ws",
        )
