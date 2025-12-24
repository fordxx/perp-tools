from __future__ import annotations

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
from app.rsi_ml import compute_rsi_thresholds, compute_rsi_thresholds_percentile
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


class TvPayload(BaseModel):
    secret: str
    type: str = Field(..., description="ZONE | DIV")
    instId: str
    tf: str = "1m"
    t: str | None = None
    close: str | None = None
    zone: str | None = None


def _key(inst_id: str, tf: str) -> str:
    return f"{inst_id}:{tf}"


def _log_payload(payload: TvPayload) -> None:
    logger.info(
        "tv_webhook received type=%s instId=%s tf=%s zone=%s t=%s close=%s",
        payload.type,
        payload.instId,
        payload.tf,
        payload.zone,
        payload.t,
        payload.close,
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


@app.on_event("shutdown")
async def _shutdown() -> None:
    if ws_manager is not None:
        await ws_manager.stop()
    if candle_ws_manager is not None:
        await candle_ws_manager.stop()
    if tg_control is not None:
        tg_control.stop()
    if SETTINGS.exchange == "extended":
        close_fn = getattr(exchange, "close", None)
        if callable(close_fn):
            close_fn()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/tradingview")
async def webhook_tradingview(req: Request) -> dict:
    try:
        data = await req.json()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from e

    payload = TvPayload.model_validate(data)
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

    dedupe_key = f"{payload.type}:{inst_id}:{tf}:{payload.t or ''}"
    if state.seen(dedupe_key, ttl_seconds=60 * 30):
        _log_decision(inst_id, tf, action="skip", reason="deduped", dedupe_key=dedupe_key)
        return {"ok": True, "deduped": True}

    close_f: float | None = None
    if payload.close is not None and payload.close != "":
        try:
            close_f = float(payload.close)
        except ValueError:
            close_f = None

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
    if zone_state is None and not (allow_no_zone or SETTINGS.rsi_allow_no_zone):
        _log_decision(inst_id, tf, action="skip", reason="no_zone_state")
        return {"ok": True, "skipped": "no_zone_state"}
    if zone_state is not None and zone_state.zone not in {"OVERSOLD", "OVERBOUGHT"}:
        _log_decision(inst_id, tf, action="skip", reason="zone_expired_or_neutral", zone=zone_state.zone)
        return {"ok": True, "skipped": "zone_expired_or_neutral", "zone": zone_state.zone}
    if not state.can_trade(key, SETTINGS.cooldown_seconds):
        _log_decision(inst_id, tf, action="skip", reason="cooldown")
        return {"ok": True, "skipped": "cooldown"}

    side = "buy"
    pos_side = "long"
    if zone_state is not None:
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

    rsi_candles = candles
    if not SETTINGS.rsi_use_live_candle and len(rsi_candles) > 1:
        rsi_candles = rsi_candles[:-1]
    rsi_result = None
    if SETTINGS.rsi_filter_enabled or SETTINGS.rsi_debug:
        closes = [c.c for c in rsi_candles]
        if SETTINGS.rsi_threshold_mode == "percentile":
            rsi_result = compute_rsi_thresholds_percentile(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=SETTINGS.rsi_max_data,
            )
        else:
            rsi_result = compute_rsi_thresholds(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=SETTINGS.rsi_max_data,
                max_iter=SETTINGS.rsi_max_iter,
            )
        if rsi_result is None:
            _log_decision(inst_id, tf, action="skip", reason="no_rsi")
            return {"ok": True, "skipped": "no_rsi"}
        if SETTINGS.rsi_debug:
            last_ts = rsi_candles[-1].ts_ms if rsi_candles else None
            last_close = rsi_candles[-1].c if rsi_candles else None
            rsi_samples = max(0, len(rsi_candles) - SETTINGS.rsi_length)
            used_samples = min(SETTINGS.rsi_max_data, rsi_samples)
            alt = compute_rsi_thresholds_percentile(
                closes,
                rsi_length=SETTINGS.rsi_length,
                smooth=SETTINGS.rsi_smooth,
                smooth_period=SETTINGS.rsi_smooth_period,
                ma_type=SETTINGS.rsi_ma_type,
                max_data=SETTINGS.rsi_max_data,
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
                last_close=last_close,
                last_ts=last_ts,
                live=SETTINGS.rsi_use_live_candle,
            )
    if SETTINGS.rsi_filter_enabled:
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
        order_sz = SETTINGS.order_sz
        if SETTINGS.risk_per_trade_usdt and SETTINGS.risk_per_trade_usdt > 0 and r_value > 0:
            inst_info = exchange.get_instrument_info(inst_id=inst_id)
            ct_val = 1.0
            if inst_info and inst_info.get("ctVal"):
                ct_val = float(inst_info.get("ctVal"))
            calculated_sz_coins = SETTINGS.risk_per_trade_usdt / r_value
            calculated_sz_contracts = calculated_sz_coins / ct_val
            order_sz = str(max(1, int(calculated_sz_contracts)))
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
    if SETTINGS.risk_per_trade_usdt and SETTINGS.risk_per_trade_usdt > 0:
        import math

        inst_info = exchange.get_instrument_info(inst_id=inst_id)
        ct_val = 1.0
        if inst_info and inst_info.get("ctVal"):
            ct_val = float(inst_info.get("ctVal"))
            logger.info("tv_webhook contract_info inst_id=%s ct_val=%s", inst_id, ct_val)

        calculated_sz_coins = SETTINGS.risk_per_trade_usdt / r_value
        calculated_sz_contracts = calculated_sz_coins / ct_val
        order_sz_contracts = max(1, int(math.floor(calculated_sz_contracts)))
        order_sz = str(order_sz_contracts)
        actual_coins = order_sz_contracts * ct_val

        logger.info(
            "tv_webhook risk_based_sizing risk_usdt=%s r_value=%.4f coins=%.4f ct_val=%s contracts=%s actual_coins=%.4f",
            SETTINGS.risk_per_trade_usdt,
            r_value,
            calculated_sz_coins,
            ct_val,
            order_sz,
            actual_coins,
        )
    else:
        order_sz = SETTINGS.order_sz
        logger.info("tv_webhook fixed_sizing sz=%s", order_sz)

    if SETTINGS.exchange == "extended":
        sl_px = f"{sl:.8f}".rstrip("0").rstrip(".") if sl is not None else None

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
        else:
            notify_info(
                f"extended entry accepted instId={inst_id} side={side} sz={order_sz}"
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
            inst_info = exchange.get_instrument_info(inst_id=inst_id)
            step = Decimal(str(inst_info.get("lotSz"))) if inst_info and inst_info.get("lotSz") else Decimal("1")
            total_sz_dec = Decimal(str(order_sz))

            def _floor_to_step(value: Decimal, step_value: Decimal) -> Decimal:
                if step_value <= 0:
                    return value
                return (value / step_value).to_integral_value(rounding=ROUND_DOWN) * step_value

            tp1_sz = _floor_to_step(total_sz_dec * Decimal(str(SETTINGS.tp1_pct)), step)
            tp2_sz = _floor_to_step(total_sz_dec * Decimal(str(SETTINGS.tp2_pct)), step)
            tp3_sz = _floor_to_step(total_sz_dec * Decimal(str(SETTINGS.tp3_pct)), step)
            remaining = total_sz_dec - tp1_sz - tp2_sz - tp3_sz
            if remaining < 0:
                remaining = Decimal("0")

            tp_sizes = [
                (SETTINGS.tp1_r, tp1_sz, "tp1"),
                (SETTINGS.tp2_r, tp2_sz, "tp2"),
                (SETTINGS.tp3_r, tp3_sz, "tp3"),
                (SETTINGS.tp4_r, remaining, "tp4"),
            ]

            for rr, sz_dec, tag in tp_sizes:
                if sz_dec <= 0:
                    continue
                tp_price = take_profit_price(
                    side=side,
                    entry_price=float(entry_price),
                    stop_loss=float(sl),
                    rr=rr,
                )
                if tp_price is None:
                    continue
                tp_px = f"{tp_price:.8f}".rstrip("0").rstrip(".")
                tp_resp = exchange.place_order(
                    inst_id=inst_id,
                    td_mode=SETTINGS.okx_td_mode,
                    side="sell" if side == "buy" else "buy",
                    pos_side=pos_side,
                    ord_type="limit",
                    sz=str(sz_dec),
                    px=tp_px,
                    cl_ord_id=f"{cl_ord_id}_{tag}"[:32],
                    sl_trigger_px=None,
                    tp_trigger_px=None,
                    reduce_only=True,
                )
                if str(tp_resp.get("code", "")) not in {"0", "success"}:
                    notify_error(
                        f"extended tp failed instId={inst_id} tag={tag} price={tp_px} sz={sz_dec} resp={tp_resp}"
                    )
                else:
                    data = tp_resp.get("data") or []
                    if data:
                        ord_id = data[0].get("ordId") or ""
                        if ord_id:
                            fill_tracker.register_order_label(
                                key=str(ord_id),
                                label=tag,
                            )
                tp_orders.append({"tag": tag, "price": tp_px, "size": str(sz_dec), "resp": str(tp_resp)})
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

    # 4. 等待成交并获取实际成交价
    await asyncio.sleep(0.5)

    filled_price = None
    ord_info = exchange.get_order(inst_id=inst_id, cl_ord_id=cl_ord_id)
    if ord_info and ord_info.get("avgPx"):
        filled_price = float(ord_info.get("avgPx"))
        logger.info("tv_webhook order_filled cl_ord_id=%s filled_price=%.4f", cl_ord_id, filled_price)
        notify_info(
            f"okx entry filled instId={inst_id} side={side} px={filled_price:.6f} sz={order_sz}"
        )
    else:
        filled_price = float(entry_price)
        logger.warning("tv_webhook no_filled_price using_estimated price=%.4f", filled_price)

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

    try:
        sl_resp = exchange.place_algo_order(
            inst_id=inst_id,
            td_mode=SETTINGS.okx_td_mode,
            side=sl_side,
            pos_side=pos_side,
            ord_type="conditional",
            sz=order_sz,
            sl_trigger_px=f"{sl:.8f}".rstrip("0").rstrip("."),
            sl_ord_px="-1",
        )
        logger.info("tv_webhook sl_order_placed sl_price=%.4f resp=%s", sl, sl_resp)
        if str(sl_resp.get("code", "")) not in {"0", "success"}:
            notify_error(
                f"okx sl failed instId={inst_id} side={sl_side} sz={order_sz} resp={sl_resp}"
            )
        else:
            data = sl_resp.get("data") or []
            if data:
                algo_id = data[0].get("algoId") or ""
                if algo_id:
                    fill_tracker.register_algo_label(algo_id=algo_id, label="sl")
    except Exception as e:
        logger.error("tv_webhook sl_order_failed error=%s", str(e))
        notify_error(f"okx sl exception instId={inst_id} err={e}")

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
