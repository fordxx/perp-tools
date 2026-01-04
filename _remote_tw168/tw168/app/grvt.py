from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Literal

from pysdk.grvt_ccxt_pro import GrvtCcxtPro
from pysdk.grvt_ccxt_env import GrvtEnv, get_grvt_endpoint
from pysdk.grvt_ccxt_types import GrvtOrderSide, GrvtOrderType
from pysdk.grvt_ccxt_utils import get_grvt_order, get_order_payload

from app.risk import Candle


Side = Literal["buy", "sell"]
PosSide = Literal["long", "short"]


@dataclass(frozen=True)
class GrvtCredentials:
    api_key: str
    private_key: str
    trading_account_id: str


class GrvtClient:
    """GRVT exchange client for perpetual futures trading."""

    def __init__(self, base_url: str, creds: GrvtCredentials, *, enable_rate_limit: bool = True) -> None:
        self.base_url = base_url.rstrip("/")
        self.creds = creds
        self.trading_account_id = creds.trading_account_id
        self.enable_rate_limit = enable_rate_limit
        self.logger = logging.getLogger("uvicorn.error")

        # Initialize GRVT CCXT Pro client
        self.env = GrvtEnv.TESTNET if "testnet" in base_url.lower() else GrvtEnv.PROD
        self.api = GrvtCcxtPro(
            env=self.env,
            parameters={
                "api_key": creds.api_key,
                "private_key": creds.private_key,
                "trading_account_id": creds.trading_account_id,
            },
            logger=self.logger,
        )

    async def connect(self) -> None:
        """Initialize connection and load markets."""
        try:
            await self.api.load_markets()
            self.logger.info(f"GRVT client connected, loaded {len(self.api.markets)} markets")
        except Exception as e:
            self.logger.error(f"GRVT client connection failed: {e}")
            raise

    def close(self) -> None:
        """Close the client connection."""
        try:
            if hasattr(self.api, 'close'):
                asyncio.run(self.api.close())
        except Exception as e:
            self.logger.warning(f"Error closing GRVT client: {e}")

    def _normalize_symbol(self, inst_id: str) -> str:
        """Convert TradingView symbol to GRVT format."""
        # GRVT uses symbols like: BTC_USDT_Perp
        inst = (inst_id or "").strip()
        if inst.endswith("-USDT-SWAP"):
            base = inst[: -len("-USDT-SWAP")]
            return f"{base}_USDT_Perp"
        # Support common variants: BTC-USDT, BTC/USDT, BTC_USDT
        inst = inst.replace("/", "_").replace("-", "_")
        if inst.endswith("_USDT"):
            return f"{inst}_Perp"
        if not inst.endswith("_Perp"):
            # If it ends with _PERP (uppercase), convert to _Perp
            if inst.endswith("_PERP"):
                return inst[:-5] + "_Perp"
            return f"{inst}_Perp"
        return inst

    def _resolve_symbol(self, inst_id: str) -> str:
        """Resolve symbol against GRVT markets (handles k-prefixed symbols)."""
        symbol = self._normalize_symbol(inst_id)
        markets = getattr(self.api, "markets", None) or {}
        if symbol in markets:
            return symbol
        # Some meme coins use a k-prefixed symbol on GRVT (e.g., KBONK).
        if symbol.endswith("_USDT_Perp"):
            base = symbol[: -len("_USDT_Perp")]
            alt = f"K{base}_USDT_Perp"
            if alt in markets:
                self.logger.info("GRVT symbol mapping %s -> %s", symbol, alt)
                return alt
        return symbol

    def _normalize_tick_size(self, tick_size: str | float | int | None) -> Decimal | None:
        """Normalize tick size values from CCXT/GRVT into a Decimal tick."""
        if tick_size is None:
            return None
        try:
            tick_dec = Decimal(str(tick_size))
        except Exception:
            return None
        if tick_dec <= 0:
            return None
        # CCXT often provides price precision as decimal places (e.g., 4).
        if tick_dec == tick_dec.to_integral_value() and tick_dec <= 18:
            return Decimal(1) / (Decimal(10) ** int(tick_dec))
        return tick_dec

    def _round_price(self, price: float, tick_size: str | None) -> str:
        """Round price to GRVT tick size (9 decimal places)."""
        tick = self._normalize_tick_size(tick_size)
        if tick:
            try:
                price_dec = Decimal(str(price))
                rounded = (price_dec / tick).to_integral_value(rounding=ROUND_DOWN) * tick
                return format(rounded, "f").rstrip("0").rstrip(".")
            except Exception:
                pass
        # Default to 9 decimal places for GRVT
        return f"{price:.9f}".rstrip("0").rstrip(".")

    async def get_last_price(self, *, inst_id: str) -> float | None:
        """Get last price for instrument."""
        try:
            symbol = self._resolve_symbol(inst_id)
            ticker = await self.api.fetch_ticker(symbol)
            if not ticker:
                return None
            # GRVT returns 'last_price' rather than CCXT 'last'
            for key in ("last", "last_price", "lastPrice", "last_px", "lastPriceStr"):
                if key in ticker and ticker.get(key) is not None and ticker.get(key) != "":
                    try:
                        return float(ticker.get(key))
                    except Exception:
                        continue
            # Fallback: try common alternate keys
            if "last_price" in ticker:
                try:
                    return float(ticker.get("last_price"))
                except Exception:
                    return None
            return None
        except Exception as e:
            self.logger.warning(f"GRVT get_last_price failed for {inst_id}: {e}")
            return None

    async def get_position(self, *, inst_id: str, pos_side: str) -> dict[str, Any] | None:
        """Get position for instrument and side."""
        try:
            symbol = self._resolve_symbol(inst_id)
            positions = await self.api.fetch_positions(
                symbols=[symbol], params={"trading_account_id": self.trading_account_id}
            )
            for pos in positions:
                pos_symbol = pos.get("symbol") or pos.get("instrument") or pos.get("inst")
                if pos_symbol == symbol:
                    # GRVT positions don't have posSide, determine from size
                    raw_size = pos.get("contracts")
                    if raw_size is None:
                        raw_size = pos.get("size")
                    if raw_size is None:
                        raw_size = pos.get("position")
                    size = float(raw_size or 0)
                    if size == 0:
                        continue
                    actual_side = "long" if size > 0 else "short"
                    if actual_side == pos_side.lower():
                        return {
                            "instId": inst_id,
                            "posSide": pos_side,
                            "pos": str(abs(size)),
                            "avgPx": pos.get("entryPrice")
                            or pos.get("entry_price")
                            or pos.get("avgPx")
                            or "0",
                            "markPx": pos.get("markPrice")
                            or pos.get("mark_price")
                            or pos.get("markPx")
                            or "0",
                            "liqPx": pos.get("liquidationPrice")
                            or pos.get("est_liquidation_price")
                            or pos.get("liqPx")
                            or "0",
                            "margin": pos.get("margin")
                            or pos.get("margin_size")
                            or "0",
                            "pnl": pos.get("unrealizedPnl")
                            or pos.get("unrealized_pnl")
                            or "0",
                        }
            return None
        except Exception as e:
            self.logger.warning(f"GRVT get_position failed for {inst_id}: {e}")
            return None

    async def get_instrument_info(self, *, inst_id: str) -> dict[str, Any] | None:
        """Get instrument information with minQuote support."""
        try:
            symbol = self._resolve_symbol(inst_id)
            market = self.api.markets.get(symbol)
            if market:
                # GRVT market entries use a custom schema with tick_size/min_size.
                tick_raw = market.get("tick_size")
                min_size_raw = market.get("min_size")

                limits = market.get("limits", {})
                cost_limits = limits.get("cost", {})
                amount_limits = limits.get("amount", {})
                precision = market.get("precision", {})

                # Extract minimum order value (minQuote)
                min_quote = cost_limits.get("min", "5")  # GRVT default 5 USDT

                # Get actual tick size from market precision or tick_size field.
                tick_sz = self._normalize_tick_size(tick_raw) or self._normalize_tick_size(precision.get("price"))
                if tick_sz is None:
                    tick_sz = Decimal("0.000000001")  # Fallback to 9 decimal places
                tick_sz = format(tick_sz, "f").rstrip("0").rstrip(".")

                # Use min_size as both min size and step when provided by GRVT.
                min_size = None
                if min_size_raw is not None:
                    try:
                        min_size = Decimal(str(min_size_raw))
                    except Exception:
                        min_size = None

                lot_step = min_size if min_size and min_size > 0 else Decimal(str(market.get("contractSize", "1")))
                min_sz = min_size if min_size and min_size > 0 else Decimal(str(amount_limits.get("min", "0.001")))

                return {
                    "instId": symbol,
                    "ctVal": "1",  # GRVT perpetuals have 1 contract value
                    "lotSz": str(min_sz),
                    "lotStep": str(lot_step),
                    "tickSz": tick_sz,  # Use actual tick size from market
                    "minSz": str(min_sz),
                    "minQuote": str(min_quote),  # New field: minimum order value
                }
            return None
        except Exception as e:
            self.logger.warning(f"GRVT get_instrument_info failed for {inst_id}: {e}")
            return None

    async def place_order(
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
        sl_trigger_px: str | None = None,
        tp_trigger_px: str | None = None,
        reduce_only: bool = False,
    ) -> Any:
        """Place order on GRVT."""
        try:
            symbol = self._resolve_symbol(inst_id)

            # GRVT API expects string sides and order types (use lowercase)
            order_side = str(side).lower()
            order_type = str(ord_type).lower() if str(ord_type).lower() in {"market", "limit"} else "limit"

            amount = Decimal(str(sz))
            price = Decimal(str(px)) if px else None

            # GRVT requires numeric client_order_id: extract digits or hash
            if cl_ord_id.isdigit():
                client_order_id_int = int(cl_ord_id)
            else:
                # Remove non-digits and convert, or use abs(hash) as fallback
                digits_only = ''.join(c for c in cl_ord_id if c.isdigit())
                client_order_id_int = int(digits_only) if digits_only else abs(hash(cl_ord_id)) % (10**15)

            params = {
                "client_order_id": client_order_id_int,
                "reduce_only": reduce_only,
                "trading_account_id": self.trading_account_id,
            }

            # Handle TP/SL orders
            if sl_trigger_px or tp_trigger_px:
                # GRVT supports trigger orders via conditional orders
                if sl_trigger_px:
                    params["stopLossPrice"] = float(sl_trigger_px)
                if tp_trigger_px:
                    params["takeProfitPrice"] = float(tp_trigger_px)
                # Use conditional order type for TP/SL
                order_type = GrvtOrderType.LIMIT  # GRVT handles triggers differently

            response = await self.api.create_order(
                symbol=symbol,
                order_type=order_type,
                side=order_side,
                amount=amount,
                price=price,
                params=params,
            )

            if response:
                return {
                    "code": "0",
                    "msg": "",
                    "data": [
                        {
                            "ordId": response.get("id", ""),
                            "clOrdId": cl_ord_id,
                            "sCode": "0",
                            "sMsg": "",
                        }
                    ],
                }
            else:
                return {"code": "1", "msg": "Order creation failed"}

        except Exception as e:
            self.logger.error(f"GRVT place_order failed: {e}")
            return {"code": "1", "msg": str(e)}

    async def place_algo_order(
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
        """Place algorithmic order with min_quote validation."""
        try:
            symbol = self._resolve_symbol(inst_id)
            order_side = str(side).lower()
            amount = Decimal(str(sz))

            # Pre-flight validation: check min_quote requirement
            inst_info = await self.get_instrument_info(inst_id=inst_id)
            if inst_info and inst_info.get("minQuote"):
                min_quote = Decimal(str(inst_info.get("minQuote")))
                trigger_price = Decimal(str(sl_trigger_px or tp_trigger_px or 0))
                order_value = amount * trigger_price

                if order_value < min_quote:
                    self.logger.error(
                        f"GRVT order rejected pre-flight: value={order_value} < min_quote={min_quote}"
                    )
                    return {
                        "code": "min_quote_failed",
                        "msg": f"Order value {order_value} below min_quote {min_quote}",
                        "details": {
                            "order_value": float(order_value),
                            "min_quote": float(min_quote),
                            "sz": str(sz),
                            "trigger_px": str(trigger_price),
                        },
                    }

            trigger_px = sl_trigger_px or tp_trigger_px
            if not trigger_px:
                return {"code": "1", "msg": "missing_trigger_price"}

            trigger_type = "STOP_LOSS" if sl_trigger_px else "TAKE_PROFIT"

            # Build a GRVT order payload and inject trigger metadata (SDK doesn't expose this).
            client_order_id = abs(hash(f"{inst_id}:{trigger_type}:{trigger_px}")) % (10**15)
            order = get_grvt_order(
                sub_account_id=self.trading_account_id,
                symbol=symbol,
                order_type=GrvtOrderType.LIMIT,
                side=order_side,
                amount=amount,
                limit_price=Decimal(str(trigger_px)),
                params={
                    "reduce_only": True,
                    "client_order_id": client_order_id,
                },
            )
            payload = get_order_payload(
                order,
                private_key=self.creds.private_key,
                env=self.api.env,
                instruments=self.api.markets,
            )
            payload["order"].setdefault("metadata", {})["trigger"] = {
                "trigger_type": trigger_type,
                "tpsl": {
                    "trigger_by": "MARK",
                    "trigger_price": str(trigger_px),
                    "close_position": False,
                },
            }

            response = await self.api._auth_and_post(
                get_grvt_endpoint(self.api.env, "CREATE_ORDER"),
                payload=payload,
            )

            if response and response.get("result") is not None:
                return {
                    "code": "0",
                    "data": [
                        {
                            "algoId": (response.get("result") or {}).get("order_id", ""),
                            "sCode": "0",
                            "sMsg": "",
                        }
                    ],
                    "msg": "",
                }
            else:
                return {"code": "1", "msg": str(response or "Algo order creation failed")}

        except Exception as e:
            self.logger.error(f"GRVT place_algo_order failed: {e}")
            return {"code": "1", "msg": str(e)}

    async def get_order(self, *, inst_id: str, cl_ord_id: str) -> dict[str, Any] | None:
        """Get order status."""
        try:
            response = await self.api.fetch_order(
                params={"client_order_id": cl_ord_id, "trading_account_id": self.trading_account_id}
            )
            return response if response else None
        except Exception as e:
            self.logger.warning(f"GRVT get_order failed for {cl_ord_id}: {e}")
            return None

    async def cancel_order(self, *, inst_id: str, cl_ord_id: str | None = None, ord_id: str | None = None) -> Any:
        """Cancel order."""
        try:
            symbol = self._resolve_symbol(inst_id)
            params = {"trading_account_id": self.trading_account_id}
            if cl_ord_id:
                params["client_order_id"] = cl_ord_id
            elif ord_id:
                params["order_id"] = ord_id  # Changed from "id" to "order_id"
            success = await self.api.cancel_order(symbol=symbol, params=params)
            return {
                "code": "0" if success else "1",
                "msg": "",
                "data": [{"ordId": ord_id or cl_ord_id, "clOrdId": cl_ord_id}],
            }
        except Exception as e:
            self.logger.error(f"GRVT cancel_order failed: {e}")
            return {"code": "1", "msg": str(e)}

    async def cancel_all_orders(self, *, inst_id: str | None = None) -> Any:
        """Cancel all open orders, optionally for a specific instrument."""
        try:
            params = {"trading_account_id": self.trading_account_id}
            if inst_id:
                # For symbol-specific, get open orders and cancel each
                symbol = self._resolve_symbol(inst_id)
                orders = await self.api.fetch_open_orders(symbol=symbol, params=params)
                cancelled = 0
                for order in orders or []:
                    ord_id = order.get("id") or order.get("ordId")
                    if ord_id:
                        try:
                            await self.api.cancel_order(symbol=symbol, params={"id": ord_id, "trading_account_id": self.trading_account_id})
                            cancelled += 1
                        except Exception:
                            pass
                return {
                    "code": "0",
                    "msg": f"Cancelled {cancelled} orders for {inst_id}",
                }
            else:
                # Account-wide cancel
                success = await self.api.cancel_all_orders(params=params)
                return {
                    "code": "0" if success else "1",
                    "msg": "",
                }
        except Exception as e:
            self.logger.error(f"GRVT cancel_all_orders failed: {e}")
            return {"code": "1", "msg": str(e)}

    async def get_open_orders(self, *, inst_id: str) -> list[dict[str, Any]]:
        """Get open orders for instrument."""
        try:
            symbol = self._resolve_symbol(inst_id)
            orders = await self.api.fetch_open_orders(symbol=symbol, params={"trading_account_id": self.trading_account_id})
            return orders or []
        except Exception as e:
            self.logger.warning(f"GRVT get_open_orders failed for {inst_id}: {e}")
            return []

    def fetch_candles(self, *, inst_id: str, bar: str, limit: int = 300) -> list[Candle]:
        """Fetch candles - GRVT doesn't have direct candle API, return empty list."""
        # GRVT SDK doesn't provide candle data directly
        # Would need to implement via their REST API or use external source
        self.logger.warning(f"GRVT candle fetching not implemented for {inst_id}")
        return []
