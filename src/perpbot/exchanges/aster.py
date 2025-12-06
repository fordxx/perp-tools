from __future__ import annotations

import logging

from perpbot.exchanges.base import RESTWebSocketExchangeClient

logger = logging.getLogger(__name__)


class AsterClient(RESTWebSocketExchangeClient):
    """Aster derivatives connector leveraging shared REST/WS plumbing."""

    def __init__(self) -> None:
        super().__init__(
            name="aster",
            env_prefix="ASTER",
            default_base_url="https://api.aster.exchange",
            default_testnet_url="https://testnet-api.aster.exchange",
            default_ws_url="wss://stream.aster.exchange/ws",
            default_testnet_ws_url="wss://testnet-stream.aster.exchange/ws",
        )
