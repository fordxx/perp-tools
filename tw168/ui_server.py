from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Form, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import math
from pydantic import BaseModel
def _sf(v):
    """Sanitize float for JSON: NaN/Inf -> None (null)"""
    try:
        if isinstance(v, (float, np.float64, np.float32)):
            if math.isnan(v) or math.isinf(v):
                return None
        return v
    except:
        return v


from app.config import SETTINGS
from app.state import InMemoryState
from app.fill_tracker import FillTracker
from app.notify import notify_info

# Initialize logger
logger = logging.getLogger("uvicorn.error")

# Initialize components
state = InMemoryState()
fill_tracker = FillTracker()

# Create FastAPI app for UI
ui_app = FastAPI(title="TW168 Trading UI", description="Web interface for TW168 trading system")

@ui_app.on_event("startup")
async def startup_event():
    """Start background tasks on startup"""
    try:
        from app.main import candle_ws_manager, candle_ws_symbol_tfs
        if candle_ws_manager:
            logger.info("🔌 Starting Candle WebSocket Manager from UI...")
            candle_ws_manager.start()
            
            # Explicitly subscribe to configured symbols/tfs
            if candle_ws_symbol_tfs:
                logger.info(f"📡 Subscribing to {len(candle_ws_symbol_tfs)} symbols from CANDLE_WS_SYMBOL_TFS...")
                for inst_id, tfs in candle_ws_symbol_tfs.items():
                    for tf in tfs:
                        await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf=tf)
            else:
                # Fallback to allowlist if no specific TFs configured
                from app.main import allowed_symbols
                logger.info(f"📡 Subscribing to allowlisted symbols: {allowed_symbols}")
                for inst_id in allowed_symbols:
                    if inst_id != "*":
                        await candle_ws_manager.ensure_subscription(inst_id=inst_id, tf="1h")
    except Exception as e:
        logger.error(f"❌ Failed to start CandleWsManager: {e}")

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
ui_app.mount("/static", StaticFiles(directory="static"), name="static")

# In-memory storage for UI data
ui_data = {
    "signal_history": [],
    "system_status": {
        "uptime": 0,
        "last_signal": None,
        "total_signals": 0,
        "active_positions": 0
    }
}

# --- Indicator Calculation Logic (Optimized for UI) ---

# Parameters
ATR_PERIOD = 10
ATR_MULT = 3.0
ADX_PERIOD = 14
# Wave Filter Params
WAVE_LENGTH = 14
WAVE_SMOOTH = 3

def rma_ui(s: pd.Series, period: int) -> pd.Series:
    """Relative Moving Average (used in ATR/ADX/RSI) - Fix NaN by using min_periods=1"""
    return s.ewm(alpha=1.0 / period, min_periods=1, adjust=False).mean()


def calculate_wave_filter_ui(df: pd.DataFrame, length: int = WAVE_LENGTH, smooth: int = WAVE_SMOOTH):
    """Ultra-precise Wave Filter matching 1.txt (Stoch RSI centered at 0)"""
    close = df['close']
    high = df['high'].values
    low = df['low'].values
    
    # 1. Base RSI (using RMA equivalent)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = rma_ui(gain.fillna(0.0), length)
    avg_loss = rma_ui(loss.fillna(0.0), length).replace(0, 1e-10)
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))
    
    # 2. Measurement of RSI fluctuations
    rsi_hh = rsi.rolling(window=length).max()
    rsi_ll = rsi.rolling(window=length).min()
    fluctuation = rsi_hh - rsi_ll
    
    # 3. Stochastic RSI calculation
    stoch_rsi = np.where(fluctuation == 0, 0, (rsi - rsi_ll) / fluctuation * 100)
    
    # 4. Smooth and center to [-50, 50]
    osc = (pd.Series(stoch_rsi).rolling(window=smooth, min_periods=1).mean() - 50).fillna(0).values
    
    # Visually stunning Red/Green pillars
    # Red pillars rise UP from +40 when osc > 40
    # Green pillars descend DOWN from -40 when osc < -40
    red_p = [v if v > 40.0 else 40.0 for v in osc]
    green_p = [v if v < -40.0 else -40.0 for v in osc]
    
    # Divergence Logic (lookback 4)
    bu, be = np.zeros(len(osc), dtype=bool), np.zeros(len(osc), dtype=bool)
    lb, lf = 4, 4
    
    for i in range(lb, len(osc) - lf):
        # Pivot High
        is_ph = True
        for j in range(i - lb, i + lf + 1):
            if osc[j] > osc[i]:
                is_ph = False
                break
        if is_ph:
            # Search for previous pivot high
            prev_idx = -1
            for k in range(i - 1, lb - 1, -1):
                pk = True
                for m in range(k - lb, k + lf + 1):
                    if osc[m] > osc[k]: pk = False; break
                if pk: prev_idx = k; break
            
            if prev_idx != -1:
                # Bearish Divergence
                if high[i] > high[prev_idx] and osc[i] < osc[prev_idx] and osc[i] > 0:
                    be[i] = True
        
        # Pivot Low
        is_pl = True
        for j in range(i - lb, i + lf + 1):
            if osc[j] < osc[i]:
                is_pl = False
                break
        if is_pl:
            # Search for previous pivot low
            prev_idx = -1
            for k in range(i - 1, lb - 1, -1):
                pk = True
                for m in range(k - lb, k + lf + 1):
                    if osc[m] < osc[k]: pk = False; break
                if pk: prev_idx = k; break
            
            if prev_idx != -1:
                # Bullish Divergence
                if low[i] < low[prev_idx] and osc[i] > osc[prev_idx] and osc[i] < 0:
                    bu[i] = True
            
    return osc, red_p, green_p, bu, be






def calculate_supertrend_ui(df: pd.DataFrame, period: int = ATR_PERIOD, multiplier: float = ATR_MULT):
    """Calculate SuperTrend for UI display"""
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    # ATR
    tr1 = pd.Series(high - low)
    tr2 = pd.Series(abs(high - pd.Series(close).shift(1)))
    tr3 = pd.Series(abs(low - pd.Series(close).shift(1)))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = rma_ui(tr.fillna(0.0), period).values
    
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr

    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()
    supertrend = np.empty(len(close), dtype=float)
    direction = np.ones(len(close), dtype=int)

    supertrend[0] = basic_lower[0]

    for i in range(1, len(close)):
        # Final Upper Band
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final Lower Band
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Direction and Supertrend
        if supertrend[i - 1] == final_upper[i - 1]:
            if close[i] <= final_upper[i]:
                supertrend[i] = final_upper[i]
                direction[i] = -1
            else:
                supertrend[i] = final_lower[i]
                direction[i] = 1
        else:
            if close[i] >= final_lower[i]:
                supertrend[i] = final_lower[i]
                direction[i] = 1
            else:
                supertrend[i] = final_upper[i]
                direction[i] = -1
                
    return supertrend, direction

def calculate_adx_ui(df: pd.DataFrame, period: int = ADX_PERIOD):
    """Calculate ADX for UI display"""
    high = df['high']
    low = df['low']
    close = df['close']
    
    up_move = high.diff()
    down_move = -low.diff()
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    # ATR for normalization
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = rma_ui(tr.fillna(0.0), period)
    
    plus_di = 100.0 * rma_ui(pd.Series(plus_dm), period) / atr
    minus_di = 100.0 * rma_ui(pd.Series(minus_dm), period) / atr
    
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = rma_ui(dx.fillna(0.0), period)
    
    return adx.fillna(0.0).values, plus_di.fillna(0.0).values, minus_di.fillna(0.0).values

# --- End of Indicator Logic ---

class SignalRequest(BaseModel):
    instId: str
    tf: str
    side: str
    admin_key: str | None = None
    entry_price: float | None = None
    sl_price: float | None = None
    lever: str | None = None
    mgn_mode: str | None = None
    risk_usdt: float | None = None


_LOCAL_EXCHANGE_READY = False
_LOCAL_EXCHANGE_READY_LOCK = asyncio.Lock()


def _should_validate_admin_key_locally() -> bool:
    # Allow running the UI without a configured secret (remote will validate),
    # but validate locally when a real secret is set.
    return bool(SETTINGS.tv_webhook_secret and SETTINGS.tv_webhook_secret != "CHANGE_ME")


async def _ensure_local_exchange_ready() -> None:
    """Ensure local exchange is connected when UI processes signals locally."""
    global _LOCAL_EXCHANGE_READY
    if _LOCAL_EXCHANGE_READY:
        return
    async with _LOCAL_EXCHANGE_READY_LOCK:
        if _LOCAL_EXCHANGE_READY:
            return

        from app import main as trading_main

        if SETTINGS.exchange in {"grvt", "lighter"}:
            await trading_main.exchange.connect()

        _LOCAL_EXCHANGE_READY = True


async def _forward_manual_signal(*, inst_id: str, tf: str, side: str, entry_price: float | None = None, sl_price: float | None = None, lever: str | None = None, mgn_mode: str | None = None, risk_usdt: float | None = None) -> tuple[int, dict]:
    """Forward a manual signal to the configured trading service."""
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")

    url = f"{base_url}/manual/signal"
    payload: dict = {
        "instId": inst_id,
        "tf": tf,
        "side": side,
        "type": "DIV",
        "admin_key": SETTINGS.tv_webhook_secret,
    }
    if entry_price and entry_price > 0:
        payload["entry_price"] = entry_price
    if sl_price and sl_price > 0:
        payload["sl_price"] = sl_price
    if lever:
        payload["lever"] = lever
    if mgn_mode:
        payload["mgn_mode"] = mgn_mode
    if risk_usdt and risk_usdt > 0:
        payload["risk_usdt"] = risk_usdt

    # Small retry helps with transient network hiccups, but if the port is blocked
    # (common on Lightsail when 8000 is not opened), it will still fail fast.
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, json=payload)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_exc = e
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            hint = (
                f"Cannot reach trading service: {base_url}. "
                "If this is a remote server, ensure the port is open in the firewall/security-group "
                "(Lightsail Networking) and the service listens on 0.0.0.0. "
                "Prefer exposing via 443 (reverse proxy) if you want long-term stability."
            )
            raise RuntimeError(f"{hint} (last_error={type(e).__name__}: {e})") from e
    else:
        # Defensive fallback (should not happen)
        raise RuntimeError(f"Failed to reach trading service: {base_url} (last_error={last_exc})")

    try:
        data = resp.json()
    except Exception:
        data = {"detail": resp.text}

    return resp.status_code, data


async def _fetch_remote_grvt_markets() -> tuple[int, dict]:
    """Fetch GRVT markets from the remote trading service (proxied by local UI to avoid CORS)."""
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")

    url = f"{base_url}/api/grvt/markets"
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid_json", "detail": resp.text}
    return resp.status_code, data


async def _fetch_remote_open_orders(inst_id: str | None = None) -> tuple[int, dict]:
    """Fetch open orders from the remote trading service (proxied by local UI)."""
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")

    url = f"{base_url}/api/orders/open"
    params = {}
    if inst_id:
        params["instId"] = inst_id

    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params)
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid_json", "detail": resp.text}
    return resp.status_code, data


async def _post_remote_cancel_order(*, inst_id: str, order_id: str) -> tuple[int, dict]:
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")
    url = f"{base_url}/api/orders/cancel"
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            json={"instId": inst_id, "order_id": order_id, "admin_key": SETTINGS.tv_webhook_secret},
        )
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid_json", "detail": resp.text}
    return resp.status_code, data


async def _post_remote_replace_order(
    *,
    inst_id: str,
    order_id: str,
    new_price: str,
    new_size: str | None,
) -> tuple[int, dict]:
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")
    url = f"{base_url}/api/orders/replace"
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            url,
            json={
                "instId": inst_id,
                "order_id": order_id,
                "new_price": new_price,
                "new_size": new_size,
                "admin_key": SETTINGS.tv_webhook_secret,
            },
        )
    try:
        data = resp.json()
    except Exception:
        data = {"ok": False, "error": "invalid_json", "detail": resp.text}
    return resp.status_code, data

def get_system_info() -> Dict[str, Any]:
    """Get current system information"""
    uptime = time.time() - getattr(ui_app, 'start_time', time.time())
    return {
        "uptime": int(uptime),
        "exchange": SETTINGS.exchange,
        "trading_enabled": SETTINGS.trading_enabled,
        "total_signals": len(ui_data["signal_history"]),
        "active_positions": ui_data["system_status"]["active_positions"],
        "last_signal": ui_data["system_status"]["last_signal"]
    }

def add_signal_to_history(signal: Dict[str, Any], result: Dict[str, Any], status: str) -> None:
    """Add signal to history"""
    ui_data["signal_history"].append({
        "timestamp": datetime.now().isoformat(),
        "signal": signal,
        "result": result,
        "status": status
    })
    # Keep only last 100 signals
    ui_data["signal_history"] = ui_data["signal_history"][-100:]
    ui_data["system_status"]["last_signal"] = datetime.now().isoformat()


def _normalize_inst_id_ui(raw_inst_id: str | None) -> str | None:
    if not raw_inst_id:
        return None
    inst_id = str(raw_inst_id).strip()
    if not inst_id:
        return None
    inst_up = inst_id.upper()
    # TradingView style: BTCUSDT.P
    if inst_up.endswith(".P"):
        inst_up = inst_up[:-2]
    inst_up = inst_up.replace("/", "")
    # GRVT style: BTC_USDT_Perp / BTC_USDT_PERP -> BTC-USDT-SWAP
    if "-" not in inst_up and "_USDT" in inst_up:
        base = inst_up.split("_USDT", 1)[0]
        if base:
            return f"{base}-USDT-SWAP"
    # OKX style: BTCUSDT -> BTC-USDT-SWAP
    if "-" not in inst_up and inst_up.endswith("USDT"):
        base = inst_up[:-4]
        if base:
            return f"{base}-USDT-SWAP"
    return inst_up

@ui_app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard page"""
    # Forced only BTC and ETH
    symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    # Try to fetch symbols from exchange
    try:
        from app.main import exchange
        if exchange and hasattr(exchange, "api") and hasattr(exchange.api, "markets") and exchange.api.markets:
             # Get keys (e.g. BTC_USDT_Perp)
             # If user wants GRVT style, just use them.
             # Or try to normalize to TV style? 
             # User said: "Add GRVT trading pairs". 
             # Let's list the raw keys from GRVT to be safe/accurate for API.
             symbols = sorted(list(exchange.api.markets.keys()))
    except Exception:
        pass

    if not symbols:
        # Fallback
        symbols = ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "LINK-USDT-SWAP",
                   "DOGE-USDT-SWAP", "BNB-USDT-SWAP", "BCH-USDT-SWAP", "TRX-USDT-SWAP",
                   "EIGEN-USDT-SWAP", "ETHFI-USDT-SWAP", "FARTCOIN-USDT-SWAP", "JTO-USDT-SWAP",
                   "PUMP-USDT-SWAP", "TAO-USDT-SWAP", "TON-USDT-SWAP", "TRUMP-USDT-SWAP",
                   "PENGU-USDT-SWAP", "BONK-USDT-SWAP", "BOME-USDT-SWAP", "PNUT-USDT-SWAP",
                   "XRP-USDT-SWAP", "ONDO-USDT-SWAP", "LTC-USDT-SWAP", "PENDLE-USDT-SWAP",
                   "MON-USDT-SWAP", "WLD-USDT-SWAP", "WLFI-USDT-SWAP"]
    
    admin_key = SETTINGS.tv_webhook_secret if SETTINGS.tv_webhook_secret != "CHANGE_ME" else ""

    return templates.TemplateResponse("index.html", {
        "request": request, 
        "symbols": symbols,
        "admin_key": admin_key
    })

@ui_app.get("/api/system/status")
async def get_system_status():
    """Get current system status"""
    return get_system_info()


@ui_app.get("/api/symbols")
async def get_okx_symbols() -> dict:
    """Fetch all OKX SWAP instruments (public, no auth needed)."""
    try:
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://www.okx.com/api/v5/public/instruments",
                params={"instType": "SWAP"},
            )
            resp.raise_for_status()
            data = resp.json().get("data") or []
        symbols = sorted(
            item["instId"] for item in data
            if item.get("instId", "").endswith("-USDT-SWAP") and item.get("state") == "live"
        )
        return {"ok": True, "symbols": symbols}
    except Exception as e:
        logger.error("Failed to fetch OKX symbols: %s", e)
        return {"ok": False, "symbols": [], "error": str(e)}


@ui_app.get("/api/tickers")
async def get_okx_tickers() -> dict:
    """Fetch mark prices for all USDT SWAP instruments."""
    try:
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                "https://www.okx.com/api/v5/market/tickers",
                params={"instType": "SWAP"},
            )
            resp.raise_for_status()
            data = resp.json().get("data") or []
        prices = {
            item["instId"]: item.get("last", "")
            for item in data
            if item.get("instId", "").endswith("-USDT-SWAP")
        }
        return {"ok": True, "prices": prices}
    except Exception as e:
        return {"ok": False, "prices": {}, "error": str(e)}


class LeverageRequest(BaseModel):
    instId: str
    lever: str
    mgnMode: str = "cross"


@ui_app.get("/api/leverage")
async def get_leverage(instId: str, mgnMode: str = "cross") -> dict:
    """Get current leverage for an instrument."""
    try:
        from app.main import exchange
        resp = await exchange._request_async(
            "GET", "/api/v5/account/leverage-info",
            params={"instId": instId, "mgnMode": mgnMode},
            is_trading=True,
        )
        data = (resp.get("data") or [{}])[0]
        return {"ok": True, "lever": data.get("lever", "10"), "mgnMode": mgnMode}
    except Exception as e:
        return {"ok": False, "lever": "10", "error": str(e)}


@ui_app.post("/api/leverage")
async def set_leverage(req: LeverageRequest) -> dict:
    """Set leverage for an instrument."""
    try:
        from app.main import exchange
        if req.mgnMode == "cross":
            # OKX cross mode: use ccy, not instId (instId not allowed for cross SWAP)
            parts = req.instId.split("-")  # e.g. BTC-USDT-SWAP -> ["BTC","USDT","SWAP"]
            ccy = parts[1] if len(parts) >= 2 else "USDT"
            resp = await exchange._request_async(
                "POST", "/api/v5/account/set-leverage",
                json_body={"ccy": ccy, "lever": req.lever, "mgnMode": "cross"},
                is_trading=True,
            )
        else:
            # Isolated mode: need posSide; set for both long and short
            for pos_side in ("long", "short"):
                resp = await exchange._request_async(
                    "POST", "/api/v5/account/set-leverage",
                    json_body={"instId": req.instId, "lever": req.lever, "mgnMode": "isolated", "posSide": pos_side},
                    is_trading=True,
                )
        if str(resp.get("code", "")) in {"0", "success"}:
            return {"ok": True, "lever": req.lever, "mgnMode": req.mgnMode}
        return {"ok": False, "error": resp.get("msg", "failed")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@ui_app.get("/api/algo_orders")
async def get_algo_orders(instId: str) -> dict:
    """Get pending algo (SL/TP) orders for an instrument."""
    try:
        from app.main import exchange
        orders = await exchange.get_algo_orders(inst_id=instId, ord_type="conditional")
        result = []
        for o in (orders or []):
            sl = o.get("slTriggerPx") or o.get("sl_trigger_px") or ""
            tp = o.get("tpTriggerPx") or o.get("tp_trigger_px") or ""
            side = o.get("side") or ""
            pos_side = o.get("posSide") or ""
            algo_id = o.get("algoId") or o.get("ordId") or ""
            result.append({"algoId": algo_id, "side": side, "posSide": pos_side, "slTriggerPx": sl, "tpTriggerPx": tp})
        return {"ok": True, "orders": result}
    except Exception as e:
        return {"ok": False, "orders": [], "error": str(e)}


@ui_app.get("/api/pending_orders")
async def get_pending_orders(instId: str | None = None) -> dict:
    """Get all pending limit orders + algo (SL/TP) orders from OKX."""
    try:
        from app.main import exchange
        params: dict = {"instType": "SWAP"}
        if instId:
            params["instId"] = instId
        # Regular limit/market pending orders
        resp = await exchange._request_async("GET", "/api/v5/trade/orders-pending", params=params, is_trading=True)
        orders = resp.get("data") or []
        # Algo (SL/TP/conditional) pending orders
        algo_resp = await exchange._request_async("GET", "/api/v5/trade/orders-algo-pending", params={**params, "ordType": "conditional"}, is_trading=True)
        algo_orders = algo_resp.get("data") or []
        result = []
        for o in orders:
            result.append({
                "ordId": o.get("ordId", ""),
                "instId": o.get("instId", ""),
                "side": o.get("side", ""),
                "posSide": o.get("posSide", ""),
                "ordType": o.get("ordType", ""),
                "px": o.get("px", ""),
                "sz": o.get("sz", ""),
                "fillSz": o.get("fillSz", "0"),
                "state": o.get("state", ""),
                "cTime": o.get("cTime", ""),
                "isAlgo": False,
            })
        for o in algo_orders:
            result.append({
                "ordId": o.get("algoId", o.get("ordId", "")),
                "instId": o.get("instId", ""),
                "side": o.get("side", ""),
                "posSide": o.get("posSide", ""),
                "ordType": o.get("ordType", ""),
                "px": o.get("slTriggerPx") or o.get("tpTriggerPx") or "",
                "slTriggerPx": o.get("slTriggerPx", ""),
                "tpTriggerPx": o.get("tpTriggerPx", ""),
                "sz": o.get("sz", ""),
                "fillSz": "0",
                "state": o.get("state", ""),
                "cTime": o.get("cTime", ""),
                "isAlgo": True,
            })
        return {"ok": True, "orders": result}
    except Exception as e:
        return {"ok": False, "orders": [], "error": str(e)}


@ui_app.get("/api/symbols/grvt")
async def get_grvt_symbols() -> dict:
    """Proxy GRVT market list from the remote trading service (avoids browser CORS)."""
    status, data = await _fetch_remote_grvt_markets()
    if isinstance(data, dict):
        data.setdefault("status_code", status)
    return data


@ui_app.get("/api/open_orders")
async def get_open_orders(instId: str | None = Query(default=None)) -> dict:
    """Proxy remote open orders list."""
    status, data = await _fetch_remote_open_orders(inst_id=instId)
    if isinstance(data, dict):
        data.setdefault("status_code", status)
    return data


class CancelOpenOrderRequest(BaseModel):
    instId: str
    order_id: str


class ReplaceOpenOrderRequest(BaseModel):
    instId: str
    order_id: str
    new_price: str
    new_size: str | None = None


@ui_app.post("/api/open_orders/cancel")
async def cancel_open_order(req: CancelOpenOrderRequest) -> dict:
    status, data = await _post_remote_cancel_order(inst_id=req.instId, order_id=req.order_id)
    if isinstance(data, dict):
        data.setdefault("status_code", status)
    return data


@ui_app.post("/api/open_orders/replace")
async def replace_open_order(req: ReplaceOpenOrderRequest) -> dict:
    status, data = await _post_remote_replace_order(
        inst_id=req.instId,
        order_id=req.order_id,
        new_price=req.new_price,
        new_size=req.new_size,
    )
    if isinstance(data, dict):
        data.setdefault("status_code", status)
    return data

@ui_app.get("/api/positions")
async def get_positions_api():
    """Get current positions from exchange"""
    try:
        from app.main import exchange
        # OKXClient exposes get_position(inst_id, pos_side) but not get_positions().
        # Call the raw REST endpoint directly for all positions.
        if hasattr(exchange, "_request_async"):
            resp = await exchange._request_async(
                "GET", "/api/v5/account/positions",
                params={"instType": "SWAP"},
                is_trading=True,
            )
            positions = resp.get("data") or []
        elif hasattr(exchange, "get_positions"):
            positions = await exchange.get_positions()
        else:
            return {"positions": []}
        # Format for UI
        formatted = []
        for p in positions:
            # GRVT returns dict, normalise if needed
            inst_raw = (
                p.get("instId")
                or p.get("symbol")
                or p.get("instrument")
                or p.get("inst_id")
                or p.get("instrument_id")
            )
            inst_id = _normalize_inst_id_ui(inst_raw)
            avg_px = (
                p.get("avgPx")
                or p.get("entryPrice")
                or p.get("entry_price")
                or p.get("avgPx")
                or "0"
            )
            u_pnl = (
                p.get("pnl")
                or p.get("unrealizedPnl")
                or p.get("unrealized_pnl")
                or "0"
            )
            pos = p.get("pos") or p.get("size") or p.get("contracts") or "0"
            formatted.append({
                "instId": inst_id,
                "posSide": p.get("posSide") or "net",
                "pos": str(pos),
                "avgPx": str(avg_px),
                "uPnl": str(u_pnl),
            })
        return {"positions": formatted}
    except Exception as e:
        return {"error": str(e), "positions": []}

class ClosePositionRequest(BaseModel):
    instId: str
    posSide: str = "net"
    admin_key: str | None = None

@ui_app.post("/api/positions/close")
async def close_position_api(req: ClosePositionRequest):
    """Close a position"""
    try:
        from app.main import exchange
        
        # 1. Get current size to close
        positions = await exchange.get_positions()
        target_pos = None
        for p in positions:
            p_inst = p.get("instId") or p.get("symbol")
            if p_inst == req.instId:
                target_pos = p
                break
        
        if not target_pos:
             return {"ok": False, "error": "Position not found"}

        sz = target_pos.get("pos") or target_pos.get("size")
        if not sz or float(sz) == 0:
             return {"ok": False, "error": "Position size is 0"}

        # Determine side to close
        # If long, we sell. If short, we buy.
        # GRVT/CCXT usually: pos > 0 is long.
        size_float = float(sz)
        side_to_close = "sell" if size_float > 0 else "buy"
        
        # 2. Place reduce-only market order
        # Using place_order from exchange
        # (inst_id, td_mode, side, pos_side, ord_type, sz, px, cl_ord_id, reduce_only)
        
        cl_ord_id = f"close_{int(time.time())}"
        
        # GRVT specifically
        res = await exchange.place_order(
            inst_id=req.instId,
            td_mode="cross", # Default assumption
            side=side_to_close,
            pos_side=req.posSide, # net/long/short
            ord_type="market",
            sz=str(abs(size_float)),
            px=None,
            cl_ord_id=cl_ord_id,
            reduce_only=True
        )
        
        if str(res.get("code")) == "0":
             return {"ok": True, "msg": "Close order placed"}
        else:
             return {"ok": False, "error": res.get("msg")}

    except Exception as e:
        return {"ok": False, "error": str(e)}



async def fetch_okx_candles_async(inst_id: str, bar: str, limit: int = 300, after: str = None):
    """Fetch historical candles from OKX REST API. 'after' param in OKX API means candles BEFORE that timestamp."""
    url = "https://www.okx.com/api/v5/market/history-candles" if after else "https://www.okx.com/api/v5/market/candles"
    
    # OKX API: minutes are 'm', others (H, D, W, M) are uppercase
    if bar.endswith('m'):
        bar_norm = bar.lower()
    else:
        bar_norm = bar.upper()
    
    params = {"instId": inst_id, "bar": bar_norm, "limit": str(limit)}
    if after:
        params["after"] = str(after)
    
    timeout = httpx.Timeout(5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json().get("data", [])
            candles = []
            for row in reversed(data):
                candles.append({
                    "time": int(int(row[0]) / 1000),
                    "open": float(row[1]), "high": float(row[2]),
                    "low": float(row[3]), "close": float(row[4]),
                    "volume": float(row[5])
                })
            return candles
    except Exception as e:
        logger.error(f"❌ Failed to fetch REST candles (after={after}): {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Failed to fetch REST candles: {e}")
        return []


@ui_app.get("/api/candles/history")
async def get_historical_data(instId: str, tf: str, before: int):
    """API to fetch more history for infinite scroll. 'before' is a unix timestamp in seconds."""
    rest_candles = await fetch_okx_candles_async(instId, tf, limit=300, after=str(before * 1000))
    if not rest_candles:
        return {"ok": False, "data": []}
        
    df = pd.DataFrame(rest_candles)
    st_v, st_d = calculate_supertrend_ui(df)
    wa, wa_r, wa_g, wa_bu, wa_be = calculate_wave_filter_ui(df)
    
    payload = []
    for k in range(len(df)):
        payload.append({
            "time": int(df["time"].iloc[k]),
            "open": _sf(df["open"].iloc[k]), "high": _sf(df["high"].iloc[k]),
            "low": _sf(df["low"].iloc[k]), "close": _sf(df["close"].iloc[k]),
            "st": _sf(st_v[k]), "st_dir": int(st_d[k]),
            "wave": _sf(wa[k]), "wave_r": _sf(wa_r[k]), "wave_g": _sf(wa_g[k]),
            "bu": bool(wa_bu[k]), "be": bool(wa_be[k])
        })
    return {"ok": True, "data": payload}
@ui_app.websocket("/ws/chart/{instId}/{tf}")
async def chart_websocket(websocket: WebSocket, instId: str, tf: str):
    """WebSocket for real-time chart data including indicators"""
    await websocket.accept()
    logger.info(f"📈 Chart WebSocket connected: {instId} ({tf})")
    
    # Normalise instId
    normalized_inst = _normalize_inst_id_ui(instId)
    
    try:
        while True:
            # 1. Fetch candles from cache
            candles = None
            try:
                from app.main import candle_cache, candle_ws_manager
                # Ensure subscription exists
                if candle_ws_manager:
                    await candle_ws_manager.ensure_subscription(inst_id=instId, tf=tf)
                
                # Fetch whatever we have, at least 1 bar
                candles = await candle_cache.get_candles(
                    source="okx", inst_id=instId, tf=tf, min_bars=1
                )
                if not candles and normalized_inst:
                     candles = await candle_cache.get_candles(
                        source="okx", inst_id=normalized_inst, tf=tf, min_bars=1
                    )
            except Exception as e:
                logger.error(f"❌ Error fetching candles: {e}")
            
            if not candles or len(candles) == 0:
                # No data in cache, try REST API fallback for initial load
                await websocket.send_json({"type": "heartbeat", "time": time.time(), "msg": "正在从 OKX 补拉历史 K 线..."})
                rest_candles = await fetch_okx_candles_async(instId, tf, limit=300)
                if rest_candles:
                    # Transform to the internal DataFrame format for indicator calculation
                    df_rest = pd.DataFrame(rest_candles)
                    
                    # Indicators... (run in thread to avoid blocking event loop)
                    loop = asyncio.get_event_loop()
                    st_v, st_d = await loop.run_in_executor(None, calculate_supertrend_ui, df_rest)
                    wa, wa_r, wa_g, wa_bu, wa_be = await loop.run_in_executor(None, calculate_wave_filter_ui, df_rest)
                    
                    full_payload = []
                    for k in range(len(df_rest)):
                        full_payload.append({
                            "time": int(df_rest["time"].iloc[k]),
                            "open": _sf(df_rest["open"].iloc[k]), "high": _sf(df_rest["high"].iloc[k]),
                            "low": _sf(df_rest["low"].iloc[k]), "close": _sf(df_rest["close"].iloc[k]),
                            "st": _sf(st_v[k]), "st_dir": int(st_d[k]),
                            "wave": _sf(wa[k]), "wave_r": _sf(wa_r[k]), "wave_g": _sf(wa_g[k]),
                            "bu": bool(wa_bu[k]), "be": bool(wa_be[k])
                        })

                    await websocket.send_json({
                        "type": "data", "instId": instId, "tf": tf, 
                        "count": len(full_payload), "data": full_payload
                    })
                
                await asyncio.sleep(5) # Slow down polling if still no data
                continue
            
            # 2. Convert to DataFrame for calculation
            df_data = {
                "time": [c.ts_ms / 1000 for c in candles],
                "open": [float(c.open) for c in candles],
                "high": [float(c.high) for c in candles],
                "low": [float(c.low) for c in candles],
                "close": [float(c.close) for c in candles],
                "volume": [float(c.vol) for c in candles],
            }
            df = pd.DataFrame(df_data)
            
            # 3. Calculate indicators
            chart_data = []
            
            if len(df) >= 30:
                loop = asyncio.get_event_loop()
                st_val, st_dir = await loop.run_in_executor(None, calculate_supertrend_ui, df)
                wave_osc, wave_r, wave_g, wa_bu, wa_be = await loop.run_in_executor(None, calculate_wave_filter_ui, df)
                
                for i in range(len(df)):
                    chart_data.append({
                        "time": int(df["time"].iloc[i]),
                        "open": _sf(df["open"].iloc[i]), "high": _sf(df["high"].iloc[i]),
                        "low": _sf(df["low"].iloc[i]), "close": _sf(df["close"].iloc[i]),
                        "st": _sf(st_val[i]), "st_dir": int(st_dir[i]),
                        "wave": _sf(wave_osc[i]), "wave_r": _sf(wave_r[i]), "wave_g": _sf(wave_g[i]),
                        "bu": bool(wa_bu[i]), "be": bool(wa_be[i]),
                    })

            else:
                # Basic K-line only
                for i in range(len(df)):
                    chart_data.append({
                        "time": int(df["time"].iloc[i]),
                        "open": _sf(df["open"].iloc[i]),
                        "high": _sf(df["high"].iloc[i]),
                        "low": _sf(df["low"].iloc[i]),
                        "close": _sf(df["close"].iloc[i]),
                        "st": _sf(df["close"].iloc[i]),
                        "st_dir": 1,
                        "wave": 0, "wave_r": 40.0, "wave_g": -40.0,
                        "bu": False, "be": False
                    })
            
            await websocket.send_json({
                "type": "data",
                "instId": instId,
                "tf": tf,
                "count": len(chart_data),
                "data": chart_data
            })
            
            # High frequency update: 1s for TV-like experience
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(f"📉 Chart WebSocket disconnected: {instId} ({tf})")
    except Exception as e:
        logger.error(f"❌ Chart WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass

@ui_app.get("/api/signals/history")
async def get_signals_history(limit: int = Query(20, ge=1, le=100)):
    """Get recent signal history for the UI."""
    history = ui_data["signal_history"][-limit:]
    return {"history": history}

@ui_app.post("/signals/send")
async def send_signal_api(request: SignalRequest):
    """Send trading signal via API"""
    try:
        if SETTINGS.trading_service_base_url:
            status, result = await _forward_manual_signal(
                inst_id=request.instId,
                tf=request.tf,
                side=request.side,
                entry_price=request.entry_price,
                sl_price=request.sl_price,
                lever=request.lever,
                mgn_mode=request.mgn_mode,
                risk_usdt=request.risk_usdt,
            )
            if status >= 400:
                detail = result.get("detail") if isinstance(result, dict) else str(result)
                raise HTTPException(status_code=status, detail=detail)
        else:
            # Import here to avoid circular imports
            from app.main import _process_payload, TvPayload

            # Validate admin key (optional)
            if _should_validate_admin_key_locally() and request.admin_key != SETTINGS.tv_webhook_secret:
                raise HTTPException(status_code=403, detail="Invalid admin key")

            # Ensure exchange is connected when needed (GRVT/Lighter)
            await _ensure_local_exchange_ready()

            # Create payload
            payload = TvPayload(
                secret=SETTINGS.tv_webhook_secret,
                type="DIV",
                instId=request.instId,
                tf=request.tf,
                side=request.side,
                t=datetime.now().isoformat() + "Z"
            )

            # Process signal locally
            result = await _process_payload(payload, allow_no_zone=True, source="ui")

        # Add to history
        add_signal_to_history(
            signal={"instId": request.instId, "tf": request.tf, "side": request.side},
            result=result,
            status="success" if result.get("ok") else "error"
        )

        return result

    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        add_signal_to_history(
            signal={"instId": request.instId, "tf": request.tf, "side": request.side},
            result={"error": detail},
            status="error",
        )
        raise
    except Exception as e:
        error_msg = str(e)
        add_signal_to_history(
            signal={"instId": request.instId, "tf": request.tf, "side": request.side},
            result={"error": error_msg},
            status="error"
        )
        raise HTTPException(status_code=500, detail=error_msg)

@ui_app.post("/signals/send/form")
async def send_signal_form(
    instId: str = Form(...),
    tf: str = Form(...),
    side: str = Form(...),
):
    """Send trading signal via form submission"""
    try:
        if SETTINGS.trading_service_base_url:
            status, remote = await _forward_manual_signal(inst_id=instId, tf=tf, side=side)
            if status >= 400:
                detail = remote.get("detail") if isinstance(remote, dict) else str(remote)
                result = {"ok": False, "error": detail}
            else:
                result = remote
        else:
            # Import here to avoid circular imports
            from app.main import _process_payload, TvPayload

            # Ensure exchange is connected when needed (GRVT/Lighter)
            await _ensure_local_exchange_ready()

            # Create payload
            payload = TvPayload(
                secret=SETTINGS.tv_webhook_secret,
                type="DIV",
                instId=instId,
                tf=tf,
                side=side,
                t=datetime.now().isoformat() + "Z"
            )

            # Process signal locally
            result = await _process_payload(payload, allow_no_zone=True, source="ui")

        # Add to history
        add_signal_to_history(
            signal={"instId": instId, "tf": tf, "side": side},
            result=result,
            status="success" if result.get("ok") else "error"
        )

        return result

    except Exception as e:
        error_msg = str(e)
        add_signal_to_history(
            signal={"instId": instId, "tf": tf, "side": side},
            result={"error": error_msg},
            status="error"
        )
        return {"ok": False, "error": error_msg}

# Duplicate /api/positions removed — real implementation is at line ~689


@ui_app.get("/api/compute_sl")
async def compute_sl_api(instId: str, tf: str, side: str, entry: float) -> dict:
    """Compute strategy SL and estimated entry offset - used by order setup panel."""
    try:
        from app.main import candle_cache, _get_ref_price_from_bar  # type: ignore
        from app.config import get_entry_two_limit_towards_sl_pct, get_lookback_bars  # type: ignore
        from app.risk import stop_loss_price_lookback, fetch_candles_paged  # type: ignore

        # Use 1m ref bar price as reference (falls back to current entry if unavailable)
        ref_price = await _get_ref_price_from_bar(instId, bar=SETTINGS.entry_two_limit_ref_bar)
        ref = float(ref_price) if ref_price else entry

        tf_lower = tf.lower()
        # Get candles: try cache first, then fetch from OKX
        candles = []
        if candle_cache:
            try:
                candles = await candle_cache.get_candles(source="okx", inst_id=instId, tf=tf_lower, min_bars=1) or []
            except Exception:
                candles = []
        if len(candles) < 50:
            try:
                candles = await asyncio.to_thread(
                    fetch_candles_paged, SETTINGS.okx_base_url, instId, tf_lower, 200
                )
            except Exception:
                pass

        if not candles or len(candles) < 10:
            return {"ok": False, "error": "insufficient candle data"}

        sl = stop_loss_price_lookback(
            side=side,
            entry_price=ref,
            candles=candles,
            lookback_bars=get_lookback_bars(tf_lower),
            atr_len=SETTINGS.atr_len,
            atr_buffer_mult=SETTINGS.atr_buffer_mult,
            min_buffer_bps=SETTINGS.min_buffer_bps,
        )
        if not sl:
            return {"ok": False}

        sl_f = float(sl)
        d = (ref - sl_f) if side == "buy" else (sl_f - ref)
        result: dict = {"ok": True, "sl": sl_f}
        if d > 0:
            pct = float(get_entry_two_limit_towards_sl_pct(tf_lower))
            offset_entry = (ref - pct * d) if side == "buy" else (ref + pct * d)
            result["entry"] = round(offset_entry, 2)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}

@ui_app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}



def create_templates():
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)
    index_html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>📈 TW168 Terminal Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <style>
        :root { --border: #e0e3eb; --active: #2962ff; --bg: #f8f9fb; --pane-bg: #ffffff; }
        body { background: var(--bg); color: #131722; font-family: -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif; margin:0; overflow: hidden; }
        .top-bar { height: 48px; background: #ffffff; border-bottom: 1px solid var(--border); display: flex; align-items: center; padding: 0 15px; justify-content: space-between; }
        .main-layout { display: flex; height: calc(100vh - 48px); }
        .sidebar { width: 300px; border-right: 1px solid var(--border); background: #ffffff; display: flex; flex-direction: column; }
        .content-area { flex: 1; display: flex; flex-direction: column; background: #ffffff; }
        .pane { width: 100%; border-bottom: 1px solid var(--border); background: var(--pane-bg); }
        #logConsole { height: 200px; background: #1e1e1e; color: #d1d4dc; font-size: 11px; padding: 10px; overflow-y: auto; font-family: "Consolas", monospace; border-top: 1px solid var(--border); }
        .form-select-tv { background: #fff; border: 1px solid #d1d4dc; color: #333; font-size: 13px; border-radius: 4px; padding: 2px 8px; font-weight: 600; cursor: pointer; }
        .form-select-tv:hover { border-color: #2962ff; }
        .nav-tabs .nav-link { color: #787b86; font-size: 12px; font-weight: 600; border: none; border-bottom: 2px solid transparent; }
        .nav-tabs .nav-link.active { color: #2962ff; border-bottom: 2px solid #2962ff; background: transparent; }
        .badge-custom { font-size: 10px; padding: 4px 8px; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="top-bar">
        <div class="d-flex align-items-center">
            <i class="fas fa-bolt text-warning me-2"></i>
            <span class="fw-bold me-3" style="font-size:16px;">TW168 <span style="color:#2962ff">PRO</span></span>
            <select class="form-select-tv me-2" id="iS">{% for s in symbols %}<option value="{{s}}">{{s}}</option>{% endfor %}</select>
            <select class="form-select-tv" id="tS">
                <optgroup label="分钟"><option value="1m">1m</option><option value="3m">3m</option><option value="5m">5m</option><option value="15m">15m</option><option value="30m">30m</option></optgroup>
                <optgroup label="小时"><option value="1H" selected>1h</option><option value="2H">2h</option><option value="4H">4h</option><option value="12H">12h</option></optgroup>
                <optgroup label="日/周"><option value="1D">1D</option><option value="1W">1W</option></optgroup>
            </select>
        </div>
        <div id="statusText" class="small fw-600 text-muted"><i class="fas fa-circle text-success me-1" style="font-size:8px"></i>系统就绪</div>
        <div class="d-flex align-items-center">
            <div id="priceInfo" class="me-3 fw-bold" style="font-size:14px; color:#2962ff">--</div>
            <button class="btn btn-sm btn-outline-primary" onclick="connect()"><i class="fas fa-sync-alt"></i></button>
        </div>
    </div>
    <div class="main-layout">
        <div class="sidebar">
            <ul class="nav nav-tabs px-2 mt-2">
                <li class="nav-item"><button class="nav-link active" data-bs-toggle="tab" data-bs-target="#tab-pos">活跃仓位</button></li>
                <li class="nav-item"><button class="nav-link" data-bs-toggle="tab" data-bs-target="#tab-sig">信号历史</button></li>
            </ul>
            <div class="tab-content flex-grow-1 p-2 overflow-auto">
                <div class="tab-pane fade show active" id="tab-pos"><div class="text-center text-muted mt-4">暂无持仓数据</div></div>
                <div class="tab-pane fade" id="tab-sig"><div class="text-center text-muted mt-4">等待信号捕获...</div></div>
            </div>
            <div id="logConsole">>>> 极简交易终端已启动. 等待数据同频...</div>
        </div>
        <div class="content-area">
            <div id="p-main" class="pane" style="flex: 2.5;"></div>
            <div id="p-wave" class="pane" style="flex: 1;"></div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        const debug = (m, c='#d1d4dc') => { 
            const el = document.getElementById('logConsole'); 
            if(el) { el.innerHTML += `<div style="color:${c};margin-bottom:2px">[${new Date().toLocaleTimeString()}] ${m}</div>`; el.scrollTop = el.scrollHeight; }
        };

        let charts = [], series = {}, ws = null, syncLock = false, allData = [];

        function initCharts() {
            const chartOpt = {
                layout: { background: { color: '#ffffff' }, textColor: '#333' },
                grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                timeScale: { borderColor: '#e0e3eb', timeVisible: true, secondsVisible: false, barSpacing: 8, rightOffset: 12 },
                rightPriceScale: { borderColor: '#e0e3eb' },
                handleScroll: { vertTouchDrag: false },
            };

            // Main Chart
            const ch0 = LightweightCharts.createChart(document.getElementById('p-main'), chartOpt);
            series.candle = ch0.addCandlestickSeries({ upColor: '#089981', downColor: '#f23645', borderVisible: false, wickUpColor: '#089981', wickDownColor: '#f23645' });
            series.st = ch0.addLineSeries({ lineWidth: 2, title: 'SuperTrend', priceLineVisible: false, lastValueVisible: false });
            charts.push(ch0);

            // Wave Filter Chart
            const ch1 = LightweightCharts.createChart(document.getElementById('p-wave'), chartOpt);
            series.wave = ch1.addLineSeries({ color: '#787b86', lineWidth: 2, title: 'Wave' });
            series.waveR = ch1.addHistogramSeries({ color: '#ef5350', base: 40 }); // Red pillars up from 40
            series.waveG = ch1.addHistogramSeries({ color: '#26a69a', base: -40 }); // Green pillars down from -40
            
            // Add reference lines
            [40, 0, -40].forEach(lv => {
                series.wave.createPriceLine({
                    price: lv, color: lv === 0 ? '#787b86' : '#e0e3eb', 
                    lineWidth: 1, lineStyle: lv === 0 ? 0 : 2, axisLabelVisible: true
                });
            });
            charts.push(ch1);

            // Sync
            charts.forEach((ch, idx) => {
                ch.timeScale().subscribeVisibleLogicalRangeChange(range => {
                    if (syncLock || !range) return;
                    syncLock = true;
                    charts.forEach(other => { if(other !== ch) other.timeScale().setVisibleLogicalRange(range); });
                    syncLock = false;
                });
            });

            window.onresize = () => {
                const w = document.querySelector('.content-area').offsetWidth;
                const h = document.querySelector('.content-area').offsetHeight;
                charts[0].applyOptions({ width: w, height: h * 2.5 / 3.5 });
                charts[1].applyOptions({ width: w, height: h * 1.0 / 3.5 });
            };
            window.onresize();
            debug('UI引擎装配完成. ✅', '#00ff00');
        }

        function connect() {
            const i = document.getElementById('iS').value;
            const t = document.getElementById('tS').value;
            if (ws) ws.close();
            allData = [];
            debug(`尝试建立同步链路: ${i} [${t}]...`, '#2962ff');
            
            const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
            ws = new WebSocket(`${protocol}://${location.host}/ws/chart/${i}/${t}`);
            
            ws.onmessage = (e) => {
                const res = JSON.parse(e.data);
                if (res.type === 'data') {
                    const newData = res.data;
                    if (allData.length === 0) {
                        allData = newData;
                        charts.forEach(c => c.timeScale().fitContent());
                    } else {
                        newData.forEach(n => {
                            const idx = allData.findIndex(d => d.time === n.time);
                            if (idx !== -1) allData[idx] = n;
                            else if (n.time > allData[allData.length-1].time) allData.push(n);
                        });
                    }
                    render();
                    const last = allData[allData.length-1];
                    if(last) document.getElementById('priceInfo').innerText = last.close.toFixed(2);
                    document.getElementById('statusText').innerHTML = `<i class="fas fa-circle text-success me-1" style="font-size:8px"></i>${i} 数据同频中`;
                }
            };
            ws.onerror = () => debug('WebSocket 连接异常', '#f23645');
            ws.onclose = () => debug('WebSocket 已断开', '#787b86');
        }

        function render() {
            series.candle.setData(allData.map(d => ({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close })));
            series.st.setData(allData.map(d => ({ time: d.time, value: d.st, color: d.st_dir === 1 ? '#089981' : '#f23645' })));
            
            series.wave.setData(allData.map(d => ({ time: d.time, value: d.wave })));
            series.waveR.setData(allData.map(d => ({ time: d.time, value: d.wave_r })));
            series.waveG.setData(allData.map(d => ({ time: d.time, value: d.wave_g })));
            
            // Markers on Wave line
            const markers = [];
            allData.forEach(d => {
                if (d.bu) markers.push({ time: d.time, position: 'belowBar', color: '#26a69a', shape: 'arrowUp', text: '多', size: 1 });
                if (d.be) markers.push({ time: d.time, position: 'aboveBar', color: '#ef5350', shape: 'arrowDown', text: '空', size: 1 });
            });
            series.wave.setMarkers(markers);
        }

        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            connect();
            document.getElementById('iS').onchange = connect;
            document.getElementById('tS').onchange = connect;
        });
    </script>
</body>
</html>"""
    with open(templates_dir / "index.html", "w", encoding="utf-8") as f: f.write(index_html)


if __name__ == "__main__":
    import uvicorn

    # Set start time
    ui_app.start_time = time.time()

    # Only create template if it doesn't already exist (don't overwrite custom templates)
    if not Path("templates/index.html").exists():
        create_templates()

    print("🚀 启动TW168交易UI服务器...")
    print("📱 访问地址: http://localhost:9000")
    print("📊 功能包括:")
    print("   - 实时系统状态监控")
    print("   - 手动交易信号发送")
    print("   - 信号历史记录查看")
    print("   - 活跃仓位显示")

    # Start server
    uvicorn.run(ui_app, host="0.0.0.0", port=9000, log_level="info")
