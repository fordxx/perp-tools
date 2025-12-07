from __future__ import annotations

import logging
import os
from typing import Callable, List, Optional

import httpx
import ccxt
from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class OKXClient(ExchangeClient):
    """
    ✅ OKX 永续合约 Demo Trading 客户端（终极稳定版）
    ✅ 行情：走 OKX 公共 REST（彻底规避 50038）
    ✅ 下单 / 平仓：走 ccxt 私有接口
    ✅ markets not loaded 已修复
    ✅ 本地空仓模式，专用于最小闭环测试
    """

    def __init__(self) -> None:
        self.name = "okx"
        self.venue_type = "cex"

        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None

        self.exchange: Optional[ccxt.okx] = None
        self._trading_enabled = False

        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    # =========================
    # ✅ 连接（Demo Trading）
    # =========================
    def connect(self) -> None:
        load_dotenv()

        self.api_key = os.getenv("OKX_API_KEY")
        self.api_secret = os.getenv("OKX_API_SECRET")
        self.passphrase = os.getenv("OKX_API_PASSPHRASE")

        if not self.api_key or not self.api_secret or not self.passphrase:
            raise RuntimeError("❌ Missing OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE in .env")

        self.exchange = ccxt.okx({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "password": self.passphrase,
            "enableRateLimit": True,
            "options": {
                "defaultType": "swap",
                "fetchCurrencies": False,   # ✅ 关键：禁止调用 Demo 禁用接口
            },
            "headers": {
                "x-simulated-trading": "1",  # ✅ Demo Trading
            }
        })

        # ✅ 禁止 fetch_currencies 触发 50038
        self.exchange.fetch_currencies = lambda *args, **kwargs: {}

        # ✅ 允许正常加载“公共市场”，否则会 markets not loaded
        self.exchange.load_markets()

        self._trading_enabled = True

        logger.info("✅ OKX Demo Trading connected")
        logger.info("🔐 Trading enabled: True")

    # =========================
    # ✅ 统一交易对
    # =========================
    def _normalize_symbol(self, symbol: str) -> str:
        if "SWAP" in symbol:
            return symbol
        if "/" in symbol:
            base, quote = symbol.split("/")
            return f"{base}-{quote}-SWAP"
        return symbol

    # =========================
    # ✅ 行情（公共 REST，永不 50038）
    # =========================
    def get_current_price(self, symbol: str) -> PriceQuote:
        rest_symbol = symbol.replace("/", "-").upper() + "-SWAP"
        url = "https://www.okx.com/api/v5/market/ticker"

        response = httpx.get(url, params={"instId": rest_symbol}, timeout=5)
        response.raise_for_status()

        data = response.json()

        if data.get("code") != "0" or not data.get("data"):
            raise RuntimeError(f"❌ OKX REST ticker failed: {data}")

        ticker = data["data"][0]
        bid = float(ticker["bidPx"])
        ask = float(ticker["askPx"])

        if bid <= 0 or ask <= 0:
            raise RuntimeError(f"❌ OKX invalid bid/ask from REST: {ticker}")

        return PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=bid,
            ask=ask,
            venue_type="cex",
        )

    # =========================
    # ✅ OrderBook（ccxt 可用）
    # =========================
    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        ccxt_symbol = self._normalize_symbol(symbol)
        book = self.exchange.fetch_order_book(ccxt_symbol, limit=depth)

        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q in book.get("bids", [])],
            asks=[(float(p), float(q)) for p, q in book.get("asks", [])],
        )

    # =========================
    # ✅ 开仓（市价）
    # =========================
    def place_open_order(self, request: OrderRequest) -> Order:
        if not self._trading_enabled:
            logger.warning("❌ Order rejected: trading disabled")
            return Order("rejected", self.name, request.symbol, request.side, request.size, 0.0)

        ccxt_symbol = self._normalize_symbol(request.symbol)

        order = self.exchange.create_order(
            symbol=ccxt_symbol,
            type="market",
            side=request.side,
            amount=request.size,
            params={
                "tdMode": "isolated",
                "posSide": "long" if request.side == "buy" else "short",  # ✅ 关键修复
            }
        )

        return Order(
            id=str(order["id"]),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=float(order.get("amount") or request.size),  # ✅ 关键修复
            price=float(order.get("average") or order.get("price") or 0),
        )

    # =========================
    # ✅ 平仓（reduceOnly）
    # =========================
    def place_close_order(self, position: Position, current_price: float) -> Order:
        side = "sell" if position.order.side == "buy" else "buy"
        ccxt_symbol = self._normalize_symbol(position.order.symbol)

        order = self.exchange.create_order(
            symbol=ccxt_symbol,
            type="market",
            side=side,
            amount=position.order.size,
            params={
                "reduceOnly": True,
                "tdMode": "isolated",
                "posSide": "long" if position.order.side == "buy" else "short",  # ✅ 关键修复
            }
        )

        return Order(
            id=str(order["id"]),
            exchange=self.name,
            symbol=position.order.symbol,
            side=side,
            size=float(order.get("amount") or position.order.size),
            price=float(order.get("average") or order.get("price") or current_price),
        )

    # =========================
    # ✅ 本地空仓模式（最稳定）
    # =========================
    def get_account_positions(self) -> List[Position]:
        return []

    # =========================
    # ✅ 活跃订单（最小实现）
    # =========================
    def get_active_orders(self) -> List[Order]:
        return []

    # =========================
    # ✅ 余额（最小实现）
    # =========================
    def get_account_balances(self) -> List[Balance]:
        return [Balance("USDT", 10_000)]

    # =========================
    # ✅ 撤单（兜底）
    # =========================
    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:
        try:
            self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            logger.warning("Cancel failed: %s", e)

    # =========================
    # ✅ WS 回调占位
    # =========================
    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler

    def setup_position_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._position_handler = handler
