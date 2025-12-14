from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace

from perpbot.models import OrderRequest
from perpbot.exchanges.grvt import GRVTClient


class _FakeSDK:
    def __init__(self) -> None:
        self.create_order_calls: list[dict] = []

    def create_order(self, **kwargs: object) -> SimpleNamespace:
        self.create_order_calls.append(kwargs)
        return SimpleNamespace(order_id="order-001", price=kwargs.get("price"))


class GRVTClientTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = GRVTClient()
        self.client._trading_enabled = True
        self.client._sdk = _FakeSDK()

    def test_build_order_payload_for_limit_order(self) -> None:
        request = OrderRequest(symbol="BTC/USDT", side="buy", size=0.5, limit_price=48000.0)
        payload = self.client._build_order_payload(
            request, self.client._normalize_symbol(request.symbol)
        )

        self.assertEqual(payload["instrument"], "BTC_USDT_PerP")
        self.assertEqual(payload["side"], "BUY")
        self.assertEqual(payload["size"], "0.5")
        self.assertEqual(payload["order_type"], "LIMIT")
        self.assertEqual(payload["price"], "48000.0")
        self.assertEqual(payload["time_in_force"], "GTC")

    def test_build_order_payload_for_market_order(self) -> None:
        request = OrderRequest(symbol="ETH/USDT", side="sell", size=1.2)
        payload = self.client._build_order_payload(
            request, self.client._normalize_symbol(request.symbol)
        )

        self.assertEqual(payload["instrument"], "ETH_USDT_PerP")
        self.assertEqual(payload["side"], "SELL")
        self.assertEqual(payload["size"], "1.2")
        self.assertEqual(payload["order_type"], "MARKET")
        self.assertNotIn("price", payload)
        self.assertNotIn("time_in_force", payload)

    def test_place_open_order_calls_sdk_with_payload(self) -> None:
        request = OrderRequest(symbol="BTC/USDT", side="buy", size=0.1, limit_price=47000.5)
        order = self.client.place_open_order(request)

        self.assertEqual(order.id, "order-001")
        self.assertEqual(order.price, 47000.5)

        call = self.client._sdk.create_order_calls[-1]
        self.assertEqual(call["instrument"], "BTC_USDT_PerP")
        self.assertEqual(call["side"], "BUY")
        self.assertEqual(call["order_type"], "LIMIT")
        self.assertEqual(call["price"], "47000.5")

    def test_place_open_order_market_uses_market_payload(self) -> None:
        request = OrderRequest(symbol="SOL/USDT", side="sell", size=2.0)
        order = self.client.place_open_order(request)

        self.assertEqual(order.id, "order-001")
        self.assertEqual(order.price, 0.0)

        call = self.client._sdk.create_order_calls[-1]
        self.assertEqual(call["order_type"], "MARKET")
        self.assertNotIn("price", call)
        self.assertNotIn("time_in_force", call)
