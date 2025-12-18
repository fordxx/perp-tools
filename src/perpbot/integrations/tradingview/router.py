from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .risk import fetch_okx_candles, stop_loss_price, stop_loss_price_lookback, take_profit_price
from .settings import TradingViewSettings
from .state import InMemoryState
from .execution import execute_market, resolve_size_for_exchange
from .executor import execute_market_with_stop_loss
from .markets import FETCHERS, MarketCache

logger = logging.getLogger(__name__)


class TvPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    secret: str
    type: str = Field(..., description="ZONE | DIV")
    instId: str
    exchange: Optional[str] = Field(default=None, description="Target exchange name (optional)")
    tf: str = "1m"
    t: Optional[str] = None
    close: Optional[str] = None
    zone: Optional[str] = None


def _key(inst_id: str, tf: str) -> str:
    return f"{inst_id}:{tf}"


def _inst_to_okx_inst_id(value: str) -> str:
    sym = _inst_to_symbol(value)
    if "/" in sym:
        base, quote = sym.split("/", 1)
        return f"{base.upper()}-{quote.upper()}-SWAP"
    # Fallback: treat as already OKX instId or unknown.
    return sym.upper()


def _inst_to_symbol_guess(value: str) -> str:
    v = value.strip().upper()
    # TradingView common perp suffixes: SOLUSDT.P, BTCUSDT.PERP, etc.
    for suffix in (".P", ".PERP", "PERP"):
        if v.endswith(suffix):
            v = v[: -len(suffix)]
            break
    if "/" in v:
        return v
    if "-" in v:
        parts = v.split("-")
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    # Try to split by known quote suffixes.
    for quote in ("USDT", "USDC", "USD", "BTC", "ETH"):
        if v.endswith(quote) and len(v) > len(quote):
            base = v[: -len(quote)]
            return f"{base}/{quote}"
    return v


def _inst_to_symbol(value: str) -> str:
    v = value.strip().upper()
    if "/" in v:
        return v
    parts = v.split("-")
    if len(parts) >= 3 and parts[-1] == "SWAP":
        return f"{parts[0]}/{parts[1]}"
    return _inst_to_symbol_guess(v)


def _allowed(settings: TradingViewSettings, inst_id: str) -> bool:
    if settings.allow_all_symbols:
        return True
    candidate_raw = inst_id.strip().upper()
    candidate_symbol = _inst_to_symbol(inst_id).upper()
    candidate_inst = _inst_to_okx_inst_id(inst_id).upper()
    allow = {a.strip().upper() for a in settings.symbol_allowlist}
    return (candidate_raw in allow) or (candidate_symbol in allow) or (candidate_inst in allow)


def create_tradingview_router(service: Any) -> APIRouter:
    settings = TradingViewSettings.from_env()
    state = InMemoryState()
    markets_cache = MarketCache(ttl_sec=int(os.getenv("PERPBOT_TV_MARKETS_CACHE_SEC", "600")))
    router = APIRouter()

    @router.get("/api/tv168/options")
    def tv168_options() -> dict[str, Any]:
        exchanges_available = sorted({getattr(ex, "name", "") for ex in getattr(service, "exchanges", []) if getattr(ex, "name", "")})
        return {
            "enabled": settings.enabled,
            "default_exchange": settings.default_exchange,
            "exchange_allowlist": sorted(settings.exchange_allowlist) if settings.exchange_allowlist else [],
            "exchange_aliases": dict(settings.exchange_aliases),
            "exchanges_available": exchanges_available,
            "exchanges_supported_markets": sorted(FETCHERS.keys()),
            "symbols_allowlist": sorted({s.strip() for s in settings.symbol_allowlist if s.strip()}),
            "symbol_aliases": dict(settings.symbol_aliases),
            "allow_all_symbols": bool(settings.allow_all_symbols),
        }

    @router.get("/api/tv168/markets")
    def tv168_markets(exchange: str, quote: str | None = None) -> dict[str, Any]:
        ex = exchange.strip().lower()
        ex = settings.exchange_aliases.get(ex, ex)
        if settings.exchange_allowlist and ex not in settings.exchange_allowlist:
            raise HTTPException(status_code=403, detail="Exchange not allowed")

        cached = markets_cache.get(ex)
        if cached is None:
            fetcher = FETCHERS.get(ex)
            if fetcher is None:
                return {"ok": False, "exchange": ex, "markets": [], "reason": "unsupported_exchange"}
            try:
                cached = fetcher()
                markets_cache.set(ex, cached)
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "exchange": ex, "markets": [], "reason": str(exc)}

        markets = [{"symbol": m.symbol, "raw": m.raw} for m in cached]

        effective_quote = (quote or "").strip().upper()
        if not effective_quote:
            effective_quote = "USD" if ex == "hyperliquid" else "USDT"
        if effective_quote not in {"ALL", "*"}:
            markets = [m for m in markets if m["symbol"].upper().endswith(f"/{effective_quote}")]

        if not settings.allow_all_symbols:
            allow = {a.strip().upper() for a in settings.symbol_allowlist if a.strip()}
            if allow:
                filtered = []
                for m in markets:
                    if (
                        m["symbol"].upper() in allow
                        or m["raw"].upper() in allow
                        or m["raw"].upper() in settings.symbol_aliases
                    ):
                        filtered.append(m)
                markets = filtered

        markets.sort(key=lambda x: x["symbol"])
        return {"ok": True, "exchange": ex, "quote": effective_quote, "markets": markets}

    @router.get("/health/tradingview")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": settings.enabled,
            "default_exchange": settings.default_exchange,
            "exchange_allowlist": sorted(settings.exchange_allowlist) if settings.exchange_allowlist else [],
            "trading_enabled": bool(service.state.trading_enabled),
        }

    @router.post("/webhook/tradingview")
    async def webhook_tradingview(req: Request) -> dict[str, Any]:
        if not settings.enabled:
            raise HTTPException(status_code=503, detail="TradingView webhook disabled")

        try:
            data = await req.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

        payload = TvPayload.model_validate(data)

        if payload.secret != settings.secret:
            raise HTTPException(status_code=401, detail="Bad secret")
        inst_raw = payload.instId.strip()
        inst_aliased = settings.symbol_aliases.get(inst_raw.upper(), inst_raw)
        if not (_allowed(settings, inst_raw) or _allowed(settings, inst_aliased)):
            raise HTTPException(status_code=403, detail="Symbol not allowed")

        exchange_raw = (payload.exchange or settings.default_exchange).strip().lower()
        exchange_name = settings.exchange_aliases.get(exchange_raw, exchange_raw)
        if settings.exchange_allowlist and exchange_name not in settings.exchange_allowlist:
            raise HTTPException(status_code=403, detail="Exchange not allowed")

        inst_id = _inst_to_okx_inst_id(inst_aliased)
        symbol = _inst_to_symbol(inst_aliased)
        tf = payload.tf
        key = _key(inst_id, tf)

        dedupe_key = f"{payload.type}:{inst_id}:{tf}:{payload.t or ''}"
        if state.seen(dedupe_key, ttl_seconds=60 * 30):
            return {"ok": True, "deduped": True}

        close_f: float | None = None
        if payload.close is not None and payload.close != "":
            try:
                close_f = float(payload.close)
            except ValueError:
                close_f = None

        msg_type = payload.type.upper()
        if msg_type == "ZONE":
            if payload.zone is None:
                raise HTTPException(status_code=400, detail="Missing zone")
            zone = payload.zone.upper()
            if zone not in {"OVERSOLD", "OVERBOUGHT", "NEUTRAL"}:
                raise HTTPException(status_code=400, detail="Invalid zone")
            state.set_zone(key, zone=zone, close=close_f)
            return {"ok": True, "type": "ZONE", "instId": inst_id, "tf": tf, "zone": zone}

        if msg_type != "DIV":
            raise HTTPException(status_code=400, detail="Unknown type")

        zone_state = state.get_zone(key)
        if zone_state is None:
            return {"ok": True, "skipped": "no_zone_state"}

        if (zone_state.zone not in {"OVERSOLD", "OVERBOUGHT"}) or (
            (zone_state.ts + settings.zone_ttl_seconds) < time.time()
        ):
            return {"ok": True, "skipped": "zone_expired_or_neutral", "zone": zone_state.zone}

        if not state.can_trade(key, settings.cooldown_seconds):
            return {"ok": True, "skipped": "cooldown"}

        if zone_state.zone == "OVERSOLD":
            side = "buy"
            if not settings.enable_long:
                return {"ok": True, "skipped": "long_disabled"}
        else:
            side = "sell"
            if not settings.enable_short:
                return {"ok": True, "skipped": "short_disabled"}

        candles = fetch_okx_candles(settings.candles_base_url, inst_id, tf, limit=settings.candle_limit)
        entry_price = close_f or zone_state.close or (candles[-1].c if candles else None)
        if entry_price is None:
            return {"ok": True, "skipped": "no_entry_price"}

        if settings.stop_method == "pivot":
            sl = stop_loss_price(
                side=side,  # type: ignore[arg-type]
                entry_price=float(entry_price),
                candles=candles,
                pivot_len=settings.pivot_len,
                atr_len=settings.atr_len,
                atr_buffer_mult=settings.atr_buffer_mult,
                min_buffer_bps=settings.min_buffer_bps,
            )
        else:
            sl = stop_loss_price_lookback(
                side=side,  # type: ignore[arg-type]
                entry_price=float(entry_price),
                candles=candles,
                lookback_bars=settings.stop_lookback_bars,
                atr_len=settings.atr_len,
                atr_buffer_mult=settings.atr_buffer_mult,
                min_buffer_bps=settings.min_buffer_bps,
            )
        if sl is None:
            return {"ok": True, "skipped": "no_stoploss"}

        if side == "buy" and float(sl) >= float(entry_price):
            return {"ok": True, "skipped": "invalid_stoploss", "reason": "sl_gte_entry", "sl": sl, "entry": float(entry_price)}
        if side == "sell" and float(sl) <= float(entry_price):
            return {"ok": True, "skipped": "invalid_stoploss", "reason": "sl_lte_entry", "sl": sl, "entry": float(entry_price)}

        tp = take_profit_price(side=side, entry_price=float(entry_price), stop_loss=float(sl), rr=settings.tp_rr)  # type: ignore[arg-type]

        # Default behavior: paper decision only.
        can_execute = bool(service.state.trading_enabled) and (os.getenv("PERPBOT_TV_TRADING_ENABLED", "false").lower() in {"1","true","yes","y","on"})
        exec_result = None
        if can_execute:
            exchange = next((ex for ex in service.exchanges if ex.name == exchange_name), None)
            if exchange is None:
                raise HTTPException(status_code=503, detail=f"Exchange not available: {exchange_name}")
            try:
                size = resolve_size_for_exchange(
                    exchange=exchange_name,
                    default_size=settings.order_size,
                    per_exchange=settings.order_size_by_exchange,
                )

                # Use new executor with stop-loss support
                hedge_mode = os.getenv("PERPBOT_TV_HEDGE_MODE", "true").lower() in {"1","true","yes","y","on"}
                place_sl = os.getenv("PERPBOT_TV_PLACE_STOP_LOSS", "true").lower() in {"1","true","yes","y","on"}

                exec_result = execute_market_with_stop_loss(
                    exchange_client=exchange,
                    exchange_name=exchange_name,
                    canonical_symbol=symbol,
                    side=side,
                    size=size,
                    stop_loss_price=float(sl),
                    entry_price=float(entry_price),
                    symbol_overrides=settings.symbol_overrides_by_exchange,
                    hedge_mode=hedge_mode,
                    place_stop_loss=place_sl,
                )

                if exec_result.ok:
                    state.mark_traded(key)
                    logger.info(
                        "tv168 execution success: exchange=%s symbol=%s side=%s status=%s "
                        "entry_order=%s sl_order=%s elapsed_ms=%s",
                        exchange_name, symbol, side, exec_result.status.value,
                        exec_result.order.id if exec_result.order else None,
                        exec_result.stop_loss_order.id if exec_result.stop_loss_order else None,
                        exec_result.elapsed_ms,
                    )
                else:
                    logger.error(
                        "tv168 execution failed: exchange=%s symbol=%s error_class=%s error=%s",
                        exchange_name, symbol,
                        exec_result.error_class.value if exec_result.error_class else None,
                        exec_result.error_msg,
                    )
                    raise HTTPException(
                        status_code=502,
                        detail=f"Order failed ({exec_result.error_class.value if exec_result.error_class else 'unknown'}): {exec_result.error_msg}"
                    )

            except HTTPException:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.exception("TradingView execution failed: %s", exc)
                raise HTTPException(status_code=502, detail=f"Order failed: {exc}") from exc

        return {
            "ok": True,
            "type": "DIV",
            "instId": inst_id,
            "symbol": symbol,
            "tf": tf,
            "zone": zone_state.zone,
            "side": side,
            "entry": float(entry_price),
            "sl": float(sl),
            "tp": float(tp) if tp is not None else None,
            "exchange": exchange_name,
            "paper": not can_execute,
            "order": (asdict(exec_result.order) if exec_result and exec_result.order else None),
            "stop_loss_order": (asdict(exec_result.stop_loss_order) if exec_result and exec_result.stop_loss_order else None),
            "execution": (exec_result.to_dict() if exec_result else None),
        }

    return router
