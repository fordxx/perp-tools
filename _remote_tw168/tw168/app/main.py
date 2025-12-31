from __future__ import annotations

import asyncio
import logging
import logging.handlers
import time
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import SETTINGS, get_lookback_bars, get_ladder_wait_candles, get_ladder_max_wait_candles, get_ladder_price_distance, tf_to_seconds
from app.charting import plot_kline
from app.candle_cache import CandleCache, CandleWsManager
from app.fill_tracker import FillTracker
from app.metrics import get_metrics
from app.notify import notify_error, notify_info, notify_photo
from app.risk import (
    detect_head_shoulders_top,
    detect_w_bottom,
    fetch_candles,
    fetch_candles_paged,
    stop_loss_price,
    stop_loss_price_lookback,
    take_profit_price,
)
from app.rsi_ml import RsiThresholds, compute_rsi_thresholds, compute_rsi_thresholds_percentile
from app.state import InMemoryState
from app.telegram_control import TelegramControl
from app.trade_manager import TradeManager, TradePlan
from app.ws_fills import WsFillManager
from app.emergency_handler import get_emergency_handler


app = FastAPI(title="tv-webhook")
state = InMemoryState()
logger = logging.getLogger("uvicorn.error")

manager: TradeManager | None = None
fill_tracker = FillTracker()
ws_manager: WsFillManager | None = None
tg_control: TelegramControl | None = None
candle_cache: CandleCache | None = None
candle_ws_manager: CandleWsManager | None = None
candle_ws_symbol_tfs: dict[str, list[str]] = {}
rsi_pct_overrides: dict[str, tuple[float, float]] = {}
rsi_max_data_overrides: dict[str, int] = {}
rsi_pct_symbol_overrides: dict[tuple[str, str | None], tuple[float, float]] = {}
rsi_max_data_symbol_overrides: dict[tuple[str, str | None], int] = {}
last_webhook_ts: float | None = None
last_webhook_count = 0
STARTUP_TS = time.time()
_health_task: asyncio.Task | None = None
_refresh_task: asyncio.Task | None = None
_last_refresh_by_key: dict[str, float] = {}
_lighter_refresh_size_by_key: dict[str, float] = {}

# Concurrency limiter for order placement (max 3 concurrent orders)
_order_semaphore = asyncio.Semaphore(3)


async def _place_order_with_limit(exchange_obj: Any, *args: Any, **kwargs: Any) -> Any:
    """Place order with concurrency limiting."""
    async with _order_semaphore:
        return exchange_obj.place_order(*args, **kwargs)


async def _cancel_pending_ladder_orders(key: str, inst_id: str, exchange_obj: Any) -> tuple[int, int]:
    """
    Cancel all pending ladder orders for a position.

    Args:
        key: Position key (inst_id:tf)
        inst_id: Instrument ID (e.g., "EIGEN-USDT-SWAP")
        exchange_obj: Exchange client instance

    Returns:
        Tuple of (canceled_count, failed_count)
    """
    pending_orders = state.get_pending_orders(key)
    if not pending_orders:
        logger.info("cancel_pending_orders key=%s no_pending_orders", key)
        return (0, 0)

    logger.info("cancel_pending_orders key=%s count=%d", key, len(pending_orders))

    canceled = 0
    failed = 0

    for order_info in pending_orders:
        order_id = order_info.get("order_id", "")
        level = order_info.get("level", "")
        symbol = order_info.get("symbol", "")

        if not order_id:
            continue

        try:
            logger.info("canceling_pending_order key=%s order_id=%s level=%s", key, order_id, level)

            # Try to cancel the order
            cancel_resp = await exchange_obj.cancel_order(
                inst_id=inst_id,
                cl_ord_id=order_id
            )

            if str(cancel_resp.get("code", "")) in {"0", "success"}:
                canceled += 1
                logger.info("canceled_pending_order key=%s order_id=%s level=%s", key, order_id, level)
            else:
                # Order might already be filled or canceled
                logger.warning("cancel_pending_failed key=%s order_id=%s level=%s resp=%s",
                             key, order_id, level, cancel_resp)
                failed += 1

        except Exception as e:
            logger.warning("cancel_pending_error key=%s order_id=%s level=%s err=%s",
                         key, order_id, level, str(e))
            failed += 1

    # Clear the pending orders from state
    state.clear_pending_orders(key)

    logger.info("cancel_pending_complete key=%s canceled=%d failed=%d", key, canceled, failed)
    return (canceled, failed)


# Initialize exchange client based on configuration
if SETTINGS.exchange == "extended":
    from app.extended import ExtendedClient

    exchange = ExtendedClient(use_testnet=False)
    exchange.connect()
    ws_manager = WsFillManager(
        fill_tracker=fill_tracker,
        extended_stream_url=exchange.stream_url,
        extended_api_key=exchange.api_key or "",
    )
elif SETTINGS.exchange == "paradex":
    import os

    from app.paradex import ParadexClient

    env = os.getenv("PARADEX_ENV", "prod").lower()
    use_testnet = env not in {"prod", "mainnet"}
    exchange = ParadexClient(use_testnet=use_testnet)
    exchange.connect()
elif SETTINGS.exchange == "lighter":
    import os
    from app.lighter_adapter import create_lighter_adapter

    env = os.getenv("LIGHTER_ENV", "mainnet").lower()
    use_testnet = env == "testnet"
    exchange = create_lighter_adapter(use_testnet=use_testnet)
    # Note: exchange.connect() will be called in startup event (async)
    # WebSocket will be enabled after connection in _startup()
    logger.info(f"Lighter adapter created (env={env}, WebSocket will be enabled on startup)")
else:
    from app.okx import OKXClient, OKXCredentials

    okx = OKXClient(
        SETTINGS.okx_base_url,
        OKXCredentials(
            api_key=SETTINGS.okx_api_key,
            api_secret=SETTINGS.okx_api_secret,
            passphrase=SETTINGS.okx_api_passphrase,
        ),
    )
    exchange = okx
    # TradeManager handles TP ladder execution for OKX
    # Extended mode uses limit orders for TP instead
    manager = TradeManager(okx=exchange, settings=SETTINGS, fill_tracker=fill_tracker)
    ws_manager = WsFillManager(
        fill_tracker=fill_tracker,
        okx_api_key=SETTINGS.okx_api_key,
        okx_api_secret=SETTINGS.okx_api_secret,
        okx_passphrase=SETTINGS.okx_api_passphrase,
    )


def _configure_logging() -> None:
    """Configure log rotation and format for production use."""
    # Create rotating file handler (50MB files, keep 5 backups)
    handler = logging.handlers.RotatingFileHandler(
        "tw168.log",
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
        encoding="utf-8"
    )

    # Set format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    # Add handler to uvicorn logger
    uvicorn_logger = logging.getLogger("uvicorn.error")
    uvicorn_logger.addHandler(handler)

    # Set level based on environment
    if SETTINGS.trading_enabled:
        uvicorn_logger.setLevel(logging.INFO)
    else:
        uvicorn_logger.setLevel(logging.DEBUG)

    logger.info("Log rotation configured: 50MB/file, 5 backups, level=%s", uvicorn_logger.level)


def _parse_symbol_tfs(raw: str, *, default_tfs: list[str]) -> dict[str, list[str]]:
    import re

    out: dict[str, list[str]] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for item in line.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                inst_id, tf_raw = item.split(":", 1)
            else:
                parts = item.split()
                if not parts:
                    continue
                inst_id = parts[0]
                tf_raw = " ".join(parts[1:])
            inst_id = inst_id.strip()
            tfs = [t.strip().lower() for t in re.split(r"[,\s|]+", tf_raw) if t.strip()]
            if inst_id and not tfs:
                tfs = list(default_tfs)
            if inst_id and tfs:
                out[inst_id] = tfs
    return out


def _parse_pct_overrides(raw: str) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for part in line.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            tf_raw, pct_raw = part.split(":", 1)
            if "/" not in pct_raw:
                continue
            low_raw, high_raw = pct_raw.split("/", 1)
            try:
                low = float(low_raw.strip())
                high = float(high_raw.strip())
            except ValueError:
                continue
            tf_key = tf_raw.strip().lower()
            if tf_key:
                out[tf_key] = (low, high)
    return out


def _parse_int_overrides(raw: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for part in line.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            tf_raw, val_raw = part.split(":", 1)
            try:
                val = int(val_raw.strip())
            except ValueError:
                continue
            tf_key = tf_raw.strip().lower()
            if tf_key:
                out[tf_key] = val
    return out


def _parse_symbol_pct_overrides(raw: str) -> dict[tuple[str, str | None], tuple[float, float]]:
    out: dict[tuple[str, str | None], tuple[float, float]] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for part in line.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            key_raw, pct_raw = part.split(":", 1)
            if "/" not in pct_raw:
                continue
            low_raw, high_raw = pct_raw.split("/", 1)
            try:
                low = float(low_raw.strip())
                high = float(high_raw.strip())
            except ValueError:
                continue
            key_raw = key_raw.strip()
            if not key_raw:
                continue
            if "@" in key_raw:
                symbol_raw, tf_raw = key_raw.split("@", 1)
                symbol = symbol_raw.strip().upper()
                tf_key = tf_raw.strip().lower()
            else:
                symbol = key_raw.strip().upper()
                tf_key = None
            if symbol:
                out[(symbol, tf_key)] = (low, high)
    return out


def _parse_symbol_int_overrides(raw: str) -> dict[tuple[str, str | None], int]:
    out: dict[tuple[str, str | None], int] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        for part in line.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            key_raw, val_raw = part.split(":", 1)
            try:
                val = int(val_raw.strip())
            except ValueError:
                continue
            key_raw = key_raw.strip()
            if not key_raw:
                continue
            if "@" in key_raw:
                symbol_raw, tf_raw = key_raw.split("@", 1)
                symbol = symbol_raw.strip().upper()
                tf_key = tf_raw.strip().lower()
            else:
                symbol = key_raw.strip().upper()
                tf_key = None
            if symbol:
                out[(symbol, tf_key)] = val
    return out


allowed_symbols: set[str] = set(SETTINGS.symbol_allowlist)

if SETTINGS.candle_ws_enabled:
    okx_inst_ids: list[str] = []
    extended_inst_ids: list[str] = []
    default_tfs = [tf.lower() for tf in SETTINGS.candle_ws_tfs] or ["1h"]
    if SETTINGS.candle_ws_symbol_tfs_file:
        try:
            with open(SETTINGS.candle_ws_symbol_tfs_file, "r", encoding="ascii") as f:
                candle_ws_symbol_tfs = _parse_symbol_tfs(f.read(), default_tfs=default_tfs)
        except Exception:
            candle_ws_symbol_tfs = {}
    elif SETTINGS.candle_ws_symbol_tfs:
        candle_ws_symbol_tfs = _parse_symbol_tfs(SETTINGS.candle_ws_symbol_tfs, default_tfs=default_tfs)

    if candle_ws_symbol_tfs:
        allowed_symbols = set(candle_ws_symbol_tfs.keys())
    elif "*" in SETTINGS.symbol_allowlist:
        logger.warning("CANDLE_WS enabled with SYMBOL_ALLOWLIST='*'; skipping WS subscriptions")
    else:
        okx_inst_ids = list(SETTINGS.symbol_allowlist)
        extended_inst_ids = list(SETTINGS.symbol_allowlist)
        for inst_id in SETTINGS.symbol_allowlist:
            candle_ws_symbol_tfs.setdefault(inst_id, default_tfs)

    extended_stream_url = ""
    try:
        if SETTINGS.exchange == "extended" and hasattr(exchange, "stream_url"):
            extended_stream_url = exchange.stream_url
        else:
            import os
            from x10.perpetual.configuration import MAINNET_CONFIG, TESTNET_CONFIG

            env = os.getenv("EXTENDED_ENV", "testnet").lower()
            extended_stream_url = (TESTNET_CONFIG if env == "testnet" else MAINNET_CONFIG).stream_url
    except Exception:
        extended_stream_url = ""

    candle_cache = CandleCache(
        max_bars=SETTINGS.candle_cache_max_bars,
        ttl_seconds=SETTINGS.candle_cache_ttl_seconds,
    )
    candle_ws_manager = CandleWsManager(
        cache=candle_cache,
        okx_enabled=SETTINGS.candle_ws_okx_enabled,
        extended_enabled=SETTINGS.candle_ws_extended_enabled,
        okx_inst_ids=okx_inst_ids,
        extended_inst_ids=extended_inst_ids,
        tfs=[] if candle_ws_symbol_tfs else default_tfs,
        extended_stream_url=extended_stream_url,
        okx_max_subs=SETTINGS.candle_ws_okx_max_subs,
        extended_max_subs=SETTINGS.candle_ws_extended_max_subs,
        extended_idle_seconds=SETTINGS.candle_ws_extended_idle_seconds,
    )

if SETTINGS.rsi_pct_by_tf:
    rsi_pct_overrides = _parse_pct_overrides(SETTINGS.rsi_pct_by_tf)
if SETTINGS.rsi_pct_by_symbol:
    rsi_pct_symbol_overrides = _parse_symbol_pct_overrides(SETTINGS.rsi_pct_by_symbol)
if SETTINGS.rsi_max_data_by_tf:
    rsi_max_data_overrides = _parse_int_overrides(SETTINGS.rsi_max_data_by_tf)
if SETTINGS.rsi_max_data_by_symbol:
    rsi_max_data_symbol_overrides = _parse_symbol_int_overrides(SETTINGS.rsi_max_data_by_symbol)


class TvPayload(BaseModel):
    secret: str
    type: str = Field(..., description="ZONE | DIV")
    instId: str
    tf: str = "1m"
    t: str | None = None
    close: str | None = None
    zone: str | None = None
    side: str | None = None
    rsi: float | str | None = None
    rsi_long: float | str | None = None
    rsi_short: float | str | None = None


def _key(inst_id: str, tf: str) -> str:
    return f"{inst_id}:{tf}"


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _normalize_qty(qty: Decimal, *, step: Decimal | None, min_sz: Decimal | None) -> Decimal:
    if step and step > 0:
        qty = (qty / step).to_integral_value(rounding=ROUND_DOWN) * step
    else:
        qty = qty.to_integral_value(rounding=ROUND_DOWN)
    if min_sz and qty < min_sz:
        qty = min_sz
    return qty


def _build_dedupe_key(payload: "TvPayload", *, inst_id: str, tf: str, close_f: float | None) -> str:
    close_part = f"{close_f:.8f}" if close_f is not None else ""
    side_part = (payload.side or "").strip().lower()
    zone_part = (payload.zone or "").strip().upper()
    return f"{payload.type}:{inst_id}:{tf}:{payload.t or ''}:{side_part}:{zone_part}:{close_part}"


def _log_payload(payload: TvPayload) -> None:
    logger.info(
        "tv_webhook received type=%s instId=%s tf=%s zone=%s t=%s close=%s rsi=%s long=%s short=%s",
        payload.type,
        payload.instId,
        payload.tf,
        payload.zone,
        payload.t,
        payload.close,
        payload.rsi,
        payload.rsi_long,
        payload.rsi_short,
    )


def _log_decision(inst_id: str, tf: str, *, action: str, **extra: object) -> None:
    parts = " ".join(f"{k}={v}" for k, v in extra.items())
    logger.info("tv_webhook decision instId=%s tf=%s action=%s %s", inst_id, tf, action, parts)


def _normalize_inst_id(raw_inst_id: str) -> str:
    inst_id = raw_inst_id.strip().upper()
    if inst_id.endswith(".P"):
        inst_id = inst_id[:-2]
    inst_id = inst_id.replace("/", "")
    if "-" in inst_id:
        return inst_id
    if inst_id.endswith("USDT"):
        base = inst_id[:-4]
        if base:
            return f"{base}-USDT-SWAP"
    return inst_id


def _parse_float(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_side(value: str | None) -> str | None:
    if not value:
        return None
    val = value.strip().lower()
    if val in {"buy", "sell"}:
        return val
    return None


async def _calculate_order_size(
    *,
    inst_id: str,
    r_value: float,
    entry_price: float,
    tf: str | None = None,
) -> tuple[str, dict[str, object]]:
    from app.config import get_risk_per_trade

    order_sz = SETTINGS.order_sz
    meta: dict[str, object] = {}

    # Get timeframe-specific risk if available, otherwise use default
    risk_amount = get_risk_per_trade(tf) if tf else SETTINGS.risk_per_trade_usdt

    def _ceil_to_step(value: Decimal, step: Decimal | None) -> Decimal:
        if step is None or step <= 0:
            return value
        return (value / step).to_integral_value(rounding=ROUND_UP) * step

    inst_info = await exchange.get_instrument_info(inst_id=inst_id)
    lot_step = Decimal(str(inst_info.get("lotStep"))) if inst_info and inst_info.get("lotStep") else None
    min_order = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else None
    min_quote = None
    if inst_info and inst_info.get("minQuote") and entry_price > 0:
        try:
            min_quote = Decimal(str(inst_info.get("minQuote")))
        except Exception:
            min_quote = None

    if not (risk_amount and risk_amount > 0 and r_value > 0):
        try:
            qty = _normalize_qty(Decimal(str(order_sz)), step=lot_step, min_sz=min_order)
            if min_quote is not None and entry_price > 0:
                min_qty_by_quote = _ceil_to_step(min_quote / Decimal(str(entry_price)), lot_step)
                if qty < min_qty_by_quote:
                    qty = min_qty_by_quote
                    meta["min_quote"] = str(min_quote)
            order_sz = _format_decimal(qty)
            if min_order:
                meta["fixed_adjusted"] = True
                meta["min_order"] = str(min_order)
        except Exception:
            pass
        return order_sz, meta

    ct_val = float(inst_info.get("ctVal")) if inst_info and inst_info.get("ctVal") else 1.0

    risk_usdt = Decimal(str(risk_amount))
    r_value_dec = Decimal(str(r_value))
    ct_val_dec = Decimal(str(ct_val))
    calculated_sz_coins = risk_usdt / r_value_dec
    calculated_sz_contracts = calculated_sz_coins / ct_val_dec
    qty = _normalize_qty(calculated_sz_contracts, step=lot_step, min_sz=min_order)
    if min_quote is not None and entry_price > 0:
        min_qty_by_quote = _ceil_to_step(min_quote / Decimal(str(entry_price)), lot_step)
        if qty < min_qty_by_quote:
            qty = min_qty_by_quote
            meta["min_quote"] = str(min_quote)
    if qty <= 0:
        qty = min_order or Decimal("1")

    order_sz = _format_decimal(qty)
    meta = {
        "ct_val": ct_val,
        "lot_step": str(lot_step) if lot_step is not None else None,
        "min_order": str(min_order) if min_order is not None else None,
        "calculated_sz_coins": float(calculated_sz_coins),
        "actual_coins": float(qty * ct_val_dec),
    }
    return order_sz, meta


async def _place_extended_tp_orders(
    *,
    inst_id: str,
    side: str,
    pos_side: str,
    entry_price: float,
    sl: float,
    total_sz: Decimal,
    tick_size: str | None,
    cl_ord_id: str,
) -> list[dict[str, str]]:
    tp_targets = await _build_tp_targets(
        inst_id=inst_id,
        side=side,
        entry_price=entry_price,
        sl=sl,
        total_sz=total_sz,
        tick_size=tick_size,
    )
    tp_orders: list[dict[str, str]] = []
    for target in tp_targets:
        tp_resp = await exchange.place_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side="sell" if side == "buy" else "buy",
            pos_side=pos_side,
            ord_type="limit",
            sz=target["size"],
            px=target["price"],
            cl_ord_id=f"{cl_ord_id}_{target['tag']}"[:32],
            sl_trigger_px=None,
            tp_trigger_px=None,
            reduce_only=True,
        )
        if str(tp_resp.get("code", "")) not in {"0", "success"}:
            notify_error(
                f"extended tp failed instId={inst_id} tag={target['tag']} price={target['price']} sz={target['size']} resp={tp_resp}"
            )
        else:
            data = tp_resp.get("data") or []
            if data:
                ord_id = data[0].get("ordId") or ""
                if ord_id:
                    fill_tracker.register_order_label(
                        key=str(ord_id),
                        label=target["tag"],
                    )
        tp_orders.append(
            {
                "tag": target["tag"],
                "price": target["price"],
                "size": target["size"],
                "resp": str(tp_resp),
            }
        )
    return tp_orders


async def _place_extended_sl_order(
    *,
    inst_id: str,
    pos_side: str,
    sl: float,
    total_sz: Decimal,
    tick_size: str | None,
    cl_ord_id: str,
    last_price: float | None,
) -> dict[str, str] | None:
    sl_px = _round_price_to_tick(sl, tick_size)
    side = "sell" if pos_side == "long" else "buy"
    order_px = _round_price_to_tick(last_price, tick_size) if last_price is not None else sl_px
    resp = await exchange.place_order(
        inst_id=inst_id,
        td_mode=SETTINGS.okx_td_mode,
        side=side,
        pos_side=pos_side,
        ord_type="limit",
        sz=str(total_sz),
        px=order_px,
        cl_ord_id=cl_ord_id,
        sl_trigger_px=sl_px,
        tp_trigger_px=None,
        reduce_only=True,
    )
    if str(resp.get("code", "")) not in {"0", "success"}:
        notify_error(
            f"extended sl refresh failed instId={inst_id} posSide={pos_side} sl={sl_px} sz={total_sz} resp={resp}"
        )
        return None
    return {"sl": sl_px, "size": str(total_sz), "resp": str(resp)}


async def _build_tp_targets(
    *,
    inst_id: str,
    side: str,
    entry_price: float,
    sl: float,
    total_sz: Decimal,
    tick_size: str | None,
) -> list[dict[str, str]]:
    inst_info = await exchange.get_instrument_info(inst_id=inst_id)
    step = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else Decimal("1")

    def _floor_to_step(value: Decimal, step_value: Decimal) -> Decimal:
        if step_value <= 0:
            return value
        return (value / step_value).to_integral_value(rounding=ROUND_DOWN) * step_value

    total_tp_pct = SETTINGS.tp1_pct + SETTINGS.tp2_pct + SETTINGS.tp3_pct
    if total_tp_pct > 1.0:
        logger.warning(
            "extended tp_pct_exceeds_100 total=%.2f%% adjusting proportionally",
            total_tp_pct * 100,
        )
        scale_factor = 1.0 / total_tp_pct
        tp1_pct_adjusted = SETTINGS.tp1_pct * scale_factor
        tp2_pct_adjusted = SETTINGS.tp2_pct * scale_factor
        tp3_pct_adjusted = SETTINGS.tp3_pct * scale_factor
    else:
        tp1_pct_adjusted = SETTINGS.tp1_pct
        tp2_pct_adjusted = SETTINGS.tp2_pct
        tp3_pct_adjusted = SETTINGS.tp3_pct

    tp1_sz = _floor_to_step(total_sz * Decimal(str(tp1_pct_adjusted)), step)
    tp2_sz = _floor_to_step(total_sz * Decimal(str(tp2_pct_adjusted)), step)
    tp3_sz = _floor_to_step(total_sz * Decimal(str(tp3_pct_adjusted)), step)
    remaining = total_sz - tp1_sz - tp2_sz - tp3_sz
    if remaining < 0:
        logger.error(
            "extended tp_size_negative remaining=%s total=%s tp1=%s tp2=%s tp3=%s",
            remaining, total_sz, tp1_sz, tp2_sz, tp3_sz
        )
        remaining = Decimal("0")

    tp_sizes = [
        (SETTINGS.tp1_r, tp1_sz, "tp1"),
        (SETTINGS.tp2_r, tp2_sz, "tp2"),
        (SETTINGS.tp3_r, tp3_sz, "tp3"),
        (SETTINGS.tp4_r, remaining, "tp4"),
    ]
    targets: list[dict[str, str]] = []
    for rr, sz_dec, tag in tp_sizes:
        if sz_dec <= 0:
            continue
        tp_price = take_profit_price(
            side=side,
            entry_price=entry_price,
            stop_loss=sl,
            rr=rr,
        )
        if tp_price is None:
            continue
        tp_px = _round_price_to_tick(tp_price, tick_size)
        targets.append({"tag": tag, "price": tp_px, "size": str(sz_dec)})
    return targets


def _compute_trailing_sl(
    *,
    side: str,
    entry_price: float,
    sl_price: float,
    last_price: float,
    trail_start_r: float,
) -> float | None:
    r_value = abs(entry_price - sl_price)
    if r_value <= 0:
        return None
    profit = (last_price - entry_price) if side == "buy" else (entry_price - last_price)
    profit_r = profit / r_value
    if profit_r < trail_start_r:
        return None
    if profit_r >= 3.0:
        offset_r = 1.0
    elif profit_r >= 2.0:
        offset_r = 0.5
    elif profit_r >= 1.0:
        offset_r = 0.1
    else:
        offset_r = 0.0
    return entry_price + (offset_r * r_value) if side == "buy" else entry_price - (offset_r * r_value)


def _extract_order_price(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        for key in ("trigger_price", "price"):
            if key in value and value[key] is not None:
                try:
                    return float(value[key])
                except Exception:
                    continue
        return None
    for attr in ("trigger_price", "price"):
        try:
            raw = getattr(value, attr)
        except Exception:
            raw = None
        if raw is not None:
            try:
                return float(raw)
            except Exception:
                continue
    return None


def _round_price_to_tick(price: float, tick_size: str | None) -> str:
    """Round price to exchange tick size and format as string."""
    if not tick_size or tick_size == "":
        return f"{price:.8f}".rstrip("0").rstrip(".")
    try:
        from decimal import Decimal, ROUND_DOWN
        tick = Decimal(str(tick_size))
        if tick <= 0:
            return f"{price:.8f}".rstrip("0").rstrip(".")
        price_dec = Decimal(str(price))
        rounded = (price_dec / tick).quantize(Decimal("1"), rounding=ROUND_DOWN) * tick
        return str(rounded).rstrip("0").rstrip(".")
    except Exception:
        return f"{price:.8f}".rstrip("0").rstrip(".")


def _getenv_optional(name: str) -> str | None:
    import os

    value = os.getenv(name, "").strip()
    return value or None


def _start_telegram_control() -> None:
    global tg_control
    if tg_control is not None:
        return
    bot_token = _getenv_optional("TELEGRAM_BOT_TOKEN")
    chat_id = _getenv_optional("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        return

    def handler(inst_id: str, tf: str) -> None:
        _handle_telegram_div(inst_id, tf)

    tg_control = TelegramControl(token=bot_token, chat_id=chat_id, handler=handler)
    tg_control.start()


async def _refresh_extended_protection() -> None:
    if SETTINGS.exchange != "extended":
        return
    while True:
        await asyncio.sleep(SETTINGS.extended_refresh_seconds)


async def _refresh_paradex_protection() -> None:
    if SETTINGS.exchange != "paradex":
        return
    while True:
        await asyncio.sleep(SETTINGS.extended_refresh_seconds)
        if not SETTINGS.trading_enabled or not SETTINGS.extended_refresh_enabled:
            continue
        for inst_id in allowed_symbols:
            if inst_id == "*":
                continue
            pos = await exchange.get_position(inst_id=inst_id, pos_side="long")
            if not pos:
                pos = await exchange.get_position(inst_id=inst_id, pos_side="short")
            if not pos:
                continue
            size = Decimal(str(pos.get("pos", "0")))
            if size <= 0:
                continue
            entry_info = fill_tracker.get_entry_info(inst_id=inst_id)
            if entry_info is None:
                continue
            last_price = await exchange.get_last_price(inst_id=inst_id)
            if last_price is None:
                continue

            trail_sl = _compute_trailing_sl(
                side=entry_info.side,
                entry_price=entry_info.entry_price,
                sl_price=entry_info.stop_loss,
                last_price=last_price,
                trail_start_r=SETTINGS.trail_start_r,
            )
            if trail_sl is None:
                continue

            inst_info = await exchange.get_instrument_info(inst_id=inst_id)
            tick_size = inst_info.get("tickSz") if inst_info else None
            desired_sl = float(_round_price_to_tick(trail_sl, tick_size))

            orders = await exchange.get_open_orders(inst_id=inst_id)
            sl_orders = [o for o in orders if str(o.get("type", "")).upper().startswith("STOP_LOSS")]
            current_sl = None
            for order in sl_orders:
                trigger = _extract_order_price(order.get("trigger_price")) or _extract_order_price(order.get("price"))
                if trigger is None:
                    continue
                if current_sl is None:
                    current_sl = trigger
                else:
                    if entry_info.side == "buy":
                        current_sl = max(current_sl, trigger)
                    else:
                        current_sl = min(current_sl, trigger)

            if current_sl is not None:
                if entry_info.side == "buy" and desired_sl <= current_sl:
                    continue
                if entry_info.side == "sell" and desired_sl >= current_sl:
                    continue

            # Cancel old SL orders (if any) then place new SL.
            for order in sl_orders:
                ord_id = order.get("ordId")
                if ord_id:
                    await exchange.cancel_order(order_id=str(ord_id))

            sl_side = "sell" if entry_info.side == "buy" else "buy"
            resp = await exchange.place_order(
                inst_id=inst_id,
                side=sl_side,
                ord_type="stop_loss_market",
                sz=str(size),
                px=None,
                cl_ord_id=f"trail{int(time.time())}"[:32],
                reduce_only=True,
                trigger_px=_round_price_to_tick(desired_sl, tick_size),
            )
            if str(resp.get("code", "")) not in {"0", "success"}:
                notify_error(
                    f"paradex sl refresh failed instId={inst_id} side={sl_side} sl={desired_sl} sz={size} resp={resp}"
                )
            else:
                notify_info(
                    f"paradex sl refresh placed instId={inst_id} side={sl_side} sl={desired_sl}"
                )
        if not SETTINGS.trading_enabled or not SETTINGS.extended_refresh_enabled:
            continue
        now = time.time()
        for inst_id in allowed_symbols:
            if inst_id == "*":
                continue
            for pos_side in ("long", "short"):
                key = f"{inst_id}:{pos_side}"
                last_ts = _last_refresh_by_key.get(key, 0.0)
                if (now - last_ts) < SETTINGS.extended_refresh_seconds:
                    continue
                pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
                if not pos or float(pos.get("pos", "0") or "0") == 0.0:
                    state.clear_entry(inst_id)
                    continue
                try:
                    size = Decimal(str(pos.get("pos", "0")))
                except Exception:
                    size = Decimal("0")
                if size <= 0:
                    continue
                _last_refresh_by_key[key] = now

                entry_price = pos.get("open_price")
                sl_price = pos.get("sl_price")
                entry_info = fill_tracker.get_entry_info(inst_id=inst_id)
                if entry_price is None and entry_info is not None:
                    entry_price = entry_info.entry_price
                if sl_price is None and entry_info is not None:
                    sl_price = entry_info.stop_loss
                side = "buy" if pos_side == "long" else "sell"
                tick_size = None
                inst_info = await exchange.get_instrument_info(inst_id=inst_id)
                if inst_info:
                    tick_size = inst_info.get("tickSz")

                orders = await exchange.get_open_orders(inst_id=inst_id)
                opposite_side = "SELL" if pos_side == "long" else "BUY"
                sl_order_exists = False
                sl_attached = False
                for order in orders:
                    if not order.get("reduce_only"):
                        continue
                    if str(order.get("side", "")).upper() != opposite_side:
                        continue
                    stop_loss = order.get("stop_loss")
                    if stop_loss:
                        sl_order_exists = True
                        sl_from_order = _extract_order_price(stop_loss)
                        if sl_from_order is not None and sl_price is None:
                            sl_price = sl_from_order
                        break
                if sl_price is None:
                    sl_from_history = exchange.get_last_stop_loss(inst_id=inst_id, pos_side=pos_side)
                    if sl_from_history is not None:
                        sl_price = float(sl_from_history)
                        sl_attached = True

                if SETTINGS.extended_refresh_sl_enabled:
                    if not sl_price:
                        logger.warning(
                            "extended sl missing instId=%s posSide=%s size=%s", inst_id, pos_side, size
                        )
                        notify_info(
                            f"extended sl missing instId={inst_id} posSide={pos_side} size={size}"
                        )
                    elif not sl_order_exists and not sl_attached:
                        last_price = await exchange.get_last_price(inst_id=inst_id)
                        target_sl = None
                        try:
                            if entry_price is not None and last_price is not None:
                                target_sl = _compute_trailing_sl(
                                    side=side,
                                    entry_price=float(entry_price),
                                    sl_price=float(sl_price),
                                    last_price=float(last_price),
                                    trail_start_r=SETTINGS.trail_start_r,
                                )
                        except Exception:
                            target_sl = None
                        sl_to_place = float(sl_price)
                        if target_sl is not None:
                            if side == "buy":
                                sl_to_place = max(sl_to_place, target_sl)
                            else:
                                sl_to_place = min(sl_to_place, target_sl)
                        gap = float(tick_size) if tick_size else 0.0
                        if last_price is not None:
                            if side == "buy" and sl_to_place >= float(last_price) - gap:
                                continue
                            if side == "sell" and sl_to_place <= float(last_price) + gap:
                                continue
                        ts = int(time.time())
                        cl_ord_id = f"tv_refresh_sl_{ts}{pos_side[:1]}"[:32]
                        sl_order = await _place_extended_sl_order(
                            inst_id=inst_id,
                            pos_side=pos_side,
                            sl=sl_to_place,
                            total_sz=size,
                            tick_size=tick_size,
                            cl_ord_id=cl_ord_id,
                            last_price=last_price,
                        )
                        if sl_order:
                            notify_info(
                                f"extended sl refresh placed instId={inst_id} posSide={pos_side} sl={sl_order['sl']}"
                            )

                if SETTINGS.extended_refresh_tp_enabled:
                    if entry_price is None or sl_price is None:
                        logger.warning(
                            "extended tp refresh skipped instId=%s posSide=%s reason=missing_entry_or_sl",
                            inst_id, pos_side
                        )
                        continue
                    tp_targets = await _build_tp_targets(
                        inst_id=inst_id,
                        side=side,
                        entry_price=float(entry_price),
                        sl=float(sl_price),
                        total_sz=size,
                        tick_size=tick_size,
                    )
                    if not tp_targets:
                        continue

                    existing_prices: list[Decimal] = []
                    tick_val = Decimal(str(tick_size)) if tick_size else None
                    for order in orders:
                        if not order.get("reduce_only"):
                            continue
                        if str(order.get("type", "")).upper() not in {"ORDERTYPE.LIMIT", "LIMIT"}:
                            continue
                        if str(order.get("side", "")).upper() != opposite_side:
                            continue
                        price = order.get("price")
                        if price is None:
                            continue
                        try:
                            existing_prices.append(Decimal(str(price)))
                        except Exception:
                            continue

                    def _price_match(target: Decimal) -> bool:
                        if not existing_prices:
                            return False
                        if tick_val is None or tick_val <= 0:
                            return any(abs(target - p) <= Decimal("0.00000001") for p in existing_prices)
                        return any(abs(target - p) <= tick_val for p in existing_prices)

                    missing = []
                    for target in tp_targets:
                        try:
                            target_price = Decimal(str(target["price"]))
                        except Exception:
                            continue
                        if _price_match(target_price):
                            continue
                        missing.append(target)

                    if not missing:
                        continue

                    ts = int(time.time())
                    cl_ord_id = f"tv_refresh_{ts}{pos_side[:1]}"[:32]
                    placed = 0
                    for target in missing:
                        tp_resp = await exchange.place_order(
                            inst_id=inst_id,
                            td_mode=SETTINGS.okx_td_mode,
                            side="sell" if side == "buy" else "buy",
                            pos_side=pos_side,
                            ord_type="limit",
                            sz=target["size"],
                            px=target["price"],
                            cl_ord_id=f"{cl_ord_id}_{target['tag']}"[:32],
                            sl_trigger_px=None,
                            tp_trigger_px=None,
                            reduce_only=True,
                        )
                        if str(tp_resp.get("code", "")) not in {"0", "success"}:
                            notify_error(
                                f"extended tp refresh failed instId={inst_id} tag={target['tag']} price={target['price']} sz={target['size']} resp={tp_resp}"
                            )
                            continue
                        placed += 1

                    if placed:
                        notify_info(
                            f"extended tp refresh placed instId={inst_id} posSide={pos_side} count={placed}"
                        )


async def _refresh_lighter_protection() -> None:
    if SETTINGS.exchange != "lighter":
        return
    while True:
        await asyncio.sleep(SETTINGS.lighter_refresh_seconds)
        if not SETTINGS.trading_enabled or not SETTINGS.lighter_refresh_enabled:
            continue
        now = time.time()
        for inst_id in allowed_symbols:
            if inst_id == "*":
                continue
            for pos_side in ("long", "short"):
                key = f"{inst_id}:{pos_side}"
                pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
                if not pos:
                    continue
                try:
                    size = Decimal(str(pos.get("pos", "0") or "0"))
                except Exception:
                    size = Decimal("0")
                if size <= 0:
                    continue
                last_ts = _last_refresh_by_key.get(key, 0.0)
                last_sz = _lighter_refresh_size_by_key.get(key)
                if last_sz is not None and abs(last_sz - float(size)) < 1e-9:
                    if (now - last_ts) < SETTINGS.lighter_refresh_seconds:
                        continue

                entry_info = fill_tracker.get_entry_info(inst_id=inst_id)
                if entry_info is None:
                    entry_state = state.get_entry(inst_id, ttl_seconds=SETTINGS.lighter_entry_ttl_seconds)
                    if entry_state is None:
                        continue
                    entry_info = SimpleNamespace(
                        side=entry_state.side,
                        entry_price=entry_state.entry_price,
                        stop_loss=entry_state.stop_loss,
                    )

                inst_info = await exchange.get_instrument_info(inst_id=inst_id)
                tick_size = inst_info.get("tickSz") if inst_info else None
                lot_step = Decimal(str(inst_info.get("lotStep"))) if inst_info and inst_info.get("lotStep") else None
                min_order = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else None

                normalized_sz = _normalize_qty(size, step=lot_step, min_sz=min_order)
                if normalized_sz <= 0:
                    continue
                sl_order_sz = _format_decimal(normalized_sz)
                side = entry_info.side
                sl_side = "sell" if side == "buy" else "buy"

                # If existing protection orders already match, skip refresh.
                try:
                    existing_orders = await exchange.get_open_orders(inst_id=inst_id)
                except Exception:
                    logger.warning("lighter refresh skipped instId=%s posSide=%s reason=open_orders_error", inst_id, pos_side)
                    _last_refresh_by_key[key] = now
                    _lighter_refresh_size_by_key[key] = float(normalized_sz)
                    continue

                open_err_ts = getattr(exchange, "_open_orders_error_ts", 0.0)
                if not existing_orders and open_err_ts and (now - open_err_ts) < 5:
                    _last_refresh_by_key[key] = now
                    _lighter_refresh_size_by_key[key] = float(normalized_sz)
                    logger.info(
                        "lighter refresh skipped instId=%s posSide=%s reason=open_orders_recent_error",
                        inst_id,
                        pos_side,
                    )
                    continue

                store = getattr(exchange, "_okx_compat_state", None)
                if store and not existing_orders:
                    protect = store.get("protective_by_key", {}).get(key, {})
                    if protect.get("sl") or protect.get("tp"):
                        _last_refresh_by_key[key] = now
                        _lighter_refresh_size_by_key[key] = float(normalized_sz)
                        logger.info(
                            "lighter refresh skipped instId=%s posSide=%s reason=stored_protection",
                            inst_id,
                            pos_side,
                        )
                        continue

                if not existing_orders:
                    last_ts = _last_refresh_by_key.get(key, 0.0)
                    refresh_guard = SETTINGS.lighter_refresh_seconds * 2
                    if last_ts and (now - last_ts) < refresh_guard:
                        _last_refresh_by_key[key] = now
                        _lighter_refresh_size_by_key[key] = float(normalized_sz)
                        continue

                protect_orders = []
                for order in existing_orders:
                    if not order.get("reduce_only"):
                        continue
                    otype = str(order.get("type", "")).lower()
                    trigger_px = order.get("trigger_price")
                    if trigger_px is None and otype not in {"stop-loss", "stop-loss-limit", "take-profit", "take-profit-limit", "sl", "tp", "conditional"}:
                        continue
                    protect_orders.append(order)

                if protect_orders:
                    def _order_ts(o):
                        val = o.get("created_at")
                        if val is None:
                            return 0.0
                        if isinstance(val, (int, float)):
                            return float(val)
                        try:
                            return float(str(val))
                        except Exception:
                            return 0.0

                    def _order_kind(o):
                        otype = str(o.get("type", "")).lower()
                        if "stop" in otype or "sl" in otype:
                            return "sl"
                        if "take" in otype or "tp" in otype:
                            return "tp"
                        return "trigger" if o.get("trigger_price") is not None else "other"

                    def _order_key(o):
                        trigger_px = o.get("trigger_price")
                        size_val = o.get("size") or o.get("sz") or o.get("remaining_size")
                        try:
                            size_val = Decimal(str(size_val))
                        except Exception:
                            size_val = Decimal("0")
                        try:
                            trigger_val = Decimal(str(trigger_px)) if trigger_px is not None else None
                        except Exception:
                            trigger_val = None
                        return (_order_kind(o), str(trigger_val) if trigger_val is not None else None, str(size_val))

                    keep_by_key = {}
                    dupes = []
                    for order in protect_orders:
                        key_info = _order_key(order)
                        current = keep_by_key.get(key_info)
                        if current is None:
                            keep_by_key[key_info] = order
                            continue
                        if _order_ts(order) >= _order_ts(current):
                            dupes.append(current)
                            keep_by_key[key_info] = order
                        else:
                            dupes.append(order)

                    for order in dupes:
                        ord_id = order.get("ordId")
                        if ord_id:
                            try:
                                await exchange.cancel_order(inst_id=inst_id, order_id=str(ord_id))
                            except Exception:
                                pass
                    if dupes:
                        logger.info(
                            "lighter protection dedupe instId=%s posSide=%s cancelled=%d",
                            inst_id,
                            pos_side,
                            len(dupes),
                        )

                    kept_orders = list(keep_by_key.values())
                    if kept_orders:
                        protect_orders = kept_orders

                # Cancel previously placed protection orders if tracked
                if store and not protect_orders:
                    protect = store.get("protective_by_key", {}).get(key)
                    if protect:
                        for order_id in (protect.get("sl", []) + protect.get("tp", [])):
                            try:
                                await exchange.cancel_order(inst_id=inst_id, order_id=order_id)
                            except Exception:
                                pass
                        protect["sl"] = []
                        protect["tp"] = []

                sl_orders = []
                tp_orders = []
                for order in protect_orders:
                    otype = str(order.get("type", "")).lower()
                    if "stop" in otype or "sl" in otype:
                        sl_orders.append(order)
                    elif "take" in otype or "tp" in otype:
                        tp_orders.append(order)

                if SETTINGS.lighter_refresh_sl_enabled and not sl_orders:
                    sl_px = _round_price_to_tick(entry_info.stop_loss, tick_size)
                    sl_failed = False
                    try:
                        current_price = await exchange.get_last_price(inst_id=inst_id) or 0.0
                    except Exception:
                        current_price = 0.0
                    if current_price > 0:
                        sl_invalid = False
                        if side == "buy" and entry_info.stop_loss >= current_price:
                            sl_invalid = True
                        elif side == "sell" and entry_info.stop_loss <= current_price:
                            sl_invalid = True
                        if sl_invalid:
                            await _lighter_emergency_close(
                                inst_id=inst_id,
                                pos_side=pos_side,
                                close_side=sl_side,
                                size=sl_order_sz,
                                current_price=current_price,
                                entry_info=entry_info,
                                inst_info=inst_info,
                                protect_orders=protect_orders,
                                failure_reason="sl_already_breached",
                            )
                            _last_refresh_by_key[key] = now
                            _lighter_refresh_size_by_key[key] = float(normalized_sz)
                            continue
                    sl_resp = await exchange.place_algo_order(
                        inst_id=inst_id,
                        td_mode=SETTINGS.okx_td_mode,
                        side=sl_side,
                        pos_side=pos_side,
                        ord_type="conditional",
                        sz=sl_order_sz,
                        sl_trigger_px=sl_px,
                        sl_ord_px="-1",
                    )
                    if str(sl_resp.get("code", "")) not in {"0", "success"}:
                        sl_failed = True
                        notify_error(
                            f"lighter sl refresh failed instId={inst_id} posSide={pos_side} sl={sl_px} sz={sl_order_sz} resp={sl_resp}"
                        )

                    if sl_failed:
                        code = str(sl_resp.get("code", ""))
                        msg = str(sl_resp.get("msg", ""))
                        if code == "21720" or "maximum pending" in msg.lower():
                            candidates = tp_orders or protect_orders
                            if candidates:
                                oldest = min(candidates, key=lambda o: o.get("created_at") or 0)
                                ord_id = oldest.get("ordId")
                                if ord_id:
                                    try:
                                        await exchange.cancel_order(inst_id=inst_id, order_id=str(ord_id))
                                    except Exception:
                                        pass
                                    sl_retry = await exchange.place_algo_order(
                                        inst_id=inst_id,
                                        td_mode=SETTINGS.okx_td_mode,
                                        side=sl_side,
                                        pos_side=pos_side,
                                        ord_type="conditional",
                                        sz=sl_order_sz,
                                        sl_trigger_px=sl_px,
                                        sl_ord_px="-1",
                                    )
                                    if str(sl_retry.get("code", "")) in {"0", "success"}:
                                        sl_failed = False

                    if sl_failed and SETTINGS.backup_sl_enabled:
                        try:
                            backup_sl_resp = await exchange.place_order(
                                inst_id=inst_id,
                                td_mode=SETTINGS.okx_td_mode,
                                side=sl_side,
                                pos_side=pos_side,
                                ord_type="limit",
                                sz=sl_order_sz,
                                px=_round_price_to_tick(entry_info.stop_loss, tick_size),
                                cl_ord_id=f"tv_slb_{int(time.time())}"[:32],
                                sl_trigger_px=None,
                                tp_trigger_px=None,
                                reduce_only=True,
                            )
                            if str(backup_sl_resp.get("code", "")) not in {"0", "success"}:
                                sl_failed = True
                            else:
                                sl_failed = False
                        except Exception:
                            sl_failed = True

                    if sl_failed:
                        emergency_handler = get_emergency_handler()
                        await emergency_handler.register_emergency(
                            inst_id=inst_id,
                            pos_side=pos_side,
                            size=sl_order_sz,
                            entry_price=entry_info.entry_price,
                            stop_loss=float(entry_info.stop_loss),
                            cl_ord_id="lighter_refresh",
                            failure_reason="lighter_refresh_sl_failed",
                        )
                        await _lighter_emergency_close(
                            inst_id=inst_id,
                            pos_side=pos_side,
                            close_side=sl_side,
                            size=sl_order_sz,
                            current_price=current_price,
                            entry_info=entry_info,
                            inst_info=inst_info,
                            protect_orders=protect_orders,
                            failure_reason="lighter_refresh_sl_failed",
                        )

                if SETTINGS.lighter_refresh_tp_enabled and SETTINGS.tp_enabled:
                    tp_targets = await _build_tp_targets(
                        inst_id=inst_id,
                        side=side,
                        entry_price=entry_info.entry_price,
                        sl=entry_info.stop_loss,
                        total_sz=normalized_sz,
                        tick_size=tick_size,
                    )
                    existing_tp_prices = []
                    for order in tp_orders:
                        trigger_val = order.get("trigger_price") or order.get("price")
                        if trigger_val is not None:
                            try:
                                existing_tp_prices.append(Decimal(str(trigger_val)))
                            except Exception:
                                continue

                    def _tp_exists(target_price: Decimal) -> bool:
                        if not existing_tp_prices:
                            return False
                        tick_val = None
                        try:
                            tick_val = Decimal(str(tick_size)) if tick_size else None
                        except Exception:
                            tick_val = None
                        if tick_val is None:
                            return any(abs(target_price - p) <= Decimal("0.00000001") for p in existing_tp_prices)
                        return any(abs(target_price - p) <= tick_val for p in existing_tp_prices)

                    for target in tp_targets:
                        try:
                            target_price = Decimal(str(target["price"]))
                        except Exception:
                            continue
                        if _tp_exists(target_price):
                            continue
                        tp_resp = await exchange.place_algo_order(
                            inst_id=inst_id,
                            td_mode=SETTINGS.okx_td_mode,
                            side=sl_side,
                            pos_side=pos_side,
                            ord_type="conditional",
                            sz=target["size"],
                            tp_trigger_px=target["price"],
                            tp_ord_px="-1",
                        )
                        if str(tp_resp.get("code", "")) not in {"0", "success"}:
                            notify_error(
                                f"lighter tp refresh failed instId={inst_id} tag={target['tag']} price={target['price']} sz={target['size']} resp={tp_resp}"
                            )

                _last_refresh_by_key[key] = now
                _lighter_refresh_size_by_key[key] = float(normalized_sz)
                logger.info(
                    "lighter protection refreshed instId=%s posSide=%s size=%s",
                    inst_id,
                    pos_side,
                    sl_order_sz,
                )


async def _lighter_emergency_close(
    *,
    inst_id: str,
    pos_side: str,
    close_side: str,
    size: str,
    current_price: float,
    entry_info: SimpleNamespace,
    inst_info: dict | None,
    protect_orders: list[dict],
    failure_reason: str,
) -> bool:
    min_quote = None
    if inst_info and inst_info.get("minQuote"):
        try:
            min_quote = Decimal(str(inst_info.get("minQuote")))
        except Exception:
            min_quote = None

    if min_quote is not None and current_price > 0:
        try:
            if Decimal(str(current_price)) * Decimal(str(size)) < min_quote:
                notify_error(
                    f"lighter emergency close skipped instId={inst_id} reason=min_quote_not_met"
                )
                emergency_handler = get_emergency_handler()
                await emergency_handler.register_emergency(
                    inst_id=inst_id,
                    pos_side=pos_side,
                    size=size,
                    entry_price=entry_info.entry_price,
                    stop_loss=float(entry_info.stop_loss),
                    cl_ord_id="lighter_emerg",
                    failure_reason="min_quote_not_met",
                )
                return False
        except Exception:
            pass

    # Only attempt to clear protection orders when SL is missing.
    for order in protect_orders:
        ord_id = order.get("ordId")
        if ord_id:
            try:
                await exchange.cancel_order(inst_id=inst_id, order_id=str(ord_id))
            except Exception:
                pass

    emergency_handler = get_emergency_handler()
    await emergency_handler.register_emergency(
        inst_id=inst_id,
        pos_side=pos_side,
        size=size,
        entry_price=entry_info.entry_price,
        stop_loss=float(entry_info.stop_loss),
        cl_ord_id="lighter_emerg",
        failure_reason=failure_reason,
    )

    for attempt in range(3):
        try:
            resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=close_side,
                pos_side=pos_side,
                ord_type="market",
                sz=size,
                px=None,
                cl_ord_id=f"tv_emerg_{int(time.time())}_{attempt}"[:32],
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=True,
            )
            if str(resp.get("code", "")) in {"0", "success"}:
                await emergency_handler.clear_emergency(inst_id, pos_side)
                return True
        except Exception:
            pass
        await asyncio.sleep(0.2 * (attempt + 1))
    notify_error(
        f"🚨 CRITICAL ALERT 🚨\n"
        f"Emergency close failed\n"
        f"Symbol: {inst_id}\n"
        f"Side: {pos_side}\n"
        f"Size: {size}\n"
        f"Reason: {failure_reason}"
    )
    return False


async def _dedupe_lighter_orders() -> None:
    if SETTINGS.exchange != "lighter":
        return
    dedupe_interval = min(SETTINGS.lighter_refresh_seconds, 15)
    while True:
        await asyncio.sleep(dedupe_interval)
        if not SETTINGS.trading_enabled:
            continue
        for inst_id in allowed_symbols:
            if inst_id == "*":
                continue
            try:
                orders = await exchange.get_open_orders(inst_id=inst_id)
            except Exception:
                continue
            protect_orders = [o for o in orders if o.get("reduce_only")]
            if not protect_orders:
                continue

            def _order_ts(o):
                val = o.get("created_at")
                if val is None:
                    return 0.0
                if isinstance(val, (int, float)):
                    return float(val)
                try:
                    return float(str(val))
                except Exception:
                    return 0.0

            def _order_key(o):
                return (
                    str(o.get("side")),
                    str(o.get("type")),
                    str(o.get("trigger_price")),
                    str(o.get("size") or o.get("sz") or o.get("remaining_size")),
                )

            keep_by_key = {}
            dupes = []
            for order in protect_orders:
                key_info = _order_key(order)
                current = keep_by_key.get(key_info)
                if current is None:
                    keep_by_key[key_info] = order
                    continue
                if _order_ts(order) >= _order_ts(current):
                    dupes.append(current)
                    keep_by_key[key_info] = order
                else:
                    dupes.append(order)

            for order in dupes:
                ord_id = order.get("ordId")
                if ord_id:
                    try:
                        await exchange.cancel_order(inst_id=inst_id, order_id=str(ord_id))
                    except Exception:
                        pass
            if dupes:
                logger.info("lighter protection dedupe instId=%s cancelled=%d", inst_id, len(dupes))


@app.on_event("startup")
async def _startup() -> None:
    # Configure log rotation
    _configure_logging()

    # Connect Lighter exchange if using Lighter (async)
    if SETTINGS.exchange == "lighter":
        logger.info("Connecting to Lighter exchange (async via adapter)...")
        await exchange.connect()
        logger.info("✅ Lighter client connected via adapter")
        
        # Enable Lighter WebSocket for real-time monitoring
        LIGHTER_WS_SYMBOLS = [
            "ETH-USDT-SWAP", "BTC-USDT-SWAP", "SOL-USDT-SWAP", "LINK-USDT-SWAP",
            "DOGE-USDT-SWAP", "BNB-USDT-SWAP", "BCH-USDT-SWAP", "TRX-USDT-SWAP",
            "EIGEN-USDT-SWAP", "ETHFI-USDT-SWAP", "FARTCOIN-USDT-SWAP", "JTO-USDT-SWAP",
            "PUMP-USDT-SWAP", "TAO-USDT-SWAP", "TON-USDT-SWAP", "TRUMP-USDT-SWAP",
            "XRP-USDT-SWAP", "ONDO-USDT-SWAP", "LTC-USDT-SWAP",
        ]
        
        logger.info("🔌 Enabling Lighter WebSocket for real-time monitoring...")
        try:
            exchange.enable_websocket(auto_subscribe_account=False)
            
            ws_subscribed = 0
            for okx_symbol in LIGHTER_WS_SYMBOLS:
                lighter_symbol = okx_symbol.replace("-SWAP", "").replace("-", "/")
                
                # Orderbook handler
                def make_orderbook_handler(sym):
                    def handler(data):
                        try:
                            # Extract bid/ask from Lighter format
                            bids = data.get("bids", []) if isinstance(data, dict) else getattr(data, "bids", [])
                            asks = data.get("asks", []) if isinstance(data, dict) else getattr(data, "asks", [])
                            if bids and asks:
                                best_bid = float(bids[0]["price"]) / 10**6 if isinstance(bids[0], dict) else float(bids[0].price) / 10**6
                                best_ask = float(asks[0]["price"]) / 10**6 if isinstance(asks[0], dict) else float(asks[0].price) / 10**6
                                if best_bid > 0 and best_ask > 0:
                                    logger.info(f"📖 {sym} 盘口: bid={best_bid:.4f} ask={best_ask:.4f}")
                        except Exception as e:
                            logger.debug(f"Orderbook parse error for {sym}: {e}")
                    return handler
                
                await exchange.subscribe_orderbook_stream(lighter_symbol, make_orderbook_handler(okx_symbol))
                exchange.subscribe_trades_stream(lighter_symbol, lambda x: None)  # Placeholder
                ws_subscribed += 1
            
            # Start WebSocket after all subscriptions
            await exchange.start_websocket()
            
            logger.info(f"✅ Lighter WebSocket enabled: {ws_subscribed} symbols subscribed")
        
        except Exception as e:
            import traceback
            logger.error(f"❌ Failed to enable Lighter WebSocket: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.info("ℹ️  Continuing without WebSocket (REST API only)")

    if SETTINGS.trading_enabled and manager is not None:
        manager.start()
    if SETTINGS.trading_enabled and ws_manager is not None:
        ws_manager.start(
            enable_okx=SETTINGS.exchange == "okx",
            enable_extended=SETTINGS.exchange == "extended",
        )
    if SETTINGS.candle_ws_enabled and candle_ws_manager is not None:
        logger.info(f"Starting candle WebSocket manager (symbols: {len(candle_ws_symbol_tfs) if candle_ws_symbol_tfs else 0})")
        candle_ws_manager.start()
        if candle_ws_symbol_tfs:
            subscription_count = 0
            for inst_id, tfs in candle_ws_symbol_tfs.items():
                for tf in tfs:
                    await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf=tf)
                    subscription_count += 1
            logger.info(f"Candle WebSocket subscribed to {subscription_count} channels")
            stats = candle_ws_manager.get_stats()
            logger.info(f"Candle WebSocket stats: OKX {stats['okx']['subscribed']}/{stats['okx']['max']} ({stats['okx']['utilization']})")
    _start_telegram_control()
    if SETTINGS.health_log_seconds > 0:
        async def _health_loop() -> None:
            while True:
                await asyncio.sleep(SETTINGS.health_log_seconds)
                now = time.time()
                last_seen = last_webhook_ts
                age = None if last_seen is None else int(now - last_seen)
                logger.info(
                    "health_check uptime_s=%s last_webhook_age_s=%s webhook_count=%s",
                    int(now - STARTUP_TS),
                    age,
                    last_webhook_count,
                )
        global _health_task
        _health_task = asyncio.create_task(_health_loop())
    global _refresh_task
    if SETTINGS.exchange == "extended" and SETTINGS.extended_refresh_enabled:
        _refresh_task = asyncio.create_task(_refresh_extended_protection())
    if SETTINGS.exchange == "paradex" and SETTINGS.extended_refresh_enabled:
        _refresh_task = asyncio.create_task(_refresh_paradex_protection())
    if SETTINGS.exchange == "lighter" and SETTINGS.lighter_refresh_enabled:
        _refresh_task = asyncio.create_task(_refresh_lighter_protection())
        _refresh_task = asyncio.create_task(_dedupe_lighter_orders())


@app.on_event("shutdown")
async def _shutdown() -> None:
    if ws_manager is not None:
        try:
            await ws_manager.stop()
        except Exception as e:
            logger.error("Error stopping ws_manager: %s", str(e))
    if candle_ws_manager is not None:
        try:
            await candle_ws_manager.stop()
        except Exception as e:
            logger.error("Error stopping candle_ws_manager: %s", str(e))
    if tg_control is not None:
        try:
            tg_control.stop()
        except Exception as e:
            logger.error("Error stopping tg_control: %s", str(e))
    if _health_task is not None:
        _health_task.cancel()
    if _refresh_task is not None:
        _refresh_task.cancel()
    if SETTINGS.exchange == "extended":
        try:
            close_fn = getattr(exchange, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception as e:
            logger.error("Error closing extended exchange: %s", str(e))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics_endpoint() -> dict:
    """Get system metrics."""
    metrics = get_metrics()
    return metrics.get_summary()


@app.get("/emergency")
async def emergency_status() -> dict:
    """Get emergency positions status."""
    emergency_handler = get_emergency_handler()
    positions = await emergency_handler.get_emergency_positions()

    return {
        "count": len(positions),
        "positions": [
            {
                "inst_id": pos.inst_id,
                "pos_side": pos.pos_side,
                "size": pos.size,
                "entry_price": pos.entry_price,
                "stop_loss": pos.stop_loss,
                "failure_reason": pos.failure_reason,
                "age_seconds": int(time.time() - pos.timestamp),
                "retry_count": pos.retry_count,
                "max_retries": pos.max_retries,
            }
            for pos in positions
        ],
    }


@app.get("/rate_limits")
def rate_limits_endpoint() -> dict:
    """Get rate limiter statistics."""
    from app.rate_limiter import get_rate_limiter_stats

    return get_rate_limiter_stats()


@app.get("/websocket/stats")
def websocket_stats_endpoint() -> dict:
    """Get WebSocket subscription statistics."""
    if candle_ws_manager:
        return candle_ws_manager.get_stats()
    return {"error": "WebSocket manager not initialized"}


@app.post("/webhook/tradingview")
async def webhook_tradingview(req: Request) -> dict:
    raw_body = await req.body()
    logger.info(
        "tv_webhook request content_type=%s len=%s",
        req.headers.get("content-type"),
        len(raw_body),
    )
    try:
        import json

        data = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        snippet = raw_body[:500].decode("utf-8", errors="replace")
        logger.warning("tv_webhook invalid_json err=%s body=%s", e, snippet)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e
    except Exception as e:
        # Catch any other unexpected errors
        snippet = raw_body[:200].decode("utf-8", errors="replace")
        logger.error("tv_webhook unexpected_error err=%s body_snippet=%s", e, snippet, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e

    payload = TvPayload.model_validate(data)
    global last_webhook_ts, last_webhook_count
    last_webhook_ts = time.time()
    last_webhook_count += 1
    return await _process_payload(payload)


async def _process_payload(payload: TvPayload, *, allow_no_zone: bool = False) -> dict:
    inst_id = _normalize_inst_id(payload.instId)
    if inst_id != payload.instId:
        _log_decision(payload.instId, payload.tf, action="symbol_mapped", mapped=inst_id)
    if payload.secret != SETTINGS.tv_webhook_secret:
        _log_decision(inst_id, payload.tf, action="reject", reason="bad_secret")
        raise HTTPException(status_code=401, detail="Bad secret")
    if "*" not in SETTINGS.symbol_allowlist and inst_id not in allowed_symbols:
        _log_decision(inst_id, payload.tf, action="reject", reason="symbol_not_allowed")
        raise HTTPException(status_code=403, detail="Symbol not allowed")

    tf = payload.tf
    key = _key(inst_id, tf)

    _log_payload(payload)

    close_f: float | None = None
    if payload.close is not None and payload.close != "":
        try:
            close_f = float(payload.close)
        except ValueError:
            close_f = None
    payload_side = _parse_side(payload.side)
    skip_rsi_filter = payload_side is not None

    dedupe_key = _build_dedupe_key(payload, inst_id=inst_id, tf=tf, close_f=close_f)
    if state.seen(dedupe_key, ttl_seconds=SETTINGS.dedupe_ttl_seconds):
        _log_decision(inst_id, tf, action="skip", reason="deduped", dedupe_key=dedupe_key)
        return {"ok": True, "deduped": True}

    if candle_ws_manager is not None and SETTINGS.candle_ws_enabled:
        try:
            if candle_ws_symbol_tfs and SETTINGS.candle_ws_symbol_tfs_strict:
                allowed = candle_ws_symbol_tfs.get(inst_id)
                if allowed and tf.lower() in allowed:
                    await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf=tf)
            else:
                await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf=tf)
        except Exception:
            pass

    if payload.type.upper() == "ZONE":
        if payload.zone is None:
            raise HTTPException(status_code=400, detail="Missing zone")
        zone = payload.zone.upper()
        if zone not in {"OVERSOLD", "OVERBOUGHT", "NEUTRAL"}:
            raise HTTPException(status_code=400, detail="Invalid zone")
        state.set_zone(key, zone=zone, close=close_f)
        _log_decision(inst_id, tf, action="zone_set", zone=zone, close=close_f)
        return {"ok": True, "type": "ZONE", "zone": zone}

    if payload.type.upper() == "CLOSE":
        pos = await exchange.get_position(inst_id=inst_id, pos_side="long")
        if not pos:
            pos = await exchange.get_position(inst_id=inst_id, pos_side="short")
        if not pos or float(pos.get("pos", "0") or "0") == 0:
            _log_decision(inst_id, tf, action="close_skip", reason="no_position")
            return {"ok": True, "type": "CLOSE", "skipped": "no_position"}

        pos_side = pos.get("posSide", "long")
        close_side = "sell" if pos_side == "long" else "buy"
        close_sz = str(pos.get("pos"))

        if SETTINGS.exchange == "lighter":
            try:
                symbol = inst_id.replace("-SWAP", "").replace("-", "/")
                cancel_all_fn = getattr(exchange, "cancel_all_orders_for_symbol", None)
                if callable(cancel_all_fn):
                    canceled, failed = cancel_all_fn(symbol)
                    logger.info("lighter close cancel_all_orders symbol=%s canceled=%d failed=%d", symbol, canceled, failed)
            except Exception as e:
                logger.warning("lighter close cancel_all_orders_failed instId=%s err=%s", inst_id, e)
        await _cancel_pending_ladder_orders(key, inst_id, exchange)

        resp = await exchange.place_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side=close_side,
            pos_side=pos_side,
            ord_type="market",
            sz=close_sz,
            px=None,
            reduce_only=True,
        )
        _log_decision(inst_id, tf, action="close_order", side=close_side, posSide=pos_side, resp=resp)
        return {"ok": True, "type": "CLOSE", "order": resp}

    if payload.type.upper() != "DIV":
        raise HTTPException(status_code=400, detail="Unknown type")

    # DIV signal must specify side (buy/sell)
    if payload_side is None:
        _log_decision(inst_id, tf, action="skip", reason="missing_side")
        raise HTTPException(status_code=400, detail="DIV signal must specify 'side' field (buy or sell)")

    # Check cooldown
    if not state.can_trade(key, SETTINGS.cooldown_seconds):
        _log_decision(inst_id, tf, action="skip", reason="cooldown")
        return {"ok": True, "skipped": "cooldown"}

    side = payload_side
    pos_side = "long" if side == "buy" else "short"

    # Create a simple zone_state for logging purposes
    zone_state = SimpleNamespace(
        zone="OVERSOLD" if side == "buy" else "OVERBOUGHT",
        close=close_f,
    )

    # Fetch candles first to get real-time price
    desired_limit = max(300, SETTINGS.rsi_max_data + SETTINGS.rsi_length + 2)
    candles: list
    preferred_source = "extended" if SETTINGS.exchange == "extended" else "okx"
    candles = []
    if candle_cache is not None:
        cached = await candle_cache.get_candles(
            source=preferred_source,
            inst_id=inst_id,
            tf=tf,
            min_bars=desired_limit,
        )
        if cached:
            candles = cached[-desired_limit:]
        elif preferred_source == "extended":
            cached = await candle_cache.get_candles(
                source="okx",
                inst_id=inst_id,
                tf=tf,
                min_bars=desired_limit,
            )
            if cached:
                _log_decision(inst_id, tf, action="candles_cache_okx")
                candles = cached[-desired_limit:]

    if not candles:
        if SETTINGS.exchange == "extended" and hasattr(exchange, "fetch_candles"):
            candles = exchange.fetch_candles(inst_id=inst_id, tf=tf, limit=desired_limit)
            if candle_cache is not None and candles:
                await candle_cache.set_candles(
                    source="extended",
                    inst_id=inst_id,
                    tf=tf,
                    candles=candles,
                )
            if not candles:
                _log_decision(inst_id, tf, action="candles_fallback_okx")
                candles = fetch_candles_paged(SETTINGS.okx_base_url, inst_id, tf, limit=desired_limit)
                if candle_cache is not None and candles:
                    await candle_cache.set_candles(
                        source="okx",
                        inst_id=inst_id,
                        tf=tf,
                        candles=candles,
                    )
        else:
            candles = fetch_candles_paged(SETTINGS.okx_base_url, inst_id, tf, limit=desired_limit)
            if candle_cache is not None and candles:
                await candle_cache.set_candles(
                    source="okx",
                    inst_id=inst_id,
                    tf=tf,
                    candles=candles,
                )
    last_candle_close = candles[-1].c if candles else None

    # Priority: use real-time price from candles, fallback to payload close, then zone close
    entry_price = last_candle_close or close_f or (zone_state.close if zone_state is not None else None)

    if entry_price is None:
        _log_decision(inst_id, tf, action="skip", reason="no_entry_price")
        return {"ok": True, "skipped": "no_entry_price"}

    if not SETTINGS.trading_enabled:
        try:
            last_px = await exchange.get_last_price(inst_id=inst_id)
        except Exception:
            last_px = None
        if last_px is not None:
            _log_decision(
                inst_id,
                tf,
                action="paper_entry_market",
                entry=last_px,
                close=last_candle_close,
            )
            entry_price = last_px

    rsi_result = None
    rsi_from_payload = False
    payload_rsi = _parse_float(payload.rsi)
    payload_long = _parse_float(payload.rsi_long)
    payload_short = _parse_float(payload.rsi_short)
    if payload_rsi is not None and payload_long is not None and payload_short is not None:
        rsi_result = RsiThresholds(
            rsi=payload_rsi,
            long_threshold=payload_long,
            short_threshold=payload_short,
        )
        rsi_from_payload = True
        if SETTINGS.rsi_debug:
            _log_decision(
                inst_id,
                tf,
                action="rsi_from_tv",
                rsi=round(payload_rsi, 6),
                long=round(payload_long, 6),
                short=round(payload_short, 6),
            )

    rsi_candles = candles
    if not SETTINGS.rsi_use_live_candle and len(rsi_candles) > 1:
        rsi_candles = rsi_candles[:-1]
    if (SETTINGS.rsi_filter_enabled or SETTINGS.rsi_debug) and rsi_result is None:
        tf_key = tf.strip().lower()
        symbol_key = inst_id.strip().upper()
        rsi_max_data = rsi_max_data_symbol_overrides.get(
            (symbol_key, tf_key),
            rsi_max_data_symbol_overrides.get(
                (symbol_key, None),
                rsi_max_data_overrides.get(tf_key, SETTINGS.rsi_max_data),
            ),
        )
        rsi_low_pct, rsi_high_pct = rsi_pct_symbol_overrides.get(
            (symbol_key, tf_key),
            rsi_pct_symbol_overrides.get(
                (symbol_key, None),
                rsi_pct_overrides.get(tf_key, (SETTINGS.rsi_pct_low, SETTINGS.rsi_pct_high)),
            ),
        )
        closes = [c.c for c in rsi_candles]
        if SETTINGS.rsi_threshold_mode == "percentile":
            rsi_result = compute_rsi_thresholds_percentile(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=rsi_max_data,
                low_pct=rsi_low_pct,
                high_pct=rsi_high_pct,
            )
        else:
            rsi_result = compute_rsi_thresholds(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=rsi_max_data,
                max_iter=SETTINGS.rsi_max_iter,
            )
        if rsi_result is None:
            _log_decision(inst_id, tf, action="skip", reason="no_rsi")
            return {"ok": True, "skipped": "no_rsi"}
        if SETTINGS.rsi_debug and not rsi_from_payload:
            last_ts = rsi_candles[-1].ts_ms if rsi_candles else None
            last_close = rsi_candles[-1].c if rsi_candles else None
            rsi_samples = max(0, len(rsi_candles) - SETTINGS.rsi_length)
            used_samples = min(rsi_max_data, rsi_samples)
            alt = compute_rsi_thresholds_percentile(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=rsi_max_data,
                low_pct=rsi_low_pct,
                high_pct=rsi_high_pct,
            )
            _log_decision(
                inst_id,
                tf,
                action="rsi_debug",
                rsi=round(rsi_result.rsi, 6),
                long=round(rsi_result.long_threshold, 6),
                short=round(rsi_result.short_threshold, 6),
                mode=SETTINGS.rsi_threshold_mode,
                alt_long=round(alt.long_threshold, 6) if alt else None,
                alt_short=round(alt.short_threshold, 6) if alt else None,
                candles=len(rsi_candles),
                rsi_samples=rsi_samples,
                used_samples=used_samples,
                pct_low=rsi_low_pct,
                pct_high=rsi_high_pct,
                max_data=rsi_max_data,
                last_close=last_close,
                last_ts=last_ts,
                live=SETTINGS.rsi_use_live_candle,
            )
    if SETTINGS.rsi_filter_enabled and not skip_rsi_filter:
        if rsi_result is None:
            _log_decision(inst_id, tf, action="skip", reason="no_rsi")
            return {"ok": True, "skipped": "no_rsi"}

        if allow_no_zone or (zone_state is None and SETTINGS.rsi_allow_no_zone):
            if rsi_result.rsi <= rsi_result.short_threshold:
                side = "buy"
                pos_side = "long"
                zone_state = SimpleNamespace(zone="OVERSOLD", close=entry_price)
            elif rsi_result.rsi >= rsi_result.long_threshold:
                side = "sell"
                pos_side = "short"
                zone_state = SimpleNamespace(zone="OVERBOUGHT", close=entry_price)
            else:
                _log_decision(
                    inst_id,
                    tf,
                    action="skip",
                    reason="rsi_neutral",
                    rsi=round(rsi_result.rsi, 4),
                    long=round(rsi_result.long_threshold, 4),
                    short=round(rsi_result.short_threshold, 4),
                )
                return {"ok": True, "skipped": "rsi_neutral"}
        else:
            if side == "buy" and rsi_result.rsi >= rsi_result.short_threshold:
                _log_decision(
                    inst_id,
                    tf,
                    action="skip",
                    reason="rsi_not_oversold",
                    rsi=round(rsi_result.rsi, 4),
                    short=round(rsi_result.short_threshold, 4),
                )
                return {"ok": True, "skipped": "rsi_not_oversold"}
            if side == "sell" and rsi_result.rsi <= rsi_result.long_threshold:
                _log_decision(
                    inst_id,
                    tf,
                    action="skip",
                    reason="rsi_not_overbought",
                    rsi=round(rsi_result.rsi, 4),
                    long=round(rsi_result.long_threshold, 4),
                )
                return {"ok": True, "skipped": "rsi_not_overbought"}
    elif allow_no_zone:
        _log_decision(inst_id, tf, action="skip", reason="rsi_disabled_no_zone")
        return {"ok": True, "skipped": "rsi_disabled_no_zone"}

    if side == "buy" and not SETTINGS.enable_long:
        _log_decision(inst_id, tf, action="skip", reason="long_disabled")
        return {"ok": True, "skipped": "long_disabled"}
    if side == "sell" and not SETTINGS.enable_short:
        _log_decision(inst_id, tf, action="skip", reason="short_disabled")
        return {"ok": True, "skipped": "short_disabled"}

    pattern: dict | None = None
    if side == "buy" and SETTINGS.pattern_long != "none":
        if SETTINGS.pattern_long == "w_bottom":
            m = detect_w_bottom(
                candles,
                pivot_len=SETTINGS.pattern_pivot_len,
                tol_pct=SETTINGS.pattern_tol_pct,
                min_bounce_pct=SETTINGS.w_min_bounce_pct,
                require_breakout=SETTINGS.w_require_breakout,
            )
            pattern = {"name": m.name, "ok": m.ok, "detail": m.detail}
            if not m.ok:
                _log_decision(inst_id, tf, action="skip", reason="pattern_not_matched", pattern=pattern)
                return {"ok": True, "skipped": "pattern_not_matched", "pattern": pattern}
        else:
            _log_decision(inst_id, tf, action="skip", reason="pattern_invalid", pattern=SETTINGS.pattern_long)
            return {"ok": True, "skipped": "pattern_invalid", "pattern": SETTINGS.pattern_long}
    if side == "sell" and SETTINGS.pattern_short != "none":
        if SETTINGS.pattern_short == "hs_top":
            m = detect_head_shoulders_top(
                candles,
                pivot_len=SETTINGS.pattern_pivot_len,
                tol_pct=SETTINGS.pattern_tol_pct,
                min_shoulder_drop_pct=SETTINGS.hs_min_shoulder_drop_pct,
                require_breakdown=SETTINGS.hs_require_breakdown,
            )
            pattern = {"name": m.name, "ok": m.ok, "detail": m.detail}
            if not m.ok:
                _log_decision(inst_id, tf, action="skip", reason="pattern_not_matched", pattern=pattern)
                return {"ok": True, "skipped": "pattern_not_matched", "pattern": pattern}
        else:
            _log_decision(inst_id, tf, action="skip", reason="pattern_invalid", pattern=SETTINGS.pattern_short)
            return {"ok": True, "skipped": "pattern_invalid", "pattern": SETTINGS.pattern_short}

    if SETTINGS.stop_method == "pivot":
        sl = stop_loss_price(
            side=side,
            entry_price=float(entry_price),
            candles=candles,
            pivot_len=SETTINGS.pivot_len,
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    else:
        sl = stop_loss_price_lookback(
            side=side,
            entry_price=float(entry_price),
            candles=candles,
            lookback_bars=get_lookback_bars(tf),
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
    if sl is None:
        _log_decision(inst_id, tf, action="skip", reason="no_stoploss")
        return {"ok": True, "skipped": "no_stoploss"}
    if SETTINGS.min_stop_distance_bps > 0:
        min_dist = float(entry_price) * (SETTINGS.min_stop_distance_bps / 10_000.0)
        if side == "buy":
            sl = min(sl, float(entry_price) - min_dist)
        else:
            sl = max(sl, float(entry_price) + min_dist)
    # For ladder orders, allow some tolerance since actual fill price may differ from signal price
    # Tolerance: 0.5% (50 bps) - enough to account for ladder spread but still catch major errors
    tolerance_bps = 50 if SETTINGS.ladder_enabled else 0
    tolerance = float(entry_price) * (tolerance_bps / 10000.0)

    if side == "buy" and float(sl) >= float(entry_price) + tolerance:
        _log_decision(
            inst_id,
            tf,
            action="skip",
            reason="invalid_stoploss_sl_gte_entry",
            sl=sl,
            entry=float(entry_price),
            tolerance=tolerance,
        )
        return {
            "ok": True,
            "skipped": "invalid_stoploss",
            "reason": "sl_gte_entry",
            "sl": sl,
            "entry": float(entry_price),
        }
    if side == "sell" and float(sl) <= float(entry_price) - tolerance:
        _log_decision(
            inst_id,
            tf,
            action="skip",
            reason="invalid_stoploss_sl_lte_entry",
            sl=sl,
            entry=float(entry_price),
            tolerance=tolerance,
        )
        return {
            "ok": True,
            "skipped": "invalid_stoploss",
            "reason": "sl_lte_entry",
            "sl": sl,
            "entry": float(entry_price),
        }

    tp: float | None = None
    if SETTINGS.tp_enabled:
        tp = take_profit_price(side=side, entry_price=float(entry_price), stop_loss=float(sl), rr=SETTINGS.tp4_r)

    if not SETTINGS.trading_enabled:
        r_value = abs(float(entry_price) - float(sl))
        order_sz, size_meta = await _calculate_order_size(
            inst_id=inst_id,
            r_value=r_value,
            entry_price=float(entry_price),
            tf=tf,
        )
        if size_meta:
            from app.config import get_risk_per_trade
            logger.info(
                "tv_webhook risk_based_sizing tf=%s risk_usdt=%s r_value=%.4f coins=%.4f ct_val=%s contracts=%s actual_coins=%.4f",
                tf,
                get_risk_per_trade(tf),
                r_value,
                size_meta.get("calculated_sz_coins"),
                size_meta.get("ct_val"),
                order_sz,
                size_meta.get("actual_coins"),
            )
        _log_decision(
            inst_id,
            tf,
            action="paper_trade",
            side=side,
            posSide=pos_side,
            entry=float(entry_price),
            sl=sl,
            tp=tp,
            r=r_value,
            sz=order_sz,
            zone=zone_state.zone,
        )
        return {
            "ok": True,
            "paper": True,
            "instId": inst_id,
            "zone": zone_state.zone,
            "side": side,
            "posSide": pos_side,
            "entry": float(entry_price),
            "sl": sl,
            "tp": tp,
            "r": r_value,
            "order_sz": order_sz,
            "pattern": pattern,
        }

    # ========== 新的下单逻辑：以损订仓 ==========
    import random
    import asyncio

    # 1. 计算R值（风险距离）
    r_value = abs(float(entry_price) - float(sl))

    # 2. 计算仓位大小
    # NOTE: Fixed ORDER_SZ mode creates inconsistent risk across symbols.
    # E.g., 1 BTC contract ≈ $100k vs 1 DOGE contract ≈ $0.10
    # Use RISK_PER_TRADE_USDT for consistent risk management.
    # Now supports timeframe-specific risk: 15m=100U, 30m-4h=300U
    order_sz, size_meta = await _calculate_order_size(
        inst_id=inst_id,
        r_value=r_value,
        entry_price=float(entry_price),
        tf=tf,
    )
    if size_meta and size_meta.get("fixed_adjusted"):
        logger.info(
            "tv_webhook fixed_sizing_adjusted sz=%s min_order=%s",
            order_sz,
            size_meta.get("min_order"),
        )
    elif size_meta:
        from app.config import get_risk_per_trade
        logger.info(
            "tv_webhook risk_based_sizing tf=%s risk_usdt=%s r_value=%.4f coins=%.4f ct_val=%s contracts=%s actual_coins=%.4f",
            tf,
            get_risk_per_trade(tf),
            r_value,
            size_meta.get("calculated_sz_coins"),
            size_meta.get("ct_val"),
            order_sz,
            size_meta.get("actual_coins"),
        )
    else:
        logger.info("tv_webhook fixed_sizing sz=%s", order_sz)

    # 2.5 检查仓位冲突（避免重复开仓）
    check_conflict = SETTINGS.exchange != "lighter" or SETTINGS.lighter_block_duplicate_positions
    if check_conflict:
        existing_pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
        if existing_pos and float(existing_pos.get("pos", "0") or "0") != 0:
            existing_sz = float(existing_pos.get("pos", "0") or "0")
            existing_avg_px = float(existing_pos.get("avgPx", "0") or "0")
            logger.warning(
                "tv_webhook position_conflict_detected instId=%s posSide=%s existing_sz=%.2f existing_avg_px=%.5f new_sz=%s",
                inst_id, pos_side, existing_sz, existing_avg_px, order_sz
            )
            _log_decision(
                inst_id,
                tf,
                action="skip",
                reason="position_already_exists",
                existing_sz=existing_sz,
                existing_avg_px=existing_avg_px,
                new_sz=order_sz,
            )
            notify_error(
                f"⚠️ Position conflict detected\n"
                f"Symbol: {inst_id}\n"
                f"Direction: {pos_side}\n"
                f"Existing: {existing_sz:.2f} @ {existing_avg_px:.5f}\n"
                f"New signal: {order_sz} @ {entry_price}\n"
                f"Action: Skipped new order to avoid duplicate position"
            )
            return {
                "ok": False,
                "skipped": "position_conflict",
                "existing_position": {
                    "size": existing_sz,
                    "avgPx": existing_avg_px,
                },
                "new_order": {
                    "size": order_sz,
                    "entry": float(entry_price),
                },
            }

    if SETTINGS.exchange == "paradex":
        inst_info = await exchange.get_instrument_info(inst_id=inst_id)
        tick_size = inst_info.get("tickSz") if inst_info else None
        sl_px = _round_price_to_tick(sl, tick_size) if sl is not None else None

        ts = int(time.time())
        rnd = random.randint(100, 999)
        cl_ord_id = f"tv{ts}{rnd}{side[:1]}"[:32]
        entry_px = None
        if SETTINGS.order_type == "limit":
            entry_px = _round_price_to_tick(entry_price, tick_size)

        resp = await exchange.place_order(
            inst_id=inst_id,
            side=side,
            ord_type=SETTINGS.order_type,
            sz=order_sz,
            px=entry_px,
            cl_ord_id=cl_ord_id[:32],
            reduce_only=False,
            trigger_px=None,
        )
        if str(resp.get("code", "")) not in {"0", "success"}:
            notify_error(
                f"paradex entry rejected instId={inst_id} side={side} sz={order_sz} resp={resp}"
            )
            _log_decision(inst_id, tf, action="order_rejected", side=side, posSide=pos_side)
            return {"ok": False, "error": "entry_rejected", "order": resp}

        notify_info(
            f"paradex entry accepted instId={inst_id} side={side} sz={order_sz}"
        )

        actual_pos_sz = Decimal(str(order_sz))
        if SETTINGS.tp_enabled and r_value > 0:
            pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
            if pos and pos.get("pos"):
                actual_pos_sz = Decimal(str(pos.get("pos")))

        if sl_px is not None:
            sl_side = "sell" if side == "buy" else "buy"
            sl_resp = await exchange.place_order(
                inst_id=inst_id,
                side=sl_side,
                ord_type="stop_loss_market",
                sz=str(actual_pos_sz),
                px=None,
                cl_ord_id=f"{cl_ord_id}sl"[:32],
                reduce_only=True,
                trigger_px=sl_px,
            )
            if str(sl_resp.get("code", "")) not in {"0", "success"}:
                notify_error(
                    f"paradex sl failed instId={inst_id} side={sl_side} sz={actual_pos_sz} resp={sl_resp}"
                )
            else:
                notify_info(
                    f"paradex sl placed instId={inst_id} side={sl_side} sl={sl_px}"
                )

        tp_orders: list[dict[str, str]] = []
        if SETTINGS.tp_enabled and r_value > 0:
            tp_orders = await _build_tp_targets(
                inst_id=inst_id,
                side=side,
                entry_price=float(entry_price),
                sl=float(sl),
                total_sz=actual_pos_sz,
                tick_size=tick_size,
            )
            for target in tp_orders:
                tp_resp = await exchange.place_order(
                    inst_id=inst_id,
                    side="sell" if side == "buy" else "buy",
                    ord_type="take_profit_limit",
                    sz=target["size"],
                    px=target["price"],
                    cl_ord_id=f"{cl_ord_id}{target['tag']}"[:32],
                    reduce_only=True,
                    trigger_px=target["price"],
                )
                if str(tp_resp.get("code", "")) not in {"0", "success"}:
                    notify_error(
                        f"paradex tp failed instId={inst_id} tag={target['tag']} price={target['price']} sz={target['size']} resp={tp_resp}"
                    )
            if tp_orders:
                notify_info(
                    f"paradex tp orders placed instId={inst_id} count={len(tp_orders)}"
                )

        fill_tracker.register_entry(
            inst_id=inst_id,
            side=side,
            entry_price=float(entry_price),
            stop_loss=float(sl),
        )

        state.mark_traded(key)
        state.clear_zone(key)
        _log_decision(inst_id, tf, action="order_placed", side=side, posSide=pos_side, zone=zone_state.zone)

        return {
            "ok": True,
            "type": "DIV",
            "zone": zone_state.zone,
            "side": side,
            "posSide": pos_side,
            "entry": float(entry_price),
            "sl": sl,
            "tp": tp,
            "order_sz": order_sz,
            "r_value": r_value,
            "order": resp,
            "tp_orders": tp_orders,
        }

    if SETTINGS.exchange == "extended":
        # Get instrument info for price precision
        inst_info = await exchange.get_instrument_info(inst_id=inst_id)
        tick_size = inst_info.get("tickSz") if inst_info else None
        sl_px = _round_price_to_tick(sl, tick_size) if sl is not None else None

        ts = int(time.time())
        rnd = random.randint(100, 999)
        cl_ord_id = f"tv{ts}{rnd}{side[:1]}"[:32]

        try:
            resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=side,
                pos_side=pos_side,
                ord_type=SETTINGS.order_type,
                sz=order_sz,
                px=None,
                cl_ord_id=cl_ord_id[:32],
                sl_trigger_px=sl_px,
                tp_trigger_px=None,
                reduce_only=False,
            )
        except (ConnectionError, TimeoutError) as exc:
            logger.error("extended entry network_error instId=%s err=%s", inst_id, exc, exc_info=True)
            notify_error(
                f"extended entry network failure instId={inst_id} side={side} sz={order_sz} err={exc}"
            )
            raise HTTPException(status_code=503, detail=f"Exchange network error: {exc}") from exc
        except ValueError as exc:
            logger.error("extended entry invalid_params instId=%s err=%s", inst_id, exc, exc_info=True)
            notify_error(
                f"extended entry invalid params instId={inst_id} side={side} sz={order_sz} err={exc}"
            )
            raise HTTPException(status_code=400, detail=f"Invalid order parameters: {exc}") from exc
        except Exception as exc:
            logger.error("extended entry unexpected_error instId=%s err=%s", inst_id, exc, exc_info=True)
            notify_error(
                f"extended entry failed instId={inst_id} side={side} sz={order_sz} err={exc}"
            )
            raise

        if str(resp.get("code", "")) not in {"0", "success"}:
            notify_error(
                f"extended entry rejected instId={inst_id} side={side} sz={order_sz} resp={resp}"
            )
            _log_decision(inst_id, tf, action="order_rejected", side=side, posSide=pos_side)
            return {"ok": False, "error": "entry_rejected", "order": resp}
        notify_info(
            f"extended entry accepted instId={inst_id} side={side} sz={order_sz}"
        )
        if sl_px is not None:
            notify_info(
                f"extended sl attached instId={inst_id} side={side} sl={sl_px}"
            )
        fill_tracker.register_entry(
            inst_id=inst_id,
            side=side,
            entry_price=float(entry_price),
            stop_loss=float(sl),
        )

        # Place multi-level take-profit reduce-only limit orders.
        tp_orders: list[dict[str, str]] = []
        if SETTINGS.tp_enabled and r_value > 0:
            allow_tp = True
            actual_pos_sz = Decimal(str(order_sz))
            if SETTINGS.exchange == "extended":
                # Verify position exists before placing TP orders
                max_retries = 3
                for retry in range(max_retries):
                    pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
                    if pos:
                        pos_sz = Decimal(str(pos.get("pos", "0"))) if pos else Decimal("0")
                        if pos_sz > 0:
                            actual_pos_sz = pos_sz
                            break
                    if retry < max_retries - 1:
                        await asyncio.sleep(0.5)
                else:
                    # Position not found after retries
                    allow_tp = False
                    logger.warning(
                        "extended tp skipped instId=%s posSide=%s reason=no_position_after_retries",
                        inst_id, pos_side
                    )
                    notify_info(
                        f"extended tp skipped instId={inst_id} posSide={pos_side} reason=no_position"
                    )
            if not allow_tp:
                # Don't return here - continue to mark traded
                state.mark_traded(key)
                state.clear_zone(key)
                _log_decision(inst_id, tf, action="order_placed_no_tp", side=side, posSide=pos_side, zone=zone_state.zone)
                return {
                    "ok": True,
                    "type": "DIV",
                    "zone": zone_state.zone,
                    "side": side,
                    "posSide": pos_side,
                    "entry": float(entry_price),
                    "sl": sl,
                    "tp": None,
                    "order_sz": order_sz,
                    "r_value": r_value,
                    "order": resp,
                    "warning": "tp_skipped_no_position",
                }
            tp_orders = await _place_extended_tp_orders(
                inst_id=inst_id,
                side=side,
                pos_side=pos_side,
                entry_price=float(entry_price),
                sl=float(sl),
                total_sz=actual_pos_sz,
                tick_size=tick_size,
                cl_ord_id=cl_ord_id,
            )
            if tp_orders:
                notify_info(
                    f"extended tp orders placed instId={inst_id} count={len(tp_orders)}"
                )

        state.mark_traded(key)
        state.clear_zone(key)
        _log_decision(inst_id, tf, action="order_placed", side=side, posSide=pos_side, zone=zone_state.zone)

        return {
            "ok": True,
            "type": "DIV",
            "zone": zone_state.zone,
            "side": side,
            "posSide": pos_side,
            "entry": float(entry_price),
            "sl": sl,
            "tp": tp,
            "order_sz": order_sz,
            "r_value": r_value,
            "order": resp,
            "tp_orders": tp_orders,
        }

    # 3. 下单（市价单或分级挂单）
    ts = int(time.time())
    rnd = random.randint(100, 999)

    # Get instrument info for price precision
    inst_info = await exchange.get_instrument_info(inst_id=inst_id)
    tick_size = inst_info.get("tickSz") if inst_info else None

    ladder_orders = []  # Track all ladder orders
    market_sz = None

    if SETTINGS.ladder_enabled:
        # Ladder orders: 70% market + 30% limit (L1: 20%, L2: 10%)
        total_sz = Decimal(str(order_sz))

        # Get instrument lot size info for proper normalization
        inst_info = await exchange.get_instrument_info(inst_id=inst_id)
        lot_step = Decimal(str(inst_info.get("lotStep"))) if inst_info and inst_info.get("lotStep") else None
        min_order_sz = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else None

        # Calculate sizes for each order type and normalize to lot size
        market_sz_raw = total_sz * Decimal(str(SETTINGS.ladder_market_pct))
        level1_sz_raw = total_sz * Decimal(str(SETTINGS.ladder_level1_pct))
        level2_sz_raw = total_sz * Decimal(str(SETTINGS.ladder_level2_pct))
        level3_sz_raw = total_sz * Decimal(str(SETTINGS.ladder_level3_pct))

        market_sz = _normalize_qty(market_sz_raw, step=lot_step, min_sz=min_order_sz) if market_sz_raw > 0 else Decimal("0")
        level1_sz = _normalize_qty(level1_sz_raw, step=lot_step, min_sz=min_order_sz) if level1_sz_raw > 0 else Decimal("0")
        level2_sz = _normalize_qty(level2_sz_raw, step=lot_step, min_sz=min_order_sz) if level2_sz_raw > 0 else Decimal("0")
        level3_sz = _normalize_qty(level3_sz_raw, step=lot_step, min_sz=min_order_sz) if level3_sz_raw > 0 else Decimal("0")

        # 1. Place market order first (70%)
        market_cl_ord_id = f"tv{ts}{rnd}{side[:1]}M"[:32]
        market_filled_price = None

        if market_sz > 0:
            market_resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=side,
                pos_side=pos_side,
                ord_type="market",
                sz=str(market_sz),
                px=None,
                cl_ord_id=market_cl_ord_id,
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=False,
            )

            if str(market_resp.get("code", "")) not in {"0", "success"}:
                notify_error(
                    f"okx ladder market order rejected instId={inst_id} side={side} sz={market_sz} resp={market_resp}"
                )
            else:
                logger.info("tv_webhook ladder_market_order_placed sz=%s", market_sz)

                # Wait briefly for market order to fill
                await asyncio.sleep(0.5)
                try:
                    market_ord_info = await exchange.get_order(inst_id=inst_id, cl_ord_id=market_cl_ord_id)
                    if market_ord_info and market_ord_info.get("avgPx"):
                        market_filled_price = float(market_ord_info.get("avgPx"))
                        market_filled_sz = float(market_ord_info.get("accFillSz", "0") or "0")
                        ladder_orders.append({
                            "cl_ord_id": market_cl_ord_id,
                            "size": market_filled_sz,
                            "price": market_filled_price,
                            "level": "MARKET",
                            "bps": 0,
                        })
                        logger.info("tv_webhook ladder_market_filled px=%.6f sz=%.1f", market_filled_price, market_filled_sz)
                except Exception as e:
                    logger.warning("tv_webhook market_order_query_failed err=%s", str(e))

        # 2. Place limit orders (30%: L1=20%, L2=10%)
        signal_price = float(entry_price)
        if side == "buy":
            # Buy lower: signal_price * (1 - bps/10000)
            level1_px = signal_price * (1 - SETTINGS.ladder_level1_bps / 10000)
            level2_px = signal_price * (1 - SETTINGS.ladder_level2_bps / 10000)
            level3_px = signal_price * (1 - SETTINGS.ladder_level3_bps / 10000)
        else:
            # Sell higher: signal_price * (1 + bps/10000)
            level1_px = signal_price * (1 + SETTINGS.ladder_level1_bps / 10000)
            level2_px = signal_price * (1 + SETTINGS.ladder_level2_bps / 10000)
            level3_px = signal_price * (1 + SETTINGS.ladder_level3_bps / 10000)

        # Place limit orders
        limit_levels = [
            (level1_sz, level1_px, "L1", SETTINGS.ladder_level1_bps),
            (level2_sz, level2_px, "L2", SETTINGS.ladder_level2_bps),
            (level3_sz, level3_px, "L3", SETTINGS.ladder_level3_bps),
        ]

        for sz, px, label, bps in limit_levels:
            if sz <= 0:
                continue

            limit_cl_ord_id = f"tv{ts}{rnd}{side[:1]}{label}"[:32]
            px_rounded = _round_price_to_tick(px, tick_size)

            resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=side,
                pos_side=pos_side,
                ord_type="limit",
                sz=str(sz),
                px=px_rounded,
                cl_ord_id=limit_cl_ord_id,
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=False,
            )

            if str(resp.get("code", "")) not in {"0", "success"}:
                notify_error(
                    f"okx ladder {label} rejected instId={inst_id} side={side} sz={sz} px={px_rounded} resp={resp}"
                )
            else:
                ladder_orders.append({
                    "cl_ord_id": limit_cl_ord_id,
                    "size": float(sz),
                    "price": float(px_rounded),
                    "level": label,
                    "bps": bps,
                })
                logger.info("tv_webhook ladder_limit_order_placed level=%s sz=%s px=%s bps=%.1f", label, sz, px_rounded, bps)

                # Record pending order in state for later cancellation
                # Convert inst_id to symbol format for Lighter compatibility
                symbol_for_state = inst_id.replace("-USDT-SWAP", "/USDT")
                state.add_pending_order(
                    key=key,
                    order_id=limit_cl_ord_id,
                    symbol=symbol_for_state,
                    level=label
                )

        notify_info(
            f"okx ladder orders placed instId={inst_id} side={side} total_sz={order_sz} "
            f"market={market_sz}({SETTINGS.ladder_market_pct:.0%}) "
            f"limit={level1_sz + level2_sz + level3_sz}(L1={level1_sz} L2={level2_sz} L3={level3_sz}) "
            f"signal={signal_price:.6f}"
        )

        # Use market order's cl_ord_id as reference
        cl_ord_id = market_cl_ord_id
    else:
        # Single market order (original logic)
        cl_ord_id = f"tv{ts}{rnd}{side[:1]}"[:32]

        resp = await exchange.place_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side=side,
            pos_side=pos_side,
            ord_type="market",
            sz=order_sz,
            px=None,
            cl_ord_id=cl_ord_id[:32],
            sl_trigger_px=None,
            tp_trigger_px=None,
            reduce_only=False,
        )
        if str(resp.get("code", "")) not in {"0", "success"}:
            notify_error(
                f"okx entry rejected instId={inst_id} side={side} sz={order_sz} resp={resp}"
            )
            if SETTINGS.exchange == "lighter":
                _log_decision(inst_id, tf, action="order_rejected", side=side, posSide=pos_side)
                return {"ok": False, "error": "entry_rejected", "order": resp}

    # 4. 等待成交并获取实际成交价（带重试机制）
    filled_price = None
    total_filled_sz = 0.0
    ord_info = None
    ord_info = None
    entry_source = "unknown"

    if SETTINGS.ladder_enabled and ladder_orders:
        if SETTINGS.exchange == "lighter":
            # Lighter fills: try trade history (order_index) first, then position as fallback.
            await asyncio.sleep(1.0)
            filled_price = None
            total_filled_sz = 0.0
            entry_source = "signal"
            try:
                store = getattr(exchange, "_okx_compat_state", None)
                if store:
                    filled_value = 0.0
                    for ladder_ord in ladder_orders:
                        cl_ord_id = ladder_ord.get("cl_ord_id", "")
                        order_id = store.get("cl_to_order", {}).get(cl_ord_id, cl_ord_id)
                        try:
                            fills = await exchange.get_order_fills(inst_id=inst_id, order_id=str(order_id))
                        except Exception:
                            fills = None
                        if fills:
                            fill_sz, fill_px = fills
                            if fill_sz > 0 and fill_px > 0:
                                total_filled_sz += fill_sz
                                filled_value += fill_sz * fill_px
                    if total_filled_sz > 0 and filled_value > 0:
                        filled_price = filled_value / total_filled_sz
                        entry_source = "fills"
            except Exception as e:
                logger.warning("tv_webhook lighter_fill_fetch_failed err=%s", str(e))

            for _ in range(3):
                try:
                    pos = await exchange.get_position(inst_id=inst_id, pos_side=pos_side)
                    if pos and float(pos.get("pos", "0") or "0") > 0:
                        total_filled_sz = float(pos.get("pos", "0") or "0")
                        avg_px = pos.get("avgPx")
                        if avg_px:
                            avg_val = float(avg_px)
                            if avg_val > 0:
                                filled_price = avg_val
                                entry_source = "position"
                        break
                except Exception:
                    pass
                await asyncio.sleep(1.0)
            if filled_price is None:
                filled_price = market_filled_price or float(entry_price)
                entry_source = "signal"
            if total_filled_sz == 0.0:
                total_filled_sz = float(market_sz) if market_sz is not None else float(order_sz)
            logger.info(
                "tv_webhook ladder_lighter_assume_filled px=%.6f sz=%.1f source=%s",
                filled_price,
                total_filled_sz,
                entry_source,
            )
        else:
            # For ladder orders: calculate weighted average fill price using TF-based wait times
            candle_seconds = tf_to_seconds(tf)
            base_wait_candles = get_ladder_wait_candles(tf)
            max_wait_candles = get_ladder_max_wait_candles(tf)
            price_distance_threshold = get_ladder_price_distance(tf)

            base_wait_time = candle_seconds * base_wait_candles  # e.g., 5m * 0.5 = 150s
            max_wait_time = candle_seconds * max_wait_candles    # e.g., 5m * 1 = 300s
            check_interval = min(10, max(2, candle_seconds / 30))  # Check every 2-10s depending on TF

            max_retries = int(max_wait_time / check_interval)
            has_partial_fills = False

            logger.info("tv_webhook ladder_wait_config tf=%s candle_sec=%d base_wait=%.1fs max_wait=%.1fs interval=%.1fs",
                       tf, candle_seconds, base_wait_time, max_wait_time, check_interval)

            # Initial check after brief delay
            await asyncio.sleep(1.0)

            filled_levels = []
            for retry in range(max_retries):
                if retry > 0:
                    await asyncio.sleep(check_interval)

                total_filled_value = 0.0
                total_filled_sz = 0.0
                all_checked = True

                for ladder_ord in ladder_orders:
                    try:
                        ord_info = await exchange.get_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])
                        if ord_info:
                            order_state = ord_info.get("state", "").lower()
                            avg_px = ord_info.get("avgPx")
                            acc_fill_sz = float(ord_info.get("accFillSz", "0") or "0")

                            if avg_px and acc_fill_sz > 0:
                                px = float(avg_px)
                                total_filled_value += px * acc_fill_sz
                                total_filled_sz += acc_fill_sz
                                if ladder_ord["level"] not in [f["level"] for f in filled_levels]:
                                    filled_levels.append({
                                        "level": ladder_ord["level"],
                                        "price": px,
                                        "size": acc_fill_sz,
                                    })
                            elif order_state == "live":
                                all_checked = False  # Still waiting for this order
                    except Exception as e:
                        logger.warning("tv_webhook ladder_query_failed level=%s err=%s", ladder_ord["level"], str(e))
                        all_checked = False

                # Calculate weighted average
                if total_filled_sz > 0:
                    filled_price = total_filled_value / total_filled_sz
                    has_partial_fills = True

                    elapsed_time = (retry + 1) * check_interval
                    logger.info("tv_webhook ladder_filled avg_px=%.4f total_sz=%.1f levels=%d elapsed=%.1fs retry=%d",
                               filled_price, total_filled_sz, len(filled_levels), elapsed_time, retry)

                    # Check if should stop waiting
                    should_stop = False
                    if all_checked:
                        # All orders checked
                        should_stop = True
                    elif elapsed_time >= max_wait_time:
                        # Max wait time exceeded
                        logger.info("tv_webhook max_wait_reached elapsed=%.1fs max=%.1fs", elapsed_time, max_wait_time)
                        should_stop = True

                    if should_stop:
                        notify_info(
                            f"okx ladder filled instId={inst_id} side={side} avg_px={filled_price:.6f} "
                            f"sz={total_filled_sz:.1f}/{order_sz} levels={len(filled_levels)} "
                            f"wait={elapsed_time:.1f}s"
                        )

                        # Cancel any unfilled limit orders (skip market order)
                        if total_filled_sz < float(order_sz):
                            logger.info("tv_webhook canceling_unfilled_ladder_orders filled=%.1f planned=%s",
                                       total_filled_sz, order_sz)
                            for ladder_ord in ladder_orders:
                                if ladder_ord["level"] == "MARKET":
                                    continue  # Skip market order (already filled)
                                try:
                                    ord_info = await exchange.get_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])
                                    if ord_info and ord_info.get("state", "").lower() in {"live", "partially_filled"}:
                                        cancel_resp = await exchange.cancel_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])
                                        if str(cancel_resp.get("code", "")) in {"0", "success"}:
                                            logger.info("tv_webhook canceled_ladder_order level=%s", ladder_ord["level"])
                                        else:
                                            logger.warning("tv_webhook cancel_ladder_failed level=%s resp=%s",
                                                          ladder_ord["level"], cancel_resp)
                                except Exception as e:
                                    logger.warning("tv_webhook cancel_ladder_error level=%s err=%s",
                                                 ladder_ord["level"], str(e))

                        # Clear pending orders from state (whether fully filled or partially filled with cancellations)
                        state.clear_pending_orders(key)
                        break
                else:
                    # No fills yet
                    elapsed_time = (retry + 1) * check_interval

                    if elapsed_time >= base_wait_time:
                        # Base wait time exceeded with no fills - should only happen if market order failed
                        logger.error("tv_webhook ladder_no_fills_canceling_all elapsed=%.1fs base_wait=%.1fs",
                                   elapsed_time, base_wait_time)

                        # Cancel all ladder orders
                        for ladder_ord in ladder_orders:
                            try:
                                cancel_resp = await exchange.cancel_order(inst_id=inst_id, cl_ord_id=ladder_ord["cl_ord_id"])
                                if str(cancel_resp.get("code", "")) in {"0", "success"}:
                                    logger.info("tv_webhook canceled_unfilled_ladder level=%s", ladder_ord["level"])
                            except Exception as e:
                                logger.warning("tv_webhook cancel_unfilled_error level=%s err=%s",
                                             ladder_ord["level"], str(e))

                        # Clear pending orders from state
                        state.clear_pending_orders(key)

                        # Return error to stop execution
                        notify_error(
                            f"⚠️ Ladder orders not filled\n"
                            f"Symbol: {inst_id}\n"
                            f"Direction: {side}\n"
                            f"Planned: {order_sz} contracts\n"
                            f"Filled: 0 (market order may have failed)\n"
                            f"Action: Canceled all orders, stopped execution"
                        )
                        _log_decision(inst_id, tf, action="error", reason="ladder_no_fills")
                        return {
                            "ok": False,
                            "error": "ladder_no_fills",
                            "instId": inst_id,
                            "side": side,
                            "planned_sz": order_sz,
                            "filled_sz": 0,
                        }
                        break
            # End of non-lighter ladder wait
    else:
        # Single order (market or limit): original logic
        max_retries = 2 if SETTINGS.exchange == "lighter" else 10  # Lighter doesn't return avgPx reliably
        for retry in range(max_retries):
            await asyncio.sleep(0.2 * (retry + 1))  # Progressive backoff
            try:
                ord_info = await exchange.get_order(inst_id=inst_id, cl_ord_id=cl_ord_id)
                if ord_info and ord_info.get("avgPx"):
                    filled_price = float(ord_info.get("avgPx"))
                    total_filled_sz = float(ord_info.get("accFillSz", order_sz))
                    logger.info("tv_webhook order_filled cl_ord_id=%s filled_price=%.4f retry=%d",
                               cl_ord_id, filled_price, retry)
                    notify_info(
                        f"okx entry filled instId={inst_id} side={side} px={filled_price:.6f} sz={total_filled_sz}"
                    )
                    break
                # Check order state
                state_val = ord_info.get("state", "").lower() if ord_info else ""
                if state_val in {"filled", "partially_filled"}:
                    if retry < max_retries - 1:
                        continue
            except Exception as e:
                logger.warning("tv_webhook order_query_failed retry=%d err=%s", retry, str(e))
                if retry < max_retries - 1:
                    continue

    if filled_price is None:
        filled_price = float(entry_price)
        total_filled_sz = float(order_sz) if total_filled_sz == 0 else total_filled_sz
        logger.warning("tv_webhook no_filled_price_after_retries using_estimated price=%.4f", filled_price)

    # 5. 基于实际成交价重新计算止损价
    if ord_info and ord_info.get("avgPx"):
        if SETTINGS.stop_method == "pivot":
            sl_actual = stop_loss_price(
                side=side,
                entry_price=filled_price,
                candles=candles,
                pivot_len=SETTINGS.pivot_len,
                atr_len=SETTINGS.atr_len,
                atr_buffer_mult=SETTINGS.atr_buffer_mult,
                min_buffer_bps=SETTINGS.min_buffer_bps,
            )
        else:
            sl_actual = stop_loss_price_lookback(
                side=side,
                entry_price=filled_price,
                candles=candles,
                lookback_bars=get_lookback_bars(tf),
                atr_len=SETTINGS.atr_len,
                atr_buffer_mult=SETTINGS.atr_buffer_mult,
                min_buffer_bps=SETTINGS.min_buffer_bps,
            )

        if sl_actual:
            # Validate recalculated stop loss
            sl_valid = True
            if side == "buy" and sl_actual >= filled_price:
                logger.error("tv_webhook recalculated_sl_invalid_buy sl=%.4f >= entry=%.4f", sl_actual, filled_price)
                sl_valid = False
            elif side == "sell" and sl_actual <= filled_price:
                logger.error("tv_webhook recalculated_sl_invalid_sell sl=%.4f <= entry=%.4f", sl_actual, filled_price)
                sl_valid = False

            if sl_valid:
                sl = sl_actual
                r_value_actual = abs(filled_price - sl)
                logger.info("tv_webhook recalculated_sl entry=%.4f sl=%.4f r=%.4f", filled_price, sl, r_value_actual)
            else:
                logger.warning("tv_webhook using_original_sl sl=%.4f (recalculated was invalid)", sl)
        else:
            logger.warning("tv_webhook failed_to_recalculate_sl using_original sl=%.4f", sl)

    fill_tracker.register_entry(
        inst_id=inst_id,
        side=side,
        entry_price=float(filled_price),
        stop_loss=float(sl),
    )
    state.set_entry(
        inst_id=inst_id,
        side=side,
        entry_price=float(filled_price),
        stop_loss=float(sl),
    )
    if SETTINGS.exchange == "lighter":
        logger.info(
            "lighter entry persisted instId=%s side=%s entry=%.6f sl=%.6f source=%s",
            inst_id,
            side,
            float(filled_price),
            float(sl),
            entry_source,
        )

    # 6. 下单独的止损单
    sl_side = "sell" if side == "buy" else "buy"
    sl_order_success = False
    sl_failure_reason = ""

    # Use actual filled size for SL order, normalized to lot size
    inst_info = await exchange.get_instrument_info(inst_id=inst_id)
    lot_step = Decimal(str(inst_info.get("lotStep"))) if inst_info and inst_info.get("lotStep") else None
    min_order = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else None

    filled_sz_decimal = Decimal(str(total_filled_sz)) if total_filled_sz > 0 else Decimal(str(order_sz))
    normalized_sl_sz = _normalize_qty(filled_sz_decimal, step=lot_step, min_sz=min_order)
    sl_order_sz = _format_decimal(normalized_sl_sz)

    # Check current market price before placing SL order
    # If price has already moved past SL, close immediately instead
    try:
        current_price = await exchange.get_last_price(inst_id=inst_id) or 0.0

        if current_price > 0:
            # For long: SL should be below current price
            # For short: SL should be above current price
            sl_invalid = False
            if side == "buy" and sl >= current_price:
                sl_invalid = True
                logger.warning("tv_webhook sl_price_invalid_long current=%.4f sl=%.4f (SL must be < current)",
                              current_price, sl)
            elif side == "sell" and sl <= current_price:
                sl_invalid = True
                logger.warning("tv_webhook sl_price_invalid_short current=%.4f sl=%.4f (SL must be > current)",
                              current_price, sl)

            if sl_invalid:
                # Price already past SL, close position immediately
                logger.error("tv_webhook sl_already_breached closing_immediately current=%.4f sl=%.4f",
                            current_price, sl)

                # Cancel any pending ladder orders before closing
                await _cancel_pending_ladder_orders(key, inst_id, exchange)

                notify_error(
                    f"⚠️ 止损已触发 - 立即平仓\n"
                    f"交易对: {inst_id}\n"
                    f"方向: {side}\n"
                    f"成交价: {filled_price:.6f}\n"
                    f"止损位: {sl:.6f}\n"
                    f"当前价: {current_price:.6f}\n"
                    f"数量: {sl_order_sz}"
                )
                # Try to close position immediately
                close_resp = await exchange.place_order(
                    inst_id=inst_id,
                    td_mode=SETTINGS.okx_td_mode,
                    side=sl_side,
                    pos_side=pos_side,
                    ord_type="market",
                    sz=sl_order_sz,
                    px=None,
                    reduce_only=True,
                )
                if str(close_resp.get("code", "")) in {"0", "success"}:
                    logger.info("tv_webhook emergency_close_success sz=%s resp=%s", sl_order_sz, close_resp)
                    # Skip SL order placement since we closed
                    sl_order_success = True
                    return {
                        "ok": True,
                        "action": "emergency_close",
                        "instId": inst_id,
                        "side": side,
                        "entry": float(filled_price),
                        "sl": sl,
                        "current_price": current_price,
                        "closed_sz": sl_order_sz,
                    }
                else:
                    logger.error("tv_webhook emergency_close_failed resp=%s", close_resp)
                    sl_failure_reason = f"emergency_close_failed: {close_resp}"
    except Exception as e:
        logger.warning("tv_webhook market_price_check_failed err=%s continuing_with_sl", str(e))

    try:
        sl_resp = await exchange.place_algo_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side=sl_side,
            pos_side=pos_side,
            ord_type="conditional",
            sz=sl_order_sz,
            sl_trigger_px=_round_price_to_tick(sl, tick_size),
            sl_ord_px="-1",
        )
        logger.info("tv_webhook sl_order_placed sl_price=%.4f resp=%s", sl, sl_resp)
        if str(sl_resp.get("code", "")) not in {"0", "success"}:
            sl_failure_reason = f"code={sl_resp.get('code')} msg={sl_resp.get('msg')}"
            notify_error(
                f"okx sl failed instId={inst_id} side={sl_side} sz={order_sz} resp={sl_resp}"
            )
        else:
            sl_order_success = True
            data = sl_resp.get("data") or []
            if data:
                algo_id = data[0].get("algoId") or ""
                if algo_id:
                    fill_tracker.register_algo_label(algo_id=algo_id, label="sl")
    except Exception as e:
        sl_failure_reason = f"exception={str(e)}"
        logger.error("tv_webhook sl_order_failed error=%s", str(e))
        notify_error(f"okx sl exception instId={inst_id} err={e}")

    # Record metrics
    metrics = get_metrics()
    metrics.record_sl_attempt(success=sl_order_success, inst_id=inst_id, reason=sl_failure_reason)

    # Try backup stop-loss strategy if enabled
    backup_sl_attempted = False
    if not sl_order_success and SETTINGS.backup_sl_enabled:
        backup_sl_attempted = True
        logger.info("tv_webhook trying_backup_sl instId=%s method=limit_order", inst_id)
        try:
            backup_sl_resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=sl_side,
                pos_side=pos_side,
                ord_type="limit",
                sz=sl_order_sz,
                px=_round_price_to_tick(sl, tick_size),
                cl_ord_id=f"{cl_ord_id}_slb"[:32],
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=True,
            )
            if str(backup_sl_resp.get("code", "")) in {"0", "success"}:
                sl_order_success = True
                logger.info("tv_webhook backup_sl_success instId=%s resp=%s", inst_id, backup_sl_resp)
                notify_info(f"okx backup SL placed (limit order) for {inst_id} at {sl}")
                data = backup_sl_resp.get("data") or []
                if data:
                    ord_id = data[0].get("ordId") or ""
                    if ord_id:
                        fill_tracker.register_order_label(key=ord_id, label="sl_backup")
        except Exception as backup_err:
            logger.error("tv_webhook backup_sl_failed instId=%s err=%s", inst_id, str(backup_err), exc_info=True)

    # Emergency handling if stop-loss order failed
    if not sl_order_success:
        logger.error("tv_webhook sl_critical_failure instId=%s posSide=%s sz=%s reason=sl_order_failed",
                     inst_id, pos_side, order_sz)

        # Check if we should alert based on failure rate
        if metrics.should_alert(threshold=0.05, min_attempts=10):
            notify_error(
                f"⚠️ HIGH SL FAILURE RATE: {metrics.sl_failure_rate:.1%} "
                f"({metrics.sl_orders_failed}/{metrics.sl_orders_attempted} attempts)"
            )

        # Register with emergency handler for monitoring
        emergency_handler = get_emergency_handler()
        await emergency_handler.register_emergency(
            inst_id=inst_id,
            pos_side=pos_side,
            size=order_sz,
            entry_price=filled_price,
            stop_loss=float(sl),
            cl_ord_id=cl_ord_id,
            failure_reason=f"SL order failed (backup_attempted={backup_sl_attempted}): {sl_failure_reason}",
        )

        # Attempt emergency market close
        emergency_close_success = False
        emergency_close_resp = None
        try:
            # Cancel any pending ladder orders before emergency close
            await _cancel_pending_ladder_orders(key, inst_id, exchange)

            # Use actual filled size for emergency close
            emergency_sz = str(total_filled_sz) if total_filled_sz > 0 else order_sz
            logger.critical(
                "tv_webhook attempting_emergency_close instId=%s posSide=%s sz=%s",
                inst_id, pos_side, emergency_sz
            )
            emergency_close_resp = await exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=sl_side,
                pos_side=pos_side,
                ord_type="market",
                sz=emergency_sz,
                px=None,
                cl_ord_id=f"{cl_ord_id}_emerg"[:32],
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=True,
            )

            if str(emergency_close_resp.get("code", "")) in {"0", "success"}:
                emergency_close_success = True
                metrics.record_emergency_close(success=True, inst_id=inst_id)
                logger.info("tv_webhook emergency_close_success instId=%s resp=%s", inst_id, emergency_close_resp)
                notify_error(
                    f"⚠️ Emergency close executed: {inst_id}\n"
                    f"Side: {pos_side}\n"
                    f"Size: {emergency_sz}\n"
                    f"Reason: SL order failed\n"
                    f"Response: {emergency_close_resp.get('code')}"
                )
                # Clear from emergency handler if close successful
                await emergency_handler.clear_emergency(inst_id, pos_side)
                # Skip marking traded and registering plan since position was closed
                return {
                    "ok": False,
                    "error": "stop_loss_failed_position_closed",
                    "instId": inst_id,
                    "emergency_close": emergency_close_resp,
                }
            else:
                logger.error("tv_webhook emergency_close_rejected instId=%s resp=%s", inst_id, emergency_close_resp)
                metrics.record_emergency_close(success=False, inst_id=inst_id)

        except Exception as close_err:
            metrics.record_emergency_close(success=False, inst_id=inst_id)
            logger.critical(
                "tv_webhook emergency_close_exception instId=%s err=%s",
                inst_id, str(close_err),
                exc_info=True
            )

        # If emergency close also failed, send critical alerts
        if not emergency_close_success:
            notify_error(
                f"🚨 CRITICAL ALERT 🚨\n"
                f"Position opened WITHOUT PROTECTION\n"
                f"Symbol: {inst_id}\n"
                f"Side: {pos_side}\n"
                f"Size: {order_sz}\n"
                f"Entry: {filled_price}\n"
                f"Intended SL: {sl}\n"
                f"SL Failure: {sl_failure_reason}\n"
                f"Backup SL: {'attempted' if backup_sl_attempted else 'disabled'}\n"
                f"Emergency Close: FAILED\n"
                f"⚠️ IMMEDIATE MANUAL INTERVENTION REQUIRED\n"
                f"⚠️ Position is being monitored by emergency handler"
            )

            # DO NOT register to TradeManager since position has no protection
            # Emergency handler will monitor this position separately
            state.mark_traded(key)
            state.clear_zone(key)
            return {
                "ok": False,
                "error": "stop_loss_failed_no_protection",
                "instId": inst_id,
                "side": side,
                "posSide": pos_side,
                "entry": filled_price,
                "intended_sl": sl,
                "size": order_sz,
                "warning": "Position has NO STOP LOSS protection - emergency handler monitoring",
            }

    # 6.5 Lighter: place TP orders directly (no TradeManager support)
    tp_orders: list[dict[str, str]] = []
    if SETTINGS.exchange == "lighter" and SETTINGS.tp_enabled:
        r_value_final = abs(filled_price - float(sl))
        if r_value_final > 0:
            tp_orders = await _build_tp_targets(
                inst_id=inst_id,
                side=side,
                entry_price=filled_price,
                sl=float(sl),
                total_sz=Decimal(str(total_filled_sz)) if total_filled_sz > 0 else Decimal(str(order_sz)),
                tick_size=tick_size,
            )
            for target in tp_orders:
                tp_resp = await exchange.place_algo_order(
                    inst_id=inst_id,
                    td_mode=SETTINGS.okx_td_mode,
                    side="sell" if side == "buy" else "buy",
                    pos_side=pos_side,
                    ord_type="conditional",
                    sz=target["size"],
                    tp_trigger_px=target["price"],
                    tp_ord_px="-1",
                )
                if str(tp_resp.get("code", "")) not in {"0", "success"}:
                    notify_error(
                        f"lighter tp failed instId={inst_id} tag={target['tag']} price={target['price']} sz={target['size']} resp={tp_resp}"
                    )
            if tp_orders:
                notify_info(
                    f"lighter tp orders placed instId={inst_id} count={len(tp_orders)}"
                )

    # 7. 标记交易和清除zone
    state.mark_traded(key)
    state.clear_zone(key)
    _log_decision(inst_id, tf, action="order_placed", side=side, posSide=pos_side, zone=zone_state.zone)

    # 8. 重新计算止盈价（基于实际成交价）
    r_value_final = abs(filled_price - float(sl))
    if SETTINGS.tp_enabled:
        tp = take_profit_price(side=side, entry_price=filled_price, stop_loss=float(sl), rr=SETTINGS.tp4_r)

    # 9. 注册TradePlan给TradeManager (only if SL is successfully placed)
    if manager is not None:
        # Use actual filled size for trade plan
        plan_sz = str(total_filled_sz) if total_filled_sz > 0 else order_sz
        await manager.upsert_plan(
            key,
            TradePlan(
                inst_id=inst_id,
                tf=tf,
                side=side,
                pos_side=pos_side,
                td_mode=SETTINGS.okx_td_mode,
                entry_price=filled_price,
                stop_loss=float(sl),
                total_sz=Decimal(plan_sz),
                r_value=r_value_final,
                cl_ord_id=cl_ord_id[:32],
            ),
        )

    return {
        "ok": True,
        "type": "DIV",
        "zone": zone_state.zone,
        "side": side,
        "posSide": pos_side,
        "entry": filled_price,
        "sl": sl,
        "tp3": tp,
        "order_sz": order_sz,
        "r_value": r_value_final,
        "order": resp,
    }


def _handle_telegram_div(inst_id: str, tf: str) -> None:
    import asyncio
    import datetime as dt

    async def _run() -> None:
        payload = TvPayload(
            secret=SETTINGS.tv_webhook_secret,
            type="DIV",
            instId=inst_id,
            tf=tf,
            t=dt.datetime.utcnow().isoformat() + "Z",
            close=None,
            zone=None,
        )
        result = await _process_payload(payload, allow_no_zone=True)
        if not result.get("ok"):
            return
        if not result.get("paper"):
            return
        inst_id_norm = result.get("instId") or inst_id
        entry = result.get("entry")
        sl = result.get("sl")
        side = result.get("side")
        if entry is None or sl is None or side is None:
            return
        candles = fetch_candles(SETTINGS.okx_base_url, inst_id_norm, tf, limit=200)
        closes = [c.c for c in candles]
        tps = []
        for rr in (SETTINGS.tp1_r, SETTINGS.tp2_r, SETTINGS.tp3_r, SETTINGS.tp4_r):
            tp_val = take_profit_price(side=side, entry_price=float(entry), stop_loss=float(sl), rr=rr)
            if tp_val is not None:
                tps.append(tp_val)
        image_path = plot_kline(
            inst_id=inst_id_norm,
            tf=tf,
            closes=closes,
            entry=float(entry),
            sl=float(sl),
            tps=tps,
            side=side,
        )
        caption = (
            f"{inst_id_norm} {tf} {side}\n"
            f"entry={entry} sl={sl} sz={result.get('order_sz')} r={result.get('r')}"
        )
        if image_path:
            notify_photo(image_path, caption=caption)
        else:
            notify_info(caption)

    asyncio.run(_run())
