from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class EdgeXClient(RESTWebSocketExchangeClient):
    """EdgeX perpetuals connector using REST/WebSocket endpoints.

    Endpoints can be overridden via environment variables:
    - EDGEX_BASE_URL / EDGEX_TESTNET_BASE_URL
    - EDGEX_WS_URL / EDGEX_TESTNET_WS_URL
    - EDGEX_ENV=testnet|mainnet
    """

    def __init__(self) -> None:
        super().__init__(
            name="edgex",
            env_prefix="EDGEX",
            default_base_url="https://api.edgex.exchange",
            default_testnet_url="https://testnet-api.edgex.exchange",
            default_ws_url="wss://stream.edgex.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.edgex.exchange/ws",
        )
