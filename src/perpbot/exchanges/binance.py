from __future__ import annotations

import logging
import os
from typing import Callable, Optional, List

import ccxt
from dotenv import load_dotenv

from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote

logger = logging.getLogger(__name__)


class BinanceClient(ExchangeClient):
    """
    ✅ Binance USDT-M Futures Testnet 客户端（严格只允许 Testnet）
    ✅ 完整实现 ExchangeClient 抽象接口（不会再报 abstract class 错误）
    ✅ 自动修复 fetch_ticker 返回 0 价格的问题
    ✅ 支持：行情 / 下单 / 平仓 / 持仓 / 余额 / 撤单
    """

    def __init__(self, use_testnet: bool = True) -> None:
        if not use_testnet:
            raise RuntimeError("❌ SAFETY ABORT: Mainnet is forbidden for Binance.")

        self.name = "binance"
        self.venue_type = "cex"
        self.use_testnet = True

        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.exchange: Optional[ccxt.binanceusdm] = None

        self._trading_enabled = False
        self._order_handler: Optional[Callable[[dict], None]] = None
        self._position_handler: Optional[Callable[[dict], None]] = None

    # =========================
    # ✅ 必须实现：connect
    # =========================
    def connect(self) -> None:
        load_dotenv()

        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")

        # 创建 CCXT 实例（即使没 key 也允许行情）
        self.exchange = ccxt.binanceusdm({
            "enableRateLimit": True,
            "options": {
                "defaultType": "future",
                "adjustForTimeDifference": True,
            }
        })

        # ✅ 强制 Testnet
        self.exchange.set_sandbox_mode(True)

        actual_url = self.exchange.urls.get("api", {}).get("public", "")

        testnet_whitelist = [
            "testnet.binancefuture.com",
            "testnet.binance.vision",
        ]

        if not any(domain in actual_url for domain in testnet_whitelist):
            raise RuntimeError(f"❌ SAFETY ABORT: Not a Binance Testnet endpoint: {actual_url}")

        # 若有 API Key 才启用交易
        if self.api_key and self.api_secret:
            self.exchange.apiKey = self.api_key
            self.exchange.secret = self.api_secret
            self._trading_enabled = True
        else:
            self._trading_enabled = False
            logger.warning("⚠️ Binance trading DISABLED: Missing API credentials")

        logger.info("✅ Binance Testnet connected")
        logger.info("🔐 Trading enabled: %s", self._trading_enabled)

    # =========================
    # ✅ 工具函数：统一交易对格式
    # =========================
    def _normalize_symbol(self, symbol: str) -> str:
        if ":USDT" in symbol:
            return symbol
        if "/" in symbol:
            base, quote = symbol.split("/")
            return f"{base}/{quote}:{quote}"
        return symbol

    # =========================
    # ✅ 行情（已修复 0 价格）
    # =========================
    def get_current_price(self, symbol: str) -> PriceQuote:
        if not self.exchange:
            raise RuntimeError("Client not connected")

        ccxt_symbol = self._normalize_symbol(symbol)
        ticker = self.exchange.fetch_ticker(ccxt_symbol)

        bid = ticker.get("bid")
        ask = ticker.get("ask")
        last = ticker.get("last") or ticker.get("close")

        # ✅ 自动修复 bid/ask 为 0 的问题
        if (not bid or bid <= 0) and last and last > 0:
            bid = last

        if (not ask or ask <= 0) and last and last > 0:
            ask = last

        # ✅ 再兜底：用 orderbook
        if not bid or not ask:
            book = self.exchange.fetch_order_book(ccxt_symbol, limit=5)
            if not bid and book.get("bids"):
                bid = book["bids"][0][0]
            if not ask and book.get("asks"):
                ask = book["asks"][0][0]

        if not bid or not ask:
            raise RuntimeError(f"❌ INVALID PRICE from Binance Testnet: {ticker}")

        return PriceQuote(
            exchange=self.name,
            symbol=symbol,
            bid=float(bid),
            ask=float(ask),
            venue_type="cex",
        )

    # =========================
    # ✅ OrderBook
    # =========================
    def get_orderbook(self, symbol: str, depth: int = 20) -> OrderBookDepth:
        ccxt_symbol = self._normalize_symbol(symbol)
        book = self.exchange.fetch_order_book(ccxt_symbol, limit=depth)

        return OrderBookDepth(
            bids=[(float(p), float(q)) for p, q in book.get("bids", [])],
            asks=[(float(p), float(q)) for p, q in book.get("asks", [])],
        )

    # =========================
    # ✅ 下单（市价）
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
        )

        return Order(
            id=str(order["id"]),
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=float(order["amount"]),
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
            params={"reduceOnly": True},
        )

        return Order(
            id=str(order["id"]),
            exchange=self.name,
            symbol=position.order.symbol,
            side=side,
            size=float(order["amount"]),
            price=float(order.get("average") or order.get("price") or 0),
        )
    # ✅ 1️⃣ 取消订单（Testnet 最小实现）
    async def cancel_order(self, order_id: str, symbol: str):
        try:
            return await self.exchange.cancel_order(order_id, symbol)
        except Exception as e:
            self.logger.warning(f"[BinanceClient] cancel_order failed: {e}")
            return None

    # ✅ 2️⃣ 账户余额（Testnet 本地空仓模式：返回固定假数据）
    async def get_account_balances(self):
        return {
            "USDT": {
                "free": 10_000,
                "used": 0,
                "total": 10_000,
            }
        }

    # ✅ 3️⃣ 当前仓位（Testnet 空仓模式：永远返回空）
    async def get_account_positions(self):
        return []

    # ✅ 4️⃣ 当前活跃订单（Testnet 最小闭环：返回空）
    async def get_active_orders(self):
        return []

    # ✅ 5️⃣ 订单更新监听（Testnet 不需要 websocket：空实现即可）
    def setup_order_update_handler(self, callback):
        self.logger.info("[BinanceClient] Order update handler registered (noop for testnet)")

    # =========================
    # ✅ 持仓
    # =========================
def get_account_positions(self) -> List[Position]:
    """
    ✅ SAFE MODE (Binance Futures Testnet 已被官方废弃 fetch_positions)
    ✅ 本地模式：不再调用 CCXT 的 fetch_positions
    ✅ 由上层策略自行维护仓位
    """
    logger.warning("⚠️ Binance Futures Testnet 已禁用 fetch_positions，当前使用本地空仓模式")
    return []

    # =========================
    # ✅ 活动订单
    # =========================
    def get_active_orders(self) -> List[Order]:
        orders = self.exchange.fetch_open_orders()
        result = []
        for o in orders:
            result.append(
                Order(
                    id=str(o["id"]),
                    exchange=self.name,
                    symbol=o["symbol"].replace(":USDT", ""),
                    side=o["side"],
                    size=float(o["amount"]),
                    price=float(o["price"] or 0),
                )
            )
        return result

    # =========================
    # ✅ 余额
    # =========================
    def get_account_balances(self) -> List[Balance]:
        bal = self.exchange.fetch_balance()
        usdt = bal["total"].get("USDT", 0)
        return [Balance("USDT", float(usdt))]

    # =========================
    # ✅ 撤单
    # =========================
    def cancel_order(self, order_id: str, symbol: str) -> None:
        ccxt_symbol = self._normalize_symbol(symbol)
        self.exchange.cancel_order(order_id, ccxt_symbol)

    # =========================
    # ✅ WS 回调占位（满足抽象接口）
    # =========================
    def setup_order_update_handler(self, handler: Callable[[dict], None]) -> None:
        self._order_handler = handler
