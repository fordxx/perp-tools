"""
OKX Compatibility Layer for LighterClient

This module provides OKX-compatible methods to wrap LighterClient functionality,
allowing it to work with main.py which expects OKX-style interfaces.
"""

import logging
import time
from typing import Any

from perpbot.exchanges.lighter import LighterClient
from perpbot.models import OrderRequest

logger = logging.getLogger("uvicorn.error")

_DEFAULT_TICK = "0.0001"
_DEFAULT_LOT = "1"


def add_okx_compat_methods(lighter_client: LighterClient) -> None:
    """
    Monkey-patch OKX-compatible methods onto a LighterClient instance.

    This allows LighterClient to work with code that expects OKX interfaces.
    """
    if not hasattr(lighter_client, "_orig_get_instrument_info"):
        setattr(lighter_client, "_orig_get_instrument_info", lighter_client.get_instrument_info)

    def _get_store() -> dict[str, dict[str, dict[str, Any]]]:
        store = getattr(lighter_client, "_okx_compat_state", None)
        if store is None:
            store = {"cl_to_order": {}, "order_meta": {}, "protective_by_key": {}}
            setattr(lighter_client, "_okx_compat_state", store)
        return store

    def _inst_to_symbol(inst_id: str) -> str:
        return inst_id.replace("-SWAP", "").replace("-", "/")

    def place_order(*, inst_id: str, td_mode: str, side: str, pos_side: str,
                    ord_type: str, sz: str, px: str | None, cl_ord_id: str | None = None,
                    sl_trigger_px: str | None = None, tp_trigger_px: str | None = None,
                    reduce_only: bool = False, **kwargs) -> dict:
        """OKX-compatible place_order interface."""
        symbol = _inst_to_symbol(inst_id)
        size = float(sz)
        limit_price = float(px) if px else None

        request = OrderRequest(symbol=symbol, side=side, size=size, limit_price=limit_price)

        if reduce_only:
            positions = lighter_client.get_account_positions()
            target_pos = next((p for p in positions if p.order.symbol == symbol), None)
            if target_pos:
                order = lighter_client.place_close_order(target_pos, limit_price or 0.0)
            else:
                return {"code": "51000", "msg": "No position", "data": []}
        else:
            order = lighter_client.place_open_order(request)

        if order.id.startswith(("error", "rejected")):
            return {"code": "50000", "msg": f"Order failed: {order.id}", "data": []}

        store = _get_store()
        meta_price = limit_price
        if meta_price is None:
            try:
                quote = lighter_client.get_current_price(symbol)
                if side == "buy":
                    meta_price = quote.ask or quote.mid
                else:
                    meta_price = quote.bid or quote.mid
            except Exception:
                meta_price = None
        resolved_cl = cl_ord_id or order.id
        store["cl_to_order"][resolved_cl] = order.id
        store["order_meta"][order.id] = {
            "order_id": order.id,
            "cl_ord_id": resolved_cl,
            "inst_id": inst_id,
            "symbol": symbol,
            "side": side,
            "pos_side": pos_side,
            "ord_type": ord_type,
            "sz": size,
            "px": meta_price,
            "ts": time.time(),
        }

        return {
            "code": "0",
            "msg": "",
            "data": [{
                "ordId": order.id,
                "clOrdId": cl_ord_id or order.id,
                "sCode": "0",
                "sMsg": ""
            }]
        }

    def get_order(*, inst_id: str, cl_ord_id: str | None = None, ord_id: str | None = None) -> dict | None:
        """
        OKX-compatible get_order interface.

        Lighter doesn't have a simple query-by-id API, so we return a minimal stub.
        Main.py gracefully handles None returns for missing orders.
        """
        store = _get_store()
        order_id = ord_id or (store["cl_to_order"].get(cl_ord_id or ""))
        if not order_id:
            logger.debug("get_order stub called: %s cl=%s ord=%s (not found)", inst_id, cl_ord_id, ord_id)
            return None
        meta = store["order_meta"].get(order_id)
        if not meta:
            return None
        state = "filled" if meta.get("ord_type") == "market" else "live"
        avg_px = meta.get("px")
        acc_fill_sz = meta.get("sz") if state == "filled" else 0
        return {
            "instId": inst_id,
            "clOrdId": meta.get("cl_ord_id"),
            "ordId": order_id,
            "state": state,
            "avgPx": avg_px,
            "accFillSz": acc_fill_sz,
            "sz": meta.get("sz"),
        }

    def place_algo_order(*, inst_id: str, td_mode: str, side: str, pos_side: str,
                        ord_type: str, sz: str, sl_trigger_px: str | None = None,
                        sl_ord_px: str | None = None, tp_trigger_px: str | None = None,
                        tp_ord_px: str | None = None, **kwargs) -> dict:
        """OKX-compatible place_algo_order for stop-loss and take-profit orders."""
        symbol = _inst_to_symbol(inst_id)
        size = float(sz)

        try:
            if sl_trigger_px:
                # Stop loss order
                trigger_price = float(sl_trigger_px)
                limit_price = float(sl_ord_px) if sl_ord_px and sl_ord_px != "-1" else None

                order = lighter_client.place_stop_loss(
                    symbol=symbol,
                    side=side,
                    size=size,
                    trigger_price=trigger_price,
                    limit_price=limit_price
                )

                if order.id.startswith("error"):
                    return {"code": "50000", "msg": f"SL failed: {order.id}", "data": []}

                store = _get_store()
                key = f"{inst_id}:{pos_side}"
                protect = store["protective_by_key"].setdefault(key, {"sl": [], "tp": []})
                protect["sl"] = [order.id]

                return {
                    "code": "0",
                    "msg": "",
                    "data": [{
                        "algoId": order.id,
                        "sCode": "0",
                        "sMsg": ""
                    }]
                }

            elif tp_trigger_px:
                # Take profit order
                trigger_price = float(tp_trigger_px)
                limit_price = float(tp_ord_px) if tp_ord_px and tp_ord_px != "-1" else None

                order = lighter_client.place_take_profit(
                    symbol=symbol,
                    side=side,
                    size=size,
                    trigger_price=trigger_price,
                    limit_price=limit_price
                )

                if order.id.startswith("error"):
                    return {"code": "50000", "msg": f"TP failed: {order.id}", "data": []}

                store = _get_store()
                key = f"{inst_id}:{pos_side}"
                protect = store["protective_by_key"].setdefault(key, {"sl": [], "tp": []})
                protect["tp"].append(order.id)

                return {
                    "code": "0",
                    "msg": "",
                    "data": [{
                        "algoId": order.id,
                        "sCode": "0",
                        "sMsg": ""
                    }]
                }

            else:
                return {"code": "51000", "msg": "Missing trigger price", "data": []}

        except Exception as e:
            logger.error(f"place_algo_order failed: {e}", exc_info=True)
            return {"code": "50000", "msg": str(e), "data": []}

    def cancel_order(*, inst_id: str | None = None, cl_ord_id: str | None = None,
                     order_id: str | None = None, **kwargs) -> dict:
        """OKX-compatible cancel_order interface."""
        store = _get_store()
        resolved_order_id = order_id or store["cl_to_order"].get(cl_ord_id or "")
        symbol = _inst_to_symbol(inst_id) if inst_id else None
        if not resolved_order_id:
            msg = "missing_order_id"
            logger.warning("cancel_order skipped: %s inst_id=%s cl=%s", msg, inst_id, cl_ord_id)
            return {"code": "51000", "msg": msg, "data": []}
        try:
            lighter_client.cancel_order(order_id=resolved_order_id, symbol=symbol)
            store["order_meta"].pop(resolved_order_id, None)
            for protect in store.get("protective_by_key", {}).values():
                for key in ("sl", "tp"):
                    if resolved_order_id in protect.get(key, []):
                        protect[key] = [oid for oid in protect.get(key, []) if oid != resolved_order_id]
            return {
                "code": "0",
                "msg": "",
                "data": [{
                    "ordId": resolved_order_id,
                    "clOrdId": cl_ord_id or resolved_order_id,
                    "sCode": "0",
                    "sMsg": ""
                }]
            }
        except Exception as e:
            logger.error("cancel_order failed: inst_id=%s cl=%s ord=%s err=%s", inst_id, cl_ord_id, resolved_order_id, e)
            return {
                "code": "50000",
                "msg": str(e),
                "data": [{
                    "ordId": resolved_order_id,
                    "clOrdId": cl_ord_id or resolved_order_id,
                    "sCode": "50000",
                    "sMsg": str(e)
                }]
            }

    def get_instrument_info(*, inst_id: str) -> dict:
        """
        OKX-compatible get_instrument_info interface.

        Returns contract specifications in OKX format.
        """
        try:
            orig = getattr(lighter_client, "_orig_get_instrument_info", None)
            info = orig(inst_id=inst_id) if callable(orig) else None
            if info:
                return {
                    "instId": inst_id,
                    "ctVal": info.get("ctVal", "1"),
                    "lotSz": info.get("lotSz", _DEFAULT_LOT),
                    "lotStep": info.get("lotStep", _DEFAULT_LOT),
                    "tickSz": info.get("tickSz", _DEFAULT_TICK),
                    "minSz": info.get("lotSz", _DEFAULT_LOT),
                }
        except Exception as e:
            logger.error("get_instrument_info failed: %s", e, exc_info=True)
        return {
            "instId": inst_id,
            "ctVal": "1",
            "lotSz": _DEFAULT_LOT,
            "lotStep": _DEFAULT_LOT,
            "tickSz": _DEFAULT_TICK,
            "minSz": _DEFAULT_LOT,
        }

    def get_last_price(*, inst_id: str) -> float:
        """OKX-compatible get_last_price interface."""
        symbol = _inst_to_symbol(inst_id)

        try:
            quote = lighter_client.get_current_price(symbol)
            return quote.mid
        except Exception as e:
            logger.error(f"get_last_price failed for {symbol}: {e}")
            return 0.0

    # Monkey-patch methods onto the instance
    lighter_client.place_order = place_order
    lighter_client.get_order = get_order
    lighter_client.place_algo_order = place_algo_order
    lighter_client.cancel_order = cancel_order
    lighter_client.get_instrument_info = get_instrument_info
    lighter_client.get_last_price = get_last_price

    logger.info("✅ OKX compatibility layer applied to LighterClient")
