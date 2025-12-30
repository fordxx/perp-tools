from __future__ import annotations

import logging
import os
from decimal import Decimal
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ParadexClient:
    """Paradex SDK wrapper (L2 private key) with a minimal OKX-style interface."""

    def __init__(self, *, use_testnet: bool = False) -> None:
        self.use_testnet = use_testnet
        self.client = None
        self._trading_enabled = False

    def connect(self) -> None:
        load_dotenv()
        l2_key = os.getenv("PARADEX_L2_PRIVATE_KEY", "")
        account = os.getenv("PARADEX_ACCOUNT_ADDRESS", "")
        env = os.getenv("PARADEX_ENV", "prod").lower()
        if self.use_testnet:
            env = "testnet"

        if not l2_key or not account:
            logger.warning("Paradex trading disabled: missing L2 key or account address")
            self._trading_enabled = False
            return

        try:
            from paradex_py import Paradex
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex SDK not installed: %s", exc)
            self._trading_enabled = False
            return

        try:
            self.client = Paradex(
                env=env,
                l2_private_key=l2_key,
                l1_address=account,
            )
            self._trading_enabled = True
            logger.info("Paradex connected env=%s account=%s...", env, account[:10])
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex connect failed: %s", exc)
            self._trading_enabled = False

    def _normalize_market(self, inst_id: str) -> str:
        raw = inst_id.strip().upper()
        if raw.endswith(".P"):
            raw = raw[:-2]
        if raw.endswith("-USDT-SWAP"):
            return f"{raw[:-10]}-USD-PERP"
        if raw.endswith("-USDT-PERP"):
            return f"{raw[:-10]}-USD-PERP"
        if raw.endswith("-USD-PERP"):
            return raw
        if raw.endswith("-SWAP"):
            raw = raw[:-5]
        if raw.endswith("TSWAP"):
            raw = raw[:-5]
        if raw.endswith("USDT"):
            base = raw[:-4].replace("/", "").replace("-", "")
            return f"{base}-USD-PERP"
        cleaned = raw.replace("/", "").replace("-", "")
        if cleaned.endswith("SWAP"):
            cleaned = cleaned[:-4]
        if cleaned.endswith("USDC"):
            base = cleaned[:-4]
        elif cleaned.endswith("USD"):
            base = cleaned[:-3]
        else:
            base = cleaned
        return f"{base}-USD-PERP"

    def get_instrument_info(self, *, inst_id: str) -> dict[str, Any] | None:
        if not self.client:
            return None
        market = self._normalize_market(inst_id)
        try:
            resp = self.client.api_client.fetch_markets({"market": market})
            results = resp.get("results", [])
            if not results:
                return None
            info = results[0]
            return {
                "tickSz": info.get("price_tick_size") or info.get("priceTickSize"),
                "lotStep": info.get("order_size_increment") or info.get("orderSizeIncrement"),
                "lotSz": info.get("order_size_increment") or info.get("orderSizeIncrement"),
                "ctVal": "1",
                "minNotional": info.get("min_notional") or info.get("minNotional"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex get_instrument_info failed inst_id=%s err=%s", inst_id, exc)
            return None

    def get_last_price(self, *, inst_id: str) -> float | None:
        if not self.client:
            return None
        market = self._normalize_market(inst_id)
        try:
            if hasattr(self.client, "fetch_bbo"):
                bbo = self.client.fetch_bbo(market)
            elif hasattr(self.client, "api_client") and hasattr(self.client.api_client, "fetch_bbo"):
                bbo = self.client.api_client.fetch_bbo(market)
            else:
                raise AttributeError("Paradex client missing fetch_bbo method")
            bid = bbo.get("bestBidPrice") or bbo.get("bid")
            ask = bbo.get("bestAskPrice") or bbo.get("ask")
            if bid is None or ask is None:
                return None
            return (float(bid) + float(ask)) / 2.0
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex get_last_price failed inst_id=%s err=%s", inst_id, exc)
            return None

    def get_position(self, *, inst_id: str, pos_side: str) -> dict[str, Any] | None:
        if not self.client:
            return None
        market = self._normalize_market(inst_id)
        try:
            if hasattr(self.client, "fetch_positions"):
                resp = self.client.fetch_positions()
            elif hasattr(self.client, "api_client") and hasattr(self.client.api_client, "fetch_positions"):
                resp = self.client.api_client.fetch_positions()
            else:
                raise AttributeError("Paradex client missing fetch_positions method")
            for pos in resp.get("results", []):
                if pos.get("market") != market:
                    continue
                size = Decimal(str(pos.get("size", "0")))
                if size == 0:
                    continue
                side = "long" if size > 0 else "short"
                if side != pos_side:
                    continue
                return {
                    "pos": str(abs(size)),
                    "avgPx": pos.get("avg_entry_price") or pos.get("avgEntryPrice"),
                }
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex get_position failed inst_id=%s err=%s", inst_id, exc)
        return None

    def get_open_orders(self, *, inst_id: str) -> list[dict[str, Any]]:
        if not self.client:
            return []
        market = self._normalize_market(inst_id)
        try:
            resp = self.client.fetch_orders(market=market)
            out: list[dict[str, Any]] = []
            for order in resp.get("results", []):
                status = (order.get("status") or "").upper()
                if status not in {"OPEN", "NEW"}:
                    continue
                out.append(
                    {
                        "ordId": order.get("id") or order.get("order_id"),
                        "type": order.get("type") or order.get("order_type"),
                        "trigger_price": order.get("trigger_price"),
                        "price": order.get("price"),
                        "size": order.get("size"),
                        "side": order.get("side"),
                        "reduce_only": "REDUCE_ONLY" in (order.get("flags") or []),
                    }
                )
            return out
        except Exception as exc:  # noqa: BLE001
            logger.error("Paradex get_open_orders failed inst_id=%s err=%s", inst_id, exc)
            return []

    def cancel_order(self, *, order_id: str) -> dict[str, Any]:
        if not self.client:
            return {"code": "1", "msg": "Paradex client not initialized"}
        try:
            resp = self.client.cancel_order(order_id)
            return {"code": "0", "msg": "", "raw": resp}
        except Exception as exc:  # noqa: BLE001
            return {"code": "1", "msg": str(exc)}

    def place_order(
        self,
        *,
        inst_id: str,
        side: str,
        ord_type: str,
        sz: str,
        px: str | None,
        cl_ord_id: str,
        reduce_only: bool = False,
        trigger_px: str | None = None,
    ) -> dict[str, Any]:
        if not self.client or not self._trading_enabled:
            return {"code": "1", "msg": "Paradex trading disabled"}

        market = self._normalize_market(inst_id)
        try:
            from paradex_py.common.order import Order, OrderSide, OrderType

            side_enum = OrderSide.Buy if side == "buy" else OrderSide.Sell
            ord_type_key = ord_type.lower()
            type_map = {
                "market": OrderType.Market,
                "limit": OrderType.Limit,
                "stop_loss_market": OrderType.StopLossMarket,
                "stop_loss_limit": OrderType.StopLossLimit,
                "take_profit_market": OrderType.TakeProfitMarket,
                "take_profit_limit": OrderType.TakeProfitLimit,
            }
            order_type = type_map.get(ord_type_key, OrderType.Market)
            limit_price = Decimal(str(px or "0"))
            trigger_price = Decimal(str(trigger_px)) if trigger_px else None

            order = Order(
                market=market,
                order_type=order_type,
                order_side=side_enum,
                size=Decimal(str(sz)),
                limit_price=limit_price,
                client_id=cl_ord_id,
                reduce_only=reduce_only,
                trigger_price=trigger_price,
            )
            if hasattr(self.client, "submit_order"):
                resp = self.client.submit_order(order)
            elif hasattr(self.client, "api_client") and hasattr(self.client.api_client, "submit_order"):
                resp = self.client.api_client.submit_order(order)
            elif hasattr(self.client, "orders") and hasattr(self.client.orders, "submit_order"):
                resp = self.client.orders.submit_order(order)
            else:
                return {"code": "1", "msg": "Paradex client missing submit_order method"}
            ord_id = resp.get("id") or resp.get("order_id") or resp.get("client_id") or "unknown"
            return {
                "code": "0",
                "msg": "",
                "data": [{"ordId": str(ord_id), "clOrdId": cl_ord_id, "sCode": "0", "sMsg": ""}],
                "raw": resp,
            }
        except Exception as exc:  # noqa: BLE001
            return {"code": "1", "msg": str(exc)}
