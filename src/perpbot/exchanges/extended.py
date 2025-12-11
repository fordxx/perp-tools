"""Extended DEX client powered by the official x10-python-trading-starknet SDK."""
from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from typing import Any, Callable, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from fast_stark_crypto.lib import get_public_key
from perpbot.execution.execution_engine import (
    OrderResult as ExecutionOrderResult,
    OrderStatus as ExecutionOrderStatus,
)
from perpbot.models import Balance, Order, OrderBookDepth, OrderRequest, Position, PriceQuote, Side
from perpbot.exchanges.base import ExchangeClient
from x10.perpetual.accounts import AccountStreamDataModel, StarkPerpetualAccount
from x10.perpetual.configuration import EndpointConfig, MAINNET_CONFIG, TESTNET_CONFIG
from x10.perpetual.markets import MarketModel, MarketStatsModel
from x10.perpetual.orderbooks import OrderbookUpdateModel
from x10.perpetual.orders import OrderSide, PlacedOrderModel, TimeInForce
from x10.perpetual.positions import PositionModel, PositionSide
from x10.perpetual.stream_client import PerpetualStreamClient
from x10.perpetual.trading_client import PerpetualTradingClient
from x10.utils.log import get_logger

TradingLogger = get_logger("perpbot.extended")
ORDERBOOK_SNAPSHOT_DEPTH = 20


@dataclass
class OrderInfo:
    order_id: str
    symbol: str
    side: Side
    price: float
    quantity: float
    filled_qty: float
    average_price: Optional[float]
    status: str


@dataclass
class PartialFillState:
    total_size: float = 0.0
    average_price: float = 0.0


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "-").upper()


def human_symbol(market_name: str) -> str:
    return market_name.replace("-", "/")


def to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


class ExtendedClient(ExchangeClient):
    """Extended client that delegates all trading to the x10 trading client."""

    def __init__(self, use_testnet: bool = False) -> None:
        self.name = "extended"
        self.venue_type = "dex"
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.stark_private_key: Optional[str] = None
        self.vault_number: Optional[str] = None

        self._endpoint_config: EndpointConfig = TESTNET_CONFIG if use_testnet else MAINNET_CONFIG
        self.base_url: str = self._endpoint_config.api_base_url
        self.ws_url: str = self._endpoint_config.stream_url

        self._trading_enabled: bool = False
        self._stark_account: Optional[StarkPerpetualAccount] = None
        self._trading_client: Optional[PerpetualTradingClient] = None
        self._stream_client: Optional[PerpetualStreamClient] = None

        self._markets: Dict[str, MarketModel] = {}
        self._market_stats_cache: Dict[str, MarketStatsModel] = {}
        self._orderbook_cache: Dict[str, OrderbookUpdateModel] = {}
        self._open_orders: Dict[str, OrderInfo] = {}
        self._positions: Dict[str, Position] = {}
        self._partial_fills: Dict[str, PartialFillState] = {}

        self._order_handler: Optional[Callable[[OrderInfo], None]] = None

        # streaming infra
        self._stream_loop: Optional[asyncio.AbstractEventLoop] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._stream_ready = threading.Event()
        self._stop_stream = threading.Event()
        self._orderbook_tasks: Dict[str, asyncio.Future] = {}
        self._account_task: Optional[asyncio.Future] = None

        # diagnostics
        self._last_order_error: Optional[str] = None
        self._last_payload: Optional[Dict[str, Any]] = None
        self._last_response: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Public API consumed by the majority of the toolkit
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Load env, prepare Stark account, create trading/stream clients and start workers."""
        load_dotenv()

        self.api_key = os.getenv("EXTENDED_API_KEY")
        self.stark_private_key = os.getenv("EXTENDED_STARK_PRIVATE_KEY")
        self.vault_number = os.getenv("EXTENDED_VAULT_NUMBER")

        env = os.getenv("EXTENDED_ENV", "testnet").lower()
        self.use_testnet = env == "testnet"
        self._endpoint_config = TESTNET_CONFIG if self.use_testnet else MAINNET_CONFIG
        self.base_url = self._endpoint_config.api_base_url
        self.ws_url = self._endpoint_config.stream_url

        self._trading_enabled = False

        if not self.api_key:
            raise ValueError("Extended API key is required")

        self._prepare_stark_account()
        if not self._stark_account:
            raise ValueError("Stark account invalid, cannot initialize trading client")

        self._trading_client = PerpetualTradingClient(
            endpoint_config=self._endpoint_config,
            stark_account=self._stark_account,
        )
        self._stream_client = PerpetualStreamClient(api_url=self._endpoint_config.stream_url)

        self._load_markets()
        self._start_stream_workers()

        TradingLogger.info("Extended client ready (testnet=%s)", self.use_testnet)
        self._trading_enabled = True

    def disconnect(self) -> None:
        if self._trading_client:
            try:
                self._run_async(self._trading_client.close())
            except Exception as exc:  # pragma: no cover - best effort
                TradingLogger.warning("Failed to close trading client: %s", exc)
        self._stop_stream_workers()

    # ----- basic metadata / quotes -------------------------------------------------

    def get_contract_attributes(self, symbol: str) -> Dict[str, Any]:
        market = self._get_market(normalize_symbol(symbol))
        cfg = market.trading_config
        return {
            "tick_size": float(cfg.min_price_change),
            "min_order_size": float(cfg.min_order_size),
            "max_order_value": float(cfg.max_limit_order_value),
        }

    def fetch_bbo_prices(self, symbols: Optional[Sequence[str]] = None) -> Dict[str, PriceQuote]:
        prices: Dict[str, PriceQuote] = {}
        targets = symbols or [human_symbol(name) for name in self._markets.keys()]
        for symbol in targets:
            self._ensure_orderbook_stream(symbol)
            quote = self._quote_from_cache(symbol)
            if quote:
                prices[symbol] = quote
        return prices

    def get_order_price(self, symbol: str) -> float:
        quote = self.fetch_bbo_prices([symbol]).get(symbol)
        if quote:
            return quote.mid
        stats = self._load_market_stats(symbol)
        if stats:
            return float((stats.bid_price + stats.ask_price) / 2)
        return 0.0

    # ----- trading interface -------------------------------------------------------

    def place_open_order(self, request: OrderRequest) -> Order:
        result = self._execute_order(request)
        return self._order_from_result(result, request)

    def place_close_order(self, position: Position, current_price: float) -> Order:
        closing_side = "sell" if position.order.side == "buy" else "buy"
        request = OrderRequest(
            symbol=position.order.symbol,
            side=closing_side,
            size=position.order.size,
            limit_price=current_price,
        )
        result = self._execute_order(request)
        return self._order_from_result(result, request)

    def cancel_order(self, order_id: str, symbol: Optional[str] = None) -> None:  # noqa: ARG002 (symbol)
        if not self._trading_client:
            raise RuntimeError("Trading client not initialized")
        try:
            self._run_async(self._cancel_order_async(order_id))
        except Exception as exc:  # pragma: no cover - log only
            TradingLogger.error("Cancel %s failed: %s", order_id, exc)

    def get_active_orders(self) -> List[OrderInfo]:
        return list(self._open_orders.values())

    def get_order_info(self, order_id: str) -> Optional[OrderInfo]:
        cached = self._open_orders.get(order_id)
        if cached:
            return cached

        if not self._trading_client:
            return None

        try:
            response = self._run_async(self._trading_client.account.get_order_by_id(int(order_id)))
            if response.data:
                return self._map_order_info(response.data)
        except Exception as exc:
            TradingLogger.warning("Failed to fetch order %s: %s", order_id, exc)
        return None

    # ----- diagnostics -------------------------------------------------------------

    def get_last_order_error(self) -> Optional[str]:
        return self._last_order_error

    def get_last_payload(self) -> Optional[Dict[str, Any]]:
        return self._last_payload

    def get_last_response(self) -> Optional[Dict[str, Any]]:
        return self._last_response

    # ----- account state -----------------------------------------------------------

    def get_account_positions(self) -> List[Position]:
        if not self._trading_client:
            return []
        try:
            response = self._run_async(self._trading_client.account.get_positions())
            positions = [self._map_position(m) for m in (response.data or [])]
            self._positions = {pos.id: pos for pos in positions}
            return positions
        except Exception as exc:
            TradingLogger.warning("Failed to load positions: %s", exc)
            return list(self._positions.values())

    def get_account_balances(self) -> List[Balance]:
        if not self._trading_client:
            return []
        try:
            response = self._run_async(self._trading_client.account.get_balance())
            data = response.data
            if not data:
                return []
            balance = Balance(
                asset=data.collateral_name or "USDC",
                free=float(data.available_for_trade),
                locked=max(float(data.balance) - float(data.available_for_trade), 0.0),
                total=float(data.balance),
            )
            return [balance]
        except Exception as exc:
            TradingLogger.warning("Balance lookup failed: %s", exc)
            return []

    # ----- streaming hooks --------------------------------------------------------

    def setup_order_update_handler(self, handler: Callable[[OrderInfo], None]) -> None:
        self._order_handler = handler

    def get_current_price(self, symbol: str) -> PriceQuote:
        self._ensure_orderbook_stream(symbol)
        quote = self._quote_from_cache(symbol)
        if quote:
            return quote

        stats = self._load_market_stats(symbol)
        if stats:
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=float(stats.bid_price),
                ask=float(stats.ask_price),
                venue_type=self.venue_type,
            )

        return PriceQuote(exchange=self.name, symbol=symbol, bid=0.0, ask=0.0, venue_type=self.venue_type)

    def get_orderbook(self, symbol: str, depth: int = 5) -> OrderBookDepth:
        market = normalize_symbol(symbol)
        orderbook = self._orderbook_cache.get(market)
        if orderbook and orderbook.bid and orderbook.ask:
            bids = [(float(entry.price), float(entry.qty)) for entry in orderbook.bid[:depth]]
            asks = [(float(entry.price), float(entry.qty)) for entry in orderbook.ask[:depth]]
            return OrderBookDepth(bids=bids, asks=asks)

        snapshot = self._load_orderbook_snapshot(symbol)
        if snapshot:
            bids = [(float(entry.price), float(entry.qty)) for entry in snapshot.bid[:depth]]
            asks = [(float(entry.price), float(entry.qty)) for entry in snapshot.ask[:depth]]
            return OrderBookDepth(bids=bids, asks=asks)

        return OrderBookDepth()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_async(self, coro: Any) -> Any:
        """Run `coro` in whatever event-loop situation we are in now."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            temp_loop = asyncio.new_event_loop()
            try:
                return temp_loop.run_until_complete(coro)
            finally:
                temp_loop.close()

        return loop.run_until_complete(coro)

    # ----- Stark account / markets ------------------------------------------------

    def _prepare_stark_account(self) -> None:
        if not (self.stark_private_key and self.vault_number and self.api_key):
            TradingLogger.warning("Stark credentials missing")
            return

        public_hex = hex(get_public_key(int(self.stark_private_key, 16)))
        self._stark_account = StarkPerpetualAccount(
            vault=int(self.vault_number, 0),
            private_key=self.stark_private_key,
            public_key=public_hex,
            api_key=self.api_key,
        )

    def _get_market(self, market_name: str) -> MarketModel:
        if market_name in self._markets:
            return self._markets[market_name]
        self._load_markets()
        if market_name not in self._markets:
            raise KeyError(f"Market {market_name} unknown")
        return self._markets[market_name]

    def _load_markets(self) -> None:
        if not self._trading_client:
            return
        response = self._run_async(self._trading_client.markets_info.get_markets())
        if response.data:
            self._markets = {model.name: model for model in response.data}

    def _load_market_stats(self, symbol: str) -> Optional[MarketStatsModel]:
        market_name = normalize_symbol(symbol)
        if market_name in self._market_stats_cache:
            return self._market_stats_cache[market_name]

        if not self._trading_client:
            return None

        try:
            response = self._run_async(
                self._trading_client.markets_info.get_market_statistics(market_name=market_name)
            )
            if response.data:
                self._market_stats_cache[market_name] = response.data
                return response.data
        except Exception as exc:
            TradingLogger.debug("Market stats fail %s: %s", symbol, exc)
        return None

    def _quote_from_cache(self, symbol: str) -> Optional[PriceQuote]:
        market_name = normalize_symbol(symbol)
        book = self._orderbook_cache.get(market_name)
        if not book:
            book = self._load_orderbook_snapshot(symbol)
        if book and book.bid and book.ask:
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=float(book.bid[0].price),
                ask=float(book.ask[0].price),
                venue_type=self.venue_type,
            )

        stats = self._load_market_stats(symbol)
        if stats:
            return PriceQuote(
                exchange=self.name,
                symbol=symbol,
                bid=float(stats.bid_price),
                ask=float(stats.ask_price),
                venue_type=self.venue_type,
            )
        return None

    # ----- order execution --------------------------------------------------------

    def _execute_order(self, request: OrderRequest) -> ExecutionOrderResult:
        if not self._trading_client:
            raise RuntimeError("Trading client not ready")

        market_name = normalize_symbol(request.symbol)
        market = self._get_market(market_name)

        raw_quantity = Decimal(str(request.size))
        quantity = self._round_quantity(raw_quantity, market)

        side = OrderSide.BUY if request.side == "buy" else OrderSide.SELL
        is_limit_request = request.limit_price is not None
        time_in_force = TimeInForce.GTT if is_limit_request else TimeInForce.IOC

        if quantity <= 0:
            raise ValueError("Rounded quantity must be positive")

        price_candidate: Decimal
        if is_limit_request:
            price_candidate = Decimal(str(request.limit_price))
        else:
            quote = self._quote_from_cache(request.symbol)
            best_price = 0.0
            if quote:
                best_price = quote.ask if side == OrderSide.BUY else quote.bid
            if not best_price or best_price <= 0:
                stats = self._load_market_stats(request.symbol)
                stats_price = None
                if stats:
                    stats_price = stats.ask_price if side == OrderSide.BUY else stats.bid_price
                best_price = float(stats_price) if stats_price is not None else 0.0
            if not best_price or best_price <= 0:
                raise RuntimeError("Unable to determine market price for IOC order")
            price_candidate = Decimal(str(best_price))

        price = price_candidate
        round_price_fn = getattr(market.trading_config, "round_price", None)
        if callable(round_price_fn):
            try:
                price = round_price_fn(price_candidate)  # type: ignore[assignment]
            except Exception:
                price = price_candidate

        expire_dt: Optional[datetime] = None
        expire_ts: Optional[int] = None
        if time_in_force == TimeInForce.GTT:
            expire_dt = utc_now() + timedelta(minutes=5)
            expire_ts = int(expire_dt.timestamp())

        post_only = is_limit_request

        payload: Dict[str, Any] = {
            "market": market_name,
            "side": side.value,
            "qty": self._format_decimal_for_api(quantity),
            "price": self._format_decimal_for_api(price),
            "type": "LIMIT",
            "time_in_force": time_in_force.value,
            "post_only": post_only,
        }
        if expire_ts is not None:
            payload["expire_time"] = expire_ts

        self._last_payload = payload

        try:
            response = self._run_async(
                self._trading_client.place_order(
                    market_name=market_name,
                    amount_of_synthetic=quantity,
                    price=price,
                    side=side,
                    post_only=post_only,
                    time_in_force=time_in_force,
                    expire_time=expire_dt,
                )
            )

            placed: Optional[PlacedOrderModel] = response.data
            order_id = str(placed.external_id if placed and placed.external_id else placed.id if placed else "unknown")

            fill_price = float(price)
            notional = float(price * quantity)

            self._last_response = {
                "status": "ok",
                "order_id": order_id,
                "details": placed,
            }
            self._last_order_error = None

            TradingLogger.info("Placed %s order %s @ %s qty=%s", request.side, order_id, price, quantity)

            return ExecutionOrderResult(
                order_id=order_id,
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                order_type="maker",
                notional=notional,
                fill_price=fill_price,
                status=ExecutionOrderStatus.SUBMITTED,
                actual_fee=0.0,
                is_fallback=False,
                execution_time_ms=0.0,
            )

        except Exception as exc:
            self._last_response = {"status": "error", "error": str(exc)}
            self._last_order_error = str(exc)
            TradingLogger.error("Order submission failed: %s", exc)

            safe_notional = float(price * quantity)
            return ExecutionOrderResult(
                order_id="error",
                exchange=self.name,
                symbol=request.symbol,
                side=request.side,
                order_type="maker",
                notional=safe_notional,
                fill_price=float(price),
                status=ExecutionOrderStatus.FAILED,
                actual_fee=0.0,
                is_fallback=False,
                execution_time_ms=0.0,
                error=str(exc),
            )

    def _round_quantity(self, quantity: Decimal, market: MarketModel) -> Decimal:
        """Round quantity according to market trading config to avoid precision errors."""
        cfg = market.trading_config

        # Prefer SDK-provided rounding helpers if they exist
        for attr in ("round_size", "round_amount", "round_qty"):
            fn = getattr(cfg, attr, None)
            if callable(fn):
                try:
                    return fn(quantity)  # type: ignore[misc]
                except Exception:
                    pass

        # Fallback: floor to multiple of min_order_size
        step_raw = getattr(cfg, "min_order_size", None)
        try:
            step = Decimal(str(step_raw)) if step_raw is not None else Decimal("0")
        except Exception:
            step = Decimal("0")

        if step > 0:
            units = (quantity / step).to_integral_value(rounding=ROUND_FLOOR)
            qty = units * step
            if qty <= 0:
                # 如果太小，直接用最小 size，交给交易所再校验
                qty = step
            return qty

        # As a very last resort, just normalize
        return quantity.normalize()

    def _determine_price(self, request: OrderRequest, market_name: str) -> Decimal:
        if request.limit_price is not None:
            price = Decimal(str(request.limit_price))
        else:
            order_price = Decimal(str(self.get_order_price(request.symbol)))
            price = order_price if order_price > 0 else Decimal("0.0")

        market = self._markets.get(market_name)
        if market:
            try:
                return market.trading_config.round_price(price)
            except Exception:
                pass

        # generic 1e-4 rounding as fallback
        return price.quantize(Decimal("0.0001"))

    def _format_decimal_for_api(self, value: Decimal) -> str:
        normalized = value.normalize()
        text = format(normalized, "f")
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    async def _cancel_order_async(self, order_id: str) -> None:
        if not self._trading_client:
            raise RuntimeError("Trading client not initialized")
        try:
            await self._trading_client.orders.cancel_order(int(order_id))
        except ValueError:
            await self._trading_client.orders.cancel_order_by_external_id(order_id)

    # ----- stream workers ---------------------------------------------------------

    def _start_stream_workers(self) -> None:
        if not self._stream_client or not self.api_key:
            return
        self._stop_stream.clear()
        loop = asyncio.new_event_loop()
        self._stream_loop = loop
        self._stream_thread = threading.Thread(
            target=self._stream_loop_worker,
            args=(loop,),
            daemon=True,
        )
        self._stream_thread.start()
        self._stream_ready.wait(timeout=5)

    def _stop_stream_workers(self) -> None:
        if not self._stream_loop:
            return
        self._stop_stream.set()
        if self._account_task:
            self._account_task.cancel()
        self._stream_loop.call_soon_threadsafe(self._stream_loop.stop)
        if self._stream_thread:
            self._stream_thread.join(timeout=2)
        for task in list(self._orderbook_tasks.values()):
            task.cancel()
        self._orderbook_tasks.clear()
        self._stream_loop = None
        self._stream_thread = None
        self._stream_ready.clear()

    def _stream_loop_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        self._account_task = loop.create_task(self._account_stream_loop())
        self._stream_ready.set()
        loop.run_forever()

    async def _account_stream_loop(self) -> None:
        if not self._stream_client or not self.api_key:
            return
        while not self._stop_stream.is_set():
            try:
                async with self._stream_client.subscribe_to_account_updates(self.api_key) as stream:
                    async for frame in stream:
                        if self._stop_stream.is_set():
                            break
                        if frame.data:
                            self._process_account_stream(frame.data)
            except Exception as exc:
                TradingLogger.warning("Account stream error: %s", exc)
                await asyncio.sleep(5)

    def _process_account_stream(self, data: AccountStreamDataModel) -> None:
        for order_model in data.orders or []:
            info = self._map_order_info(order_model)
            self._open_orders[info.order_id] = info

            if info.filled_qty > 0 and info.filled_qty < info.quantity:
                state = self._partial_fills.setdefault(info.order_id, PartialFillState())
                state.total_size = info.filled_qty
                if info.average_price:
                    state.average_price = info.average_price
            elif info.status.lower() in {"filled", "cancelled"}:
                self._partial_fills.pop(info.order_id, None)

            if self._order_handler:
                self._order_handler(info)

        for position_model in data.positions or []:
            pos = self._map_position(position_model)
            self._positions[pos.id] = pos

    def _map_order_info(self, model: Any) -> OrderInfo:
        filled = to_float(getattr(model, "filled_qty", 0.0))
        average = to_float(getattr(model, "average_price", 0.0))
        market_name = getattr(model, "market", "")
        side = getattr(model, "side", OrderSide.BUY)

        order_id = getattr(model, "external_id", None) or getattr(model, "id")
        status_value = model.status.value if hasattr(model.status, "value") else str(model.status)
        return OrderInfo(
            order_id=str(order_id),
            symbol=human_symbol(market_name),
            side="buy" if side == OrderSide.BUY else "sell",
            price=float(getattr(model, "price", 0.0)),
            quantity=float(getattr(model, "qty", 0.0)),
            filled_qty=filled,
            average_price=average if average > 0 else None,
            status=status_value,
        )

    def _map_position(self, model: PositionModel) -> Position:
        side = "buy" if model.side == PositionSide.LONG else "sell"
        order = Order(
            id=f"pos-{model.id}",
            exchange=self.name,
            symbol=human_symbol(model.market),
            side=side,
            size=float(model.size),
            price=float(model.open_price),
        )
        return Position(id=order.id, order=order, target_profit_pct=0.0)

    def _order_from_result(self, result: ExecutionOrderResult, request: OrderRequest) -> Order:
        return Order(
            id=result.order_id,
            exchange=self.name,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=result.fill_price,
        )

    # ----- orderbook streaming ----------------------------------------------------

    def _ensure_orderbook_stream(self, symbol: str) -> None:
        market = normalize_symbol(symbol)
        if market in self._orderbook_tasks or not self._stream_loop or not self._stream_client:
            return
        depth = 5
        future = asyncio.run_coroutine_threadsafe(
            self._orderbook_stream_worker(market, symbol, depth),
            self._stream_loop,
        )
        self._orderbook_tasks[market] = future

    async def _orderbook_stream_worker(self, market: str, symbol: str, depth: int) -> None:
        try:
            while not self._stop_stream.is_set():
                try:
                    async with self._stream_client.subscribe_to_orderbooks(market_name=market, depth=depth) as stream:
                        async for frame in stream:
                            if self._stop_stream.is_set():
                                break
                            if frame.data:
                                trimmed = OrderbookUpdateModel(
                                    market=frame.data.market,
                                    bid=frame.data.bid[:depth],
                                    ask=frame.data.ask[:depth],
                                )
                                self._orderbook_cache[market] = trimmed
                except Exception as exc:
                    TradingLogger.debug("Orderbook stream %s error: %s", symbol, exc)
                    await asyncio.sleep(3)
        finally:
            self._orderbook_tasks.pop(market, None)

    def _load_orderbook_snapshot(self, symbol: str) -> Optional[OrderbookUpdateModel]:
        market = normalize_symbol(symbol)
        if not self._trading_client:
            return None
        try:
            response = self._run_async(self._trading_client.markets_info.get_orderbook(market_name=market))
            data = response.data
            if data:
                depth = 5
                snapshot = OrderbookUpdateModel(
                    market=data.market,
                    bid=data.bid[:depth],
                    ask=data.ask[:depth],
                )
                self._orderbook_cache[market] = snapshot
                return snapshot
        except Exception as exc:
            TradingLogger.debug("Orderbook snapshot failed for %s: %s", symbol, exc)
        return None

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.disconnect()
        except Exception:
            pass
