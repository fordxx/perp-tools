from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class GRVTClient(RESTWebSocketExchangeClient):
    """GRVT derivatives connector."""

    def __init__(self) -> None:
        super().__init__(
            name="grvt",
            env_prefix="GRVT",
            default_base_url="https://api.grvt.exchange",
            default_testnet_url="https://testnet-api.grvt.exchange",
            default_ws_url="wss://stream.grvt.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.grvt.exchange/ws",
        )
