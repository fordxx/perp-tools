"""Extended DEX client for tw168 - simplified version without perpbot dependencies."""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fast_stark_crypto.lib import get_public_key
from x10.perpetual.accounts import StarkPerpetualAccount
from x10.perpetual.configuration import EndpointConfig, MAINNET_CONFIG, TESTNET_CONFIG
from x10.perpetual.markets import MarketModel
from x10.perpetual.order_object import OrderTpslTriggerParam
from x10.perpetual.orders import OrderPriceType, OrderSide, OrderTpslType, OrderTriggerPriceType, TimeInForce
from x10.perpetual.positions import PositionSide
from x10.perpetual.trading_client import PerpetualTradingClient

from app.risk import Candle


class ExtendedClient:
    """Simplified Extended client for tw168."""

    def __init__(self, use_testnet: bool = False) -> None:
        self.use_testnet = use_testnet
        self.api_key: Optional[str] = None
        self.stark_private_key: Optional[str] = None
        self.vault_number: Optional[str] = None

        self._endpoint_config: EndpointConfig = TESTNET_CONFIG if use_testnet else MAINNET_CONFIG
        self._stark_account: Optional[StarkPerpetualAccount] = None
        self._trading_client: Optional[PerpetualTradingClient] = None
        self._markets: Dict[str, MarketModel] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    def connect(self) -> None:
        """Load credentials and initialize trading client."""
        load_dotenv()

        self.api_key = os.getenv("EXTENDED_API_KEY")
        self.stark_private_key = os.getenv("EXTENDED_STARK_PRIVATE_KEY")
        self.vault_number = os.getenv("EXTENDED_VAULT_NUMBER")

        env = os.getenv("EXTENDED_ENV", "testnet").lower()
        self.use_testnet = env == "testnet"
        self._endpoint_config = TESTNET_CONFIG if self.use_testnet else MAINNET_CONFIG

        if not (self.stark_private_key and self.vault_number and self.api_key):
            raise ValueError("Extended credentials missing")

        public_hex = hex(get_public_key(int(self.stark_private_key, 16)))
        self._stark_account = StarkPerpetualAccount(
            vault=int(self.vault_number, 0),
            private_key=self.stark_private_key,
            public_key=public_hex,
            api_key=self.api_key,
        )

        self._trading_client = PerpetualTradingClient(
            endpoint_config=self._endpoint_config,
            stark_account=self._stark_account,
        )

        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._loop_thread.start()

        self._load_markets()

    @property
    def stream_url(self) -> str:
        return self._endpoint_config.stream_url

    def _run_async(self, coro: Any) -> Any:
        """Run async coroutine in the dedicated loop thread."""
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
            self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True)
            self._loop_thread.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=30)

    def close(self) -> None:
        """Best-effort cleanup to avoid aiohttp session warnings."""
        if self._trading_client is not None:
            try:
                self._run_async(self._trading_client.close())
            except Exception as e:
                print(f"Error closing trading client: {e}")
        if self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception as e:
                print(f"Error stopping event loop: {e}")
        if self._loop_thread is not None:
            try:
                self._loop_thread.join(timeout=2)
            except Exception as e:
                print(f"Error joining loop thread: {e}")

    def _load_markets(self) -> None:
        """Load market information from Extended."""
        if not self._trading_client:
            return
        try:
            response = self._run_async(self._trading_client.markets_info.get_markets())
            if response.data:
                self._markets = {m.name: m for m in response.data}
                print(f"Extended markets loaded: {len(self._markets)}")
        except Exception as e:
            print(f"Failed to load markets: {e}")

    def _round_price(self, market: MarketModel, price: Decimal) -> Decimal:
        round_fn = getattr(market.trading_config, "round_price", None)
        if callable(round_fn):
            try:
                return Decimal(str(round_fn(price)))
            except Exception:
                return price
        return price

    def _price_bounds(
        self, market: MarketModel, ref_price: Decimal | None
    ) -> tuple[Decimal, Decimal] | None:
        cap = getattr(market.trading_config, "limit_price_cap", None)
        floor = getattr(market.trading_config, "limit_price_floor", None)
        if cap is None or floor is None:
            return None
        try:
            cap_val = Decimal(str(cap))
            floor_val = Decimal(str(floor))
        except Exception:
            return None
        if ref_price is None:
            return None
        # If caps are <= 1, treat them as percentage bounds around reference price.
        if cap_val <= 1 and floor_val <= 1:
            upper = ref_price * (Decimal("1") + cap_val)
            lower = ref_price * (Decimal("1") - floor_val)
        else:
            lower = floor_val
            upper = cap_val
        # Validate bounds
        if upper <= lower:
            print(f"WARNING: Invalid price bounds upper={upper} <= lower={lower}, using defaults")
            return None
        return lower, upper

    def _clamp_price(self, market: MarketModel, price: Decimal, ref_price: Decimal | None) -> Decimal:
        bounds = self._price_bounds(market, ref_price)
        if not bounds:
            return price
        lower, upper = bounds
        if price > upper:
            return upper
        if price < lower:
            return lower
        return price

    def _round_price_with(self, market: MarketModel, price: Decimal, rounding: str) -> Decimal:
        min_change = getattr(market.trading_config, "min_price_change", None)
        if min_change is None:
            return self._round_price(market, price)
        try:
            return Decimal(str(price)).quantize(Decimal(str(min_change)), rounding=rounding)
        except Exception:
            return self._round_price(market, price)

    def _normalize_price(
        self, market: MarketModel, price: Decimal, ref_price: Decimal | None
    ) -> Decimal:
        if ref_price is None:
            ref_price = price
        bounds = self._price_bounds(market, ref_price)
        if bounds:
            lower, upper = bounds
            if price >= upper:
                price = self._round_price_with(market, upper, ROUND_FLOOR)
            elif price <= lower:
                price = self._round_price_with(market, lower, ROUND_CEILING)
            else:
                price = self._round_price(market, price)
        else:
            price = self._round_price(market, price)
        if price <= 0:
            min_change = getattr(market.trading_config, "min_price_change", None)
            if min_change is not None:
                price = Decimal(str(min_change))
        return price

    def _price_debug(self, message: str) -> None:
        if os.getenv("EXTENDED_PRICE_DEBUG", "").lower() in {"1", "true", "yes"}:
            print(message)

    def _get_market_stats(self, symbol: str, market: MarketModel) -> dict[str, Decimal | None]:
        stats = getattr(market, "market_stats", None)
        data = {
            "last": getattr(stats, "last_price", None) if stats else None,
            "mark": getattr(stats, "mark_price", None) if stats else None,
            "ask": getattr(stats, "ask_price", None) if stats else None,
            "bid": getattr(stats, "bid_price", None) if stats else None,
        }
        if any(value is not None for value in data.values()):
            return data
        if not self._trading_client:
            return data
        try:
            response = self._run_async(
                self._trading_client.markets_info.get_market_statistics(market_name=symbol)
            )
            if response.data:
                data["last"] = response.data.last_price
                data["mark"] = response.data.mark_price
                data["ask"] = response.data.ask_price
                data["bid"] = response.data.bid_price
        except Exception:
            pass
        return data

    def _select_reference_price(
        self, *, side: str, market: MarketModel, symbol: str
    ) -> Decimal | None:
        stats = self._get_market_stats(symbol, market)
        ref_val = None
        if side == "buy":
            ref_val = stats.get("ask") or stats.get("mark") or stats.get("last") or stats.get("bid")
        else:
            ref_val = stats.get("bid") or stats.get("mark") or stats.get("last") or stats.get("ask")
        if ref_val is None:
            return None
        return Decimal(str(ref_val))

    def get_instrument_info(self, *, inst_id: str) -> dict[str, Any] | None:
        """Get market info (similar to OKX get_instrument_info)."""
        symbol = inst_id.replace("-USDT-SWAP", "-USD")

        market = self._markets.get(symbol)
        if not market:
            return None

        return {
            "instId": symbol,
            "ctVal": "1",
            "lotSz": str(market.trading_config.min_order_size),
            "lotStep": str(market.trading_config.min_order_size_change),
            "tickSz": str(market.trading_config.min_price_change),
        }

    def get_last_price(self, *, inst_id: str) -> float | None:
        symbol = inst_id.replace("-USDT-SWAP", "-USD")
        market = self._markets.get(symbol)
        if not market or not self._trading_client:
            return None

        try:
            response = self._run_async(
                self._trading_client.markets_info.get_market_statistics(market_name=symbol)
            )
            if response.data:
                return float(response.data.last_price)
        except Exception:
            return None

    def fetch_candles(self, *, inst_id: str, tf: str, limit: int = 300) -> list[Candle]:
        symbol = inst_id.replace("-USDT-SWAP", "-USD")
        if not self._trading_client:
            return []

        interval_map = {
            "1m": "PT1M",
            "5m": "PT5M",
            "15m": "PT15M",
            "30m": "PT30M",
            "1h": "PT1H",
            "2h": "PT2H",
            "4h": "PT4H",
            "1d": "P1D",
        }
        key = tf.strip().lower()
        interval = interval_map.get(key, "PT1M")

        try:
            response = self._run_async(
                self._trading_client.markets_info.get_candles_history(
                    market_name=symbol,
                    candle_type="trades",
                    interval=interval,  # type: ignore[arg-type]
                    limit=limit,
                )
            )
            data = response.data or []
            candles = [
                Candle(
                    ts_ms=int(row.timestamp),
                    o=float(row.open),
                    h=float(row.high),
                    l=float(row.low),
                    c=float(row.close),
                )
                for row in data
            ]
            candles.sort(key=lambda c: c.ts_ms)
            return candles
        except Exception:
            return []

    def get_order(self, *, inst_id: str, cl_ord_id: str) -> dict[str, Any] | None:
        return None

    def get_position(self, *, inst_id: str, pos_side: str) -> dict[str, Any] | None:
        if not self._trading_client:
            return None
        symbol = inst_id.replace("-USDT-SWAP", "-USD")
        side = PositionSide.LONG if pos_side.lower() == "long" else PositionSide.SHORT
        try:
            response = self._run_async(
                self._trading_client.account.get_positions(market_names=[symbol], position_side=side)
            )
            data = response.data or []
            for pos in data:
                if getattr(pos, "market", None) != symbol:
                    continue
                size = getattr(pos, "size", None)
                try:
                    size_val = Decimal(str(size))
                except Exception:
                    size_val = Decimal("0")
                if size_val <= 0:
                    continue
                sl_price = None
                tp_price = None
                for key in ("sl_price", "stop_loss_price", "stop_loss", "sl"):
                    raw = getattr(pos, key, None)
                    if raw is None:
                        continue
                    if isinstance(raw, (int, float, Decimal, str)):
                        sl_price = raw
                        break
                    raw_price = getattr(raw, "trigger_price", None) or getattr(raw, "price", None)
                    if raw_price is not None:
                        sl_price = raw_price
                        break
                for key in ("tp_price", "take_profit_price", "take_profit", "tp"):
                    raw = getattr(pos, key, None)
                    if raw is None:
                        continue
                    if isinstance(raw, (int, float, Decimal, str)):
                        tp_price = raw
                        break
                    raw_price = getattr(raw, "trigger_price", None) or getattr(raw, "price", None)
                    if raw_price is not None:
                        tp_price = raw_price
                        break
                return {
                    "instId": inst_id,
                    "posSide": pos_side,
                    "pos": str(size_val),
                    "market": symbol,
                    "open_price": getattr(pos, "open_price", None),
                    "sl_price": sl_price,
                    "tp_price": tp_price,
                    "raw": pos,
                }
        except Exception:
            return None
        return None

    def get_open_orders(self, *, inst_id: str) -> list[dict[str, Any]]:
        if not self._trading_client:
            return []
        symbol = inst_id.replace("-USDT-SWAP", "-USD")
        try:
            response = self._run_async(
                self._trading_client.account.get_open_orders(market_names=[symbol])
            )
            data = response.data or []
            out: list[dict[str, Any]] = []
            for order in data:
                if getattr(order, "market", None) != symbol:
                    continue
                out.append(
                    {
                        "id": getattr(order, "id", None),
                        "external_id": getattr(order, "external_id", None),
                        "side": getattr(order, "side", None),
                        "type": getattr(order, "type", None),
                        "status": getattr(order, "status", None),
                        "reduce_only": getattr(order, "reduce_only", None),
                        "price": getattr(order, "price", None),
                        "tp_sl_type": getattr(order, "tp_sl_type", None),
                        "take_profit": getattr(order, "take_profit", None),
                        "stop_loss": getattr(order, "stop_loss", None),
                    }
                )
            return out
        except Exception:
            return []

    def place_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        px: str | None,
        cl_ord_id: str,
        sl_trigger_px: str | None,
        tp_trigger_px: str | None,
        reduce_only: bool = False,
    ) -> Any:
        """Place order on Extended."""
        symbol = inst_id.replace("-USDT-SWAP", "-USD")
        market = self._markets.get(symbol)
        if not market:
            return {"code": "1", "msg": f"Market {symbol} not found"}

        if not self._trading_client:
            return {"code": "1", "msg": "Trading client not initialized"}

        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        time_in_force = TimeInForce.IOC if ord_type == "market" else TimeInForce.GTT

        ref_price = None
        if ord_type == "market":
            if not px:
                ref_price = self._select_reference_price(side=side, market=market, symbol=symbol)
                if ref_price is None:
                    price = Decimal("100000") if side == "buy" else Decimal("0.01")
                else:
                    # Use the current reference price for IOC orders to avoid
                    # invalid limit values on Extended.
                    price = ref_price
            else:
                ref_price = Decimal(str(px))
                price = ref_price
            price = self._normalize_price(market, price, ref_price)
        else:
            if not px:
                return {"code": "1", "msg": "Limit orders require price"}
            price = Decimal(str(px))
            ref_price = price
            price = self._normalize_price(market, price, ref_price)

        self._price_debug(
            "extended price_debug symbol="
            f"{symbol} ord_type={ord_type} side={side} price={price} ref={ref_price} "
            f"cap={getattr(market.trading_config, 'limit_price_cap', None)} "
            f"floor={getattr(market.trading_config, 'limit_price_floor', None)} "
            f"tick={getattr(market.trading_config, 'min_price_change', None)}"
        )

        tp_param = None
        if tp_trigger_px:
            tp_price = self._normalize_price(market, Decimal(str(tp_trigger_px)), ref_price)
            tp_param = OrderTpslTriggerParam(
                trigger_price=tp_price,
                trigger_price_type=OrderTriggerPriceType.LAST,
                price=tp_price,
                price_type=OrderPriceType.LIMIT,
            )

        sl_param = None
        if sl_trigger_px:
            sl_price = self._normalize_price(market, Decimal(str(sl_trigger_px)), ref_price)
            sl_param = OrderTpslTriggerParam(
                trigger_price=sl_price,
                trigger_price_type=OrderTriggerPriceType.LAST,
                price=sl_price,
                price_type=OrderPriceType.MARKET,
            )

        try:
            tp_sl_type = OrderTpslType.ORDER if (tp_param or sl_param) else None
            expire_time = None
            if time_in_force == TimeInForce.GTT:
                expire_hours = float(os.getenv("EXTENDED_ORDER_EXPIRE_HOURS", "168"))
                expire_time = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
            response = self._run_async(
                self._trading_client.place_order(
                    market_name=symbol,
                    amount_of_synthetic=Decimal(str(sz)),
                    price=price,
                    side=order_side,
                    post_only=False,
                    time_in_force=time_in_force,
                    expire_time=expire_time,
                    reduce_only=reduce_only,
                    tp_sl_type=tp_sl_type,
                    take_profit=tp_param,
                    stop_loss=sl_param,
                )
            )

            order_id = str(
                response.data.external_id
                if response.data and response.data.external_id
                else response.data.id if response.data else "unknown"
            )

            return {
                "code": "0",
                "msg": "",
                "data": [
                    {
                        "ordId": order_id,
                        "clOrdId": cl_ord_id,
                        "sCode": "0",
                        "sMsg": "",
                    }
                ],
            }
        except Exception as e:
            return {"code": "1", "msg": str(e)}

    def place_algo_order(
        self,
        *,
        inst_id: str,
        td_mode: str,
        side: str,
        pos_side: str,
        ord_type: str,
        sz: str,
        sl_trigger_px: str | None = None,
        sl_ord_px: str | None = None,
        tp_trigger_px: str | None = None,
        tp_ord_px: str | None = None,
    ) -> Any:
        return {
            "code": "0",
            "data": [
                {
                    "algoId": "extended_sl_not_implemented",
                    "sCode": "0",
                    "sMsg": "Extended SL/TP handled by entry TPSL",
                }
            ],
            "msg": "",
        }
