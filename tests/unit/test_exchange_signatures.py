from __future__ import annotations

import inspect
import sys
import types
import unittest


# Prepare dummy hyperliquid packages so the module can be imported without the real SDK.
if "hyperliquid" not in sys.modules:
    sys.modules["hyperliquid"] = types.ModuleType("hyperliquid")

info_mod = types.ModuleType("hyperliquid.info")

class _DummyInfo:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

info_mod.Info = _DummyInfo
sys.modules["hyperliquid.info"] = info_mod

exchange_mod = types.ModuleType("hyperliquid.exchange")

class _DummyExchange:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

exchange_mod.Exchange = _DummyExchange
sys.modules["hyperliquid.exchange"] = exchange_mod

utils_mod = types.ModuleType("hyperliquid.utils")
utils_mod.__path__ = []
sys.modules["hyperliquid.utils"] = utils_mod

constants_mod = types.ModuleType("hyperliquid.utils.constants")
constants_mod.MAINNET_API_URL = "https://api.hyperliquid.test"
constants_mod.TESTNET_API_URL = "https://testnet.hyperliquid.test"
sys.modules["hyperliquid.utils.constants"] = constants_mod

from perpbot.exchanges.hyperliquid import HyperliquidClient
from perpbot.exchanges.okx import OKXClient


class ExchangeSignatureTestCase(unittest.TestCase):
    def _assert_request_signature(self, fn: object) -> None:
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        self.assertEqual(
            params,
            ["self", "request"],
            msg=f"{fn.__qualname__} signature must be (self, request)",
        )

    def test_hyperliquid_place_open_order_signature(self) -> None:
        self._assert_request_signature(HyperliquidClient.place_open_order)

    def test_okx_place_open_order_signature(self) -> None:
        self._assert_request_signature(OKXClient.place_open_order)
