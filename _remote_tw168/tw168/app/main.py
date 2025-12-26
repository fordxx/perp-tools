from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal, ROUND_DOWN
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import SETTINGS
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

def _parse_symbol_tfs(raw: str) -> dict[str, list[str]]:
    import re

    out: dict[str, list[str]] = {}
    for line in raw.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" in line:
            inst_id, tf_raw = line.split(":", 1)
        else:
            parts = line.split()
            if not parts:
                continue
            inst_id = parts[0]
            tf_raw = " ".join(parts[1:])
        inst_id = inst_id.strip()
        tfs = [t.strip().lower() for t in re.split(r"[,\s|]+", tf_raw) if t.strip()]
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


if SETTINGS.candle_ws_enabled:
    okx_inst_ids: list[str] = []
    extended_inst_ids: list[str] = []
    if SETTINGS.candle_ws_symbol_tfs_file:
        try:
            with open(SETTINGS.candle_ws_symbol_tfs_file, "r", encoding="ascii") as f:
                candle_ws_symbol_tfs = _parse_symbol_tfs(f.read())
        except Exception:
            candle_ws_symbol_tfs = {}
    elif SETTINGS.candle_ws_symbol_tfs:
        candle_ws_symbol_tfs = _parse_symbol_tfs(SETTINGS.candle_ws_symbol_tfs)
    if not candle_ws_symbol_tfs:
        if "*" in SETTINGS.symbol_allowlist:
            logger.warning("CANDLE_WS enabled with SYMBOL_ALLOWLIST='*'; skipping WS subscriptions")
        else:
            okx_inst_ids = list(SETTINGS.symbol_allowlist)
            extended_inst_ids = list(SETTINGS.symbol_allowlist)

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
        tfs=[tf.lower() for tf in SETTINGS.candle_ws_tfs],
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


def _calculate_order_size(*, inst_id: str, r_value: float) -> tuple[str, dict[str, object]]:
    order_sz = SETTINGS.order_sz
    meta: dict[str, object] = {}
    if not (SETTINGS.risk_per_trade_usdt and SETTINGS.risk_per_trade_usdt > 0 and r_value > 0):
        return order_sz, meta

    inst_info = exchange.get_instrument_info(inst_id=inst_id)
    ct_val = float(inst_info.get("ctVal")) if inst_info and inst_info.get("ctVal") else 1.0
    lot_step = Decimal(str(inst_info.get("lotStep"))) if inst_info and inst_info.get("lotStep") else None
    min_order = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else None

    risk_usdt = Decimal(str(SETTINGS.risk_per_trade_usdt))
    r_value_dec = Decimal(str(r_value))
    ct_val_dec = Decimal(str(ct_val))
    calculated_sz_coins = risk_usdt / r_value_dec
    calculated_sz_contracts = calculated_sz_coins / ct_val_dec
    qty = _normalize_qty(calculated_sz_contracts, step=lot_step, min_sz=min_order)
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


def _place_extended_tp_orders(
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
    tp_targets = _build_tp_targets(
        inst_id=inst_id,
        side=side,
        entry_price=entry_price,
        sl=sl,
        total_sz=total_sz,
        tick_size=tick_size,
    )
    tp_orders: list[dict[str, str]] = []
    for target in tp_targets:
        tp_resp = exchange.place_order(
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


def _place_extended_sl_order(
    *,
    inst_id: str,
    pos_side: str,
    sl: float,
    total_sz: Decimal,
    tick_size: str | None,
    cl_ord_id: str,
) -> dict[str, str] | None:
    sl_px = _round_price_to_tick(sl, tick_size)
    side = "sell" if pos_side == "long" else "buy"
    resp = exchange.place_order(
        inst_id=inst_id,
        td_mode=SETTINGS.okx_td_mode,
        side=side,
        pos_side=pos_side,
        ord_type="limit",
        sz=str(total_sz),
        px=sl_px,
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


def _build_tp_targets(
    *,
    inst_id: str,
    side: str,
    entry_price: float,
    sl: float,
    total_sz: Decimal,
    tick_size: str | None,
) -> list[dict[str, str]]:
    inst_info = exchange.get_instrument_info(inst_id=inst_id)
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
        if not SETTINGS.trading_enabled or not SETTINGS.extended_refresh_enabled:
            continue
        now = time.time()
        for inst_id in SETTINGS.symbol_allowlist:
            if inst_id == "*":
                continue
            for pos_side in ("long", "short"):
                key = f"{inst_id}:{pos_side}"
                last_ts = _last_refresh_by_key.get(key, 0.0)
                if (now - last_ts) < SETTINGS.extended_refresh_seconds:
                    continue
                pos = exchange.get_position(inst_id=inst_id, pos_side=pos_side)
                if not pos:
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
                inst_info = exchange.get_instrument_info(inst_id=inst_id)
                if inst_info:
                    tick_size = inst_info.get("tickSz")

                orders = exchange.get_open_orders(inst_id=inst_id)
                opposite_side = "SELL" if pos_side == "long" else "BUY"
                sl_order_exists = False
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

                if SETTINGS.extended_refresh_sl_enabled:
                    if not sl_price:
                        logger.warning(
                            "extended sl missing instId=%s posSide=%s size=%s", inst_id, pos_side, size
                        )
                        notify_info(
                            f"extended sl missing instId={inst_id} posSide={pos_side} size={size}"
                        )
                    elif not sl_order_exists:
                        last_price = exchange.get_last_price(inst_id=inst_id)
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
                        sl_order = _place_extended_sl_order(
                            inst_id=inst_id,
                            pos_side=pos_side,
                            sl=sl_to_place,
                            total_sz=size,
                            tick_size=tick_size,
                            cl_ord_id=cl_ord_id,
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
                    tp_targets = _build_tp_targets(
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
                        tp_resp = exchange.place_order(
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


@app.on_event("startup")
async def _startup() -> None:
    if SETTINGS.trading_enabled and manager is not None:
        manager.start()
    if SETTINGS.trading_enabled and ws_manager is not None:
        ws_manager.start(
            enable_okx=SETTINGS.exchange == "okx",
            enable_extended=SETTINGS.exchange == "extended",
        )
    if SETTINGS.candle_ws_enabled and candle_ws_manager is not None:
        candle_ws_manager.start()
        if candle_ws_symbol_tfs:
            for inst_id, tfs in candle_ws_symbol_tfs.items():
                for tf in tfs:
                    await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf=tf)
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
    except Exception as e:  # noqa: BLE001
        snippet = raw_body[:500].decode("utf-8", errors="replace")
        logger.warning("tv_webhook invalid_json err=%s body=%s", e, snippet)
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

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
    if "*" not in SETTINGS.symbol_allowlist and inst_id not in SETTINGS.symbol_allowlist:
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

    if payload.type.upper() != "DIV":
        raise HTTPException(status_code=400, detail="Unknown type")

    zone_state = state.get_zone(key)
    if payload_side is None:
        if zone_state is None and not (allow_no_zone or SETTINGS.rsi_allow_no_zone):
            _log_decision(inst_id, tf, action="skip", reason="no_zone_state")
            return {"ok": True, "skipped": "no_zone_state"}
        if zone_state is not None and zone_state.zone not in {"OVERSOLD", "OVERBOUGHT"}:
            _log_decision(inst_id, tf, action="skip", reason="zone_expired_or_neutral", zone=zone_state.zone)
            return {"ok": True, "skipped": "zone_expired_or_neutral", "zone": zone_state.zone}
        if not state.can_trade(key, SETTINGS.cooldown_seconds):
            _log_decision(inst_id, tf, action="skip", reason="cooldown")
            return {"ok": True, "skipped": "cooldown"}

    side = payload_side or "buy"
    pos_side = "long" if side == "buy" else "short"
    if payload_side is not None:
        zone_state = SimpleNamespace(
            zone="OVERSOLD" if side == "buy" else "OVERBOUGHT",
            close=close_f,
        )
    elif zone_state is not None:
        if zone_state.zone == "OVERSOLD":
            side = "buy"
            pos_side = "long"
        else:
            side = "sell"
            pos_side = "short"

    entry_price = close_f or (zone_state.close if zone_state is not None else None)
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
    if entry_price is None and last_candle_close is not None:
        entry_price = last_candle_close
    if entry_price is None:
        _log_decision(inst_id, tf, action="skip", reason="no_entry_price")
        return {"ok": True, "skipped": "no_entry_price"}

    if not SETTINGS.trading_enabled:
        try:
            last_px = exchange.get_last_price(inst_id=inst_id)
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
            lookback_bars=SETTINGS.stop_lookback_bars,
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
    if side == "buy" and float(sl) >= float(entry_price):
        _log_decision(
            inst_id,
            tf,
            action="skip",
            reason="invalid_stoploss_sl_gte_entry",
            sl=sl,
            entry=float(entry_price),
        )
        return {
            "ok": True,
            "skipped": "invalid_stoploss",
            "reason": "sl_gte_entry",
            "sl": sl,
            "entry": float(entry_price),
        }
    if side == "sell" and float(sl) <= float(entry_price):
        _log_decision(
            inst_id,
            tf,
            action="skip",
            reason="invalid_stoploss_sl_lte_entry",
            sl=sl,
            entry=float(entry_price),
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
        order_sz, size_meta = _calculate_order_size(inst_id=inst_id, r_value=r_value)
        if size_meta:
            logger.info(
                "tv_webhook risk_based_sizing risk_usdt=%s r_value=%.4f coins=%.4f ct_val=%s contracts=%s actual_coins=%.4f",
                SETTINGS.risk_per_trade_usdt,
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
    order_sz, size_meta = _calculate_order_size(inst_id=inst_id, r_value=r_value)
    if size_meta:
        logger.info(
            "tv_webhook risk_based_sizing risk_usdt=%s r_value=%.4f coins=%.4f ct_val=%s contracts=%s actual_coins=%.4f",
            SETTINGS.risk_per_trade_usdt,
            r_value,
            size_meta.get("calculated_sz_coins"),
            size_meta.get("ct_val"),
            order_sz,
            size_meta.get("actual_coins"),
        )
    else:
        logger.info("tv_webhook fixed_sizing sz=%s", order_sz)

    if SETTINGS.exchange == "extended":
        # Get instrument info for price precision
        inst_info = exchange.get_instrument_info(inst_id=inst_id)
        tick_size = inst_info.get("tickSz") if inst_info else None
        sl_px = _round_price_to_tick(sl, tick_size) if sl is not None else None

        ts = int(time.time())
        rnd = random.randint(100, 999)
        cl_ord_id = f"tv{ts}{rnd}{side[:1]}"[:32]

        try:
            resp = exchange.place_order(
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
        except Exception as exc:  # noqa: BLE001
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
                    pos = exchange.get_position(inst_id=inst_id, pos_side=pos_side)
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
            tp_orders = _place_extended_tp_orders(
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

    # 3. 下纯市价单（不附加止损）
    ts = int(time.time())
    rnd = random.randint(100, 999)
    cl_ord_id = f"tv{ts}{rnd}{side[:1]}"[:32]

    resp = exchange.place_order(
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

    # 4. 等待成交并获取实际成交价（带重试机制）
    filled_price = None
    max_retries = 5
    for retry in range(max_retries):
        await asyncio.sleep(0.3 * (retry + 1))  # Progressive backoff: 0.3s, 0.6s, 0.9s, 1.2s, 1.5s
        try:
            ord_info = exchange.get_order(inst_id=inst_id, cl_ord_id=cl_ord_id)
            if ord_info and ord_info.get("avgPx"):
                filled_price = float(ord_info.get("avgPx"))
                logger.info("tv_webhook order_filled cl_ord_id=%s filled_price=%.4f retry=%d",
                           cl_ord_id, filled_price, retry)
                notify_info(
                    f"okx entry filled instId={inst_id} side={side} px={filled_price:.6f} sz={order_sz}"
                )
                break
            # Check order state
            state_val = ord_info.get("state", "").lower() if ord_info else ""
            if state_val in {"filled", "partially_filled"}:
                # Order is filled but avgPx might be processing
                if retry < max_retries - 1:
                    continue
        except Exception as e:
            logger.warning("tv_webhook order_query_failed retry=%d err=%s", retry, str(e))
            if retry < max_retries - 1:
                continue

    if filled_price is None:
        filled_price = float(entry_price)
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
                lookback_bars=SETTINGS.stop_lookback_bars,
                atr_len=SETTINGS.atr_len,
                atr_buffer_mult=SETTINGS.atr_buffer_mult,
                min_buffer_bps=SETTINGS.min_buffer_bps,
            )

        if sl_actual:
            sl = sl_actual
            r_value_actual = abs(filled_price - sl)
            logger.info("tv_webhook recalculated_sl entry=%.4f sl=%.4f r=%.4f", filled_price, sl, r_value_actual)
        else:
            logger.warning("tv_webhook failed_to_recalculate_sl using_original sl=%.4f", sl)

    fill_tracker.register_entry(
        inst_id=inst_id,
        side=side,
        entry_price=float(filled_price),
        stop_loss=float(sl),
    )

    # 6. 下单独的止损单
    sl_side = "sell" if side == "buy" else "buy"
    sl_order_success = False
    sl_failure_reason = ""

    # Get instrument info for price precision
    inst_info = exchange.get_instrument_info(inst_id=inst_id)
    tick_size = inst_info.get("tickSz") if inst_info else None

    try:
        sl_resp = exchange.place_algo_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side=sl_side,
            pos_side=pos_side,
            ord_type="conditional",
            sz=order_sz,
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
    if not sl_order_success and SETTINGS.backup_sl_enabled:
        logger.info("tv_webhook trying_backup_sl instId=%s method=limit_order", inst_id)
        try:
            backup_sl_resp = exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=sl_side,
                pos_side=pos_side,
                ord_type="limit",
                sz=order_sz,
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
            logger.error("tv_webhook backup_sl_failed instId=%s err=%s", inst_id, str(backup_err))

    # Emergency close if stop-loss order failed
    if not sl_order_success:
        logger.error("tv_webhook emergency_close instId=%s posSide=%s sz=%s reason=sl_order_failed",
                     inst_id, pos_side, order_sz)

        # Check if we should alert based on failure rate
        if metrics.should_alert(threshold=0.05, min_attempts=10):
            notify_error(
                f"⚠️ HIGH SL FAILURE RATE: {metrics.sl_failure_rate:.1%} "
                f"({metrics.sl_orders_failed}/{metrics.sl_orders_attempted} attempts)"
            )

        try:
            emergency_resp = exchange.place_order(
                inst_id=inst_id,
                td_mode=SETTINGS.okx_td_mode,
                side=sl_side,
                pos_side=pos_side,
                ord_type="market",
                sz=order_sz,
                px=None,
                cl_ord_id=f"{cl_ord_id}_emergency"[:32],
                sl_trigger_px=None,
                tp_trigger_px=None,
                reduce_only=True,
            )
            metrics.record_emergency_close(success=True, inst_id=inst_id)
            notify_error(
                f"okx emergency close executed instId={inst_id} due to SL failure resp={emergency_resp}"
            )
            # Skip marking traded and registering plan since position was closed
            return {
                "ok": False,
                "error": "stop_loss_failed_position_closed",
                "instId": inst_id,
                "emergency_close": emergency_resp,
            }
        except Exception as close_err:
            metrics.record_emergency_close(success=False, inst_id=inst_id)
            logger.critical("tv_webhook emergency_close_failed instId=%s err=%s", inst_id, str(close_err))
            notify_error(
                f"CRITICAL: Emergency close failed for {inst_id}! Manual intervention required. Error: {close_err}"
            )
            # Continue anyway to at least mark the trade
            pass

    # 7. 标记交易和清除zone
    state.mark_traded(key)
    state.clear_zone(key)
    _log_decision(inst_id, tf, action="order_placed", side=side, posSide=pos_side, zone=zone_state.zone)

    # 8. 重新计算止盈价（基于实际成交价）
    r_value_final = abs(filled_price - float(sl))
    if SETTINGS.tp_enabled:
        tp = take_profit_price(side=side, entry_price=filled_price, stop_loss=float(sl), rr=SETTINGS.tp4_r)

    # 9. 注册TradePlan给TradeManager
    if manager is not None:
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
                total_sz=Decimal(str(order_sz)),
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
