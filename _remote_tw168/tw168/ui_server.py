from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.config import SETTINGS
from app.state import InMemoryState
from app.fill_tracker import FillTracker
from app.notify import notify_info

# Initialize components
state = InMemoryState()
fill_tracker = FillTracker()

# Create FastAPI app for UI
ui_app = FastAPI(title="TW168 Trading UI", description="Web interface for TW168 trading system")

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

class SignalRequest(BaseModel):
    instId: str
    tf: str
    side: str
    admin_key: str | None = None


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


async def _forward_manual_signal(*, inst_id: str, tf: str, side: str) -> tuple[int, dict]:
    """Forward a manual signal to the configured trading service."""
    base_url = (SETTINGS.trading_service_base_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("TRADING_SERVICE_BASE_URL is not configured")

    url = f"{base_url}/manual/signal"
    payload = {
        "instId": inst_id,
        "tf": tf,
        "side": side,
        "type": "DIV",
        "admin_key": SETTINGS.tv_webhook_secret,
    }

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
    symbols = []
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
        if not hasattr(exchange, "get_positions"):
             return {"positions": []}
        
        # Ensure connected
        if hasattr(exchange, "connect"):
             # It might be already connected by the main loop, but if this is standalone UI?
             # If running in same process (main.py imports ui?), it uses the same exchange instance.
             # If running separately, we might need to connect? 
             # The current setup seems to run UI in the SAME container/process or relies on shared memory?
             # Wait, `start_ui_server.py` likely imports `ui_app`.
             # `main.py` likely runs `uvicorn` or similar? 
             # Actually `tw168` usually runs `main.py` which might run UI?
             # Let's assume `exchange` is the active instance.
             pass

        positions = await exchange.get_positions()
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
                admin_key=request.admin_key,
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

@ui_app.get("/api/positions")
async def get_positions():
    """Get current positions"""
    # This would integrate with the actual position tracking
    # For now, return mock data
    return {"positions": []}

@ui_app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

def create_templates():
    """Create template files"""
    templates_dir = Path("templates")
    templates_dir.mkdir(exist_ok=True)

    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)

    # Create main template
    index_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🚀 TW168 交易控制面板</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        .navbar {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            box-shadow: 0 2px 20px rgba(0,0,0,0.1);
        }
        .main-container {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            margin: 20px;
            padding: 30px;
        }
        .card {
            border: none;
            border-radius: 15px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .card:hover {
            transform: translateY(-5px);
        }
        .btn-primary {
            background: linear-gradient(45deg, #667eea, #764ba2);
            border: none;
            border-radius: 25px;
            padding: 12px 30px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }
        .form-control {
            border-radius: 10px;
            border: 2px solid #e9ecef;
            transition: border-color 0.3s ease;
        }
        .form-control:focus {
            border-color: #667eea;
            box-shadow: 0 0 0 0.2rem rgba(102, 126, 234, 0.25);
        }
        .status-card {
            background: linear-gradient(45deg, #28a745, #20c997);
            color: white;
        }
        .alert-custom {
            border-radius: 10px;
            border: none;
        }
        .price-display {
            font-size: 2rem;
            font-weight: bold;
            color: #28a745;
        }
        .trading-signal {
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { transform: scale(1); }
            50% { transform: scale(1.05); }
            100% { transform: scale(1); }
        }
        .symbol-badge {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 0.8rem;
            margin: 2px;
            display: inline-block;
        }
        .signal-history {
            max-height: 400px;
            overflow-y: auto;
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }
        .status-online { background-color: #28a745; }
        .status-offline { background-color: #dc3545; }
        .status-paper { background-color: #ffc107; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-light">
        <div class="container">
            <a class="navbar-brand fw-bold" href="#">
                <i class="fas fa-rocket"></i> TW168 交易控制面板
            </a>
            <div class="d-flex align-items-center">
                <span class="badge bg-success me-2" id="exchangeBadge">GRVT</span>
                <span class="badge bg-info me-2" id="tradingStatus">实盘</span>
                <span class="status-indicator status-online" id="systemStatus"></span>
                <span class="text-muted small" id="uptime">00:00:00</span>
            </div>
        </div>
    </nav>

    <div class="container-fluid">
        <div class="main-container">
            <!-- 仓位管理 -->
            <div class="row mb-4">
                <div class="col-12">
                     <div class="card">
                         <div class="card-header bg-success text-white d-flex justify-content-between align-items-center">
                             <h5 class="mb-0"><i class="fas fa-list"></i> 当前仓位</h5>
                             <button class="btn btn-sm btn-light" onclick="refreshPositions()">
                                 <i class="fas fa-sync-alt"></i> 刷新仓位
                             </button>
                         </div>
                         <div class="card-body">
                             <div class="form-check mb-2">
                                 <input class="form-check-input" type="checkbox" value="" id="openOrdersOnlyThis" checked>
                                 <label class="form-check-label" for="openOrdersOnlyThis">只看当前交易对（使用右侧“交易对”输入框）</label>
                             </div>
                             <div class="table-responsive">
                                 <table class="table table-hover">
                                     <thead>
                                         <tr>
                                             <th>交易对</th>
                                             <th>方向</th>
                                             <th>数量</th>
                                             <th>均价</th>
                                             <th>未结盈亏</th>
                                             <th>操作</th>
                                         </tr>
                                     </thead>
                                     <tbody id="positionsTableBody">
                                         <tr><td colspan="6" class="text-center text-muted">点击刷新查看仓位</td></tr>
                                     </tbody>
                                 </table>
                             </div>
                         </div>
                     </div>
                </div>
            </div>
            
            <!-- 当前挂单 -->
            <div class="row mb-4">
                <div class="col-12">
                     <div class="card">
                         <div class="card-header bg-info text-white d-flex justify-content-between align-items-center">
                             <h5 class="mb-0"><i class="fas fa-receipt"></i> 当前挂单</h5>
                             <button class="btn btn-sm btn-light" onclick="refreshOpenOrders()">
                                 <i class="fas fa-sync-alt"></i> 刷新挂单
                             </button>
                         </div>
                         <div class="card-body">
                             <div class="table-responsive">
                                 <table class="table table-hover">
                                     <thead>
                                         <tr>
                                             <th>交易对</th>
                                             <th>方向</th>
                                             <th>价格</th>
                                             <th>数量</th>
                                             <th>类型</th>
                                             <th>状态</th>
                                         </tr>
                                     </thead>
                                     <tbody id="openOrdersTableBody">
                                         <tr><td colspan="6" class="text-center text-muted">点击刷新查看挂单</td></tr>
                                     </tbody>
                                 </table>
                             </div>
                         </div>
                     </div>
                </div>
            </div>

            <!-- 系统状态 (Original Row) -->
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="card status-card text-white">
                        <div class="card-body text-center">
                            <i class="fas fa-chart-line fa-2x mb-2"></i>
                            <h5>系统状态</h5>
                            <p class="mb-0" id="systemStatusText">运行正常</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-clock fa-2x mb-2 text-warning"></i>
                            <h5>最后信号</h5>
                            <p class="mb-0" id="lastSignalTime">-</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-signal fa-2x mb-2 text-info"></i>
                            <h5>信号计数</h5>
                            <p class="mb-0" id="signalCount">0</p>
                        </div>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="card">
                        <div class="card-body text-center">
                            <i class="fas fa-exchange-alt fa-2x mb-2 text-success"></i>
                            <h5>活跃仓位</h5>
                            <p class="mb-0" id="activePositions">0</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 手动信号发送 -->
            <div class="row">
                <div class="col-lg-6">
                    <div class="card">
                        <div class="card-header bg-primary text-white">
                            <h5 class="mb-0"><i class="fas fa-hand-paper"></i> 手动交易信号</h5>
                        </div>
                        <div class="card-body">
                            <form id="signalForm">
                                <div class="row">
                                    <div class="col-md-6 mb-3">
                                        <label class="form-label fw-bold">交易对</label>
                                        <div class="d-flex gap-2 align-items-center">
                                            <input class="form-control" list="instIdList" id="instId" name="instId" placeholder="选择或输入交易对" required>
                                            <button type="button" class="btn btn-outline-secondary btn-sm" id="refreshSymbolsBtn">刷新GRVT交易对</button>
                                        </div>
                                        <datalist id="instIdList">
                                            {% for symbol in symbols %}
                                            <option value="{{ symbol }}">
                                            {% endfor %}
                                        </datalist>
                                    </div>
                                    <div class="col-md-3 mb-3">
                                        <label class="form-label fw-bold">时间周期</label>
                                        <select class="form-select" id="tf" name="tf" required>
                                            <option value="1m">1分钟</option>
                                            <option value="5m">5分钟</option>
                                            <option value="15m">15分钟</option>
                                            <option value="30m">30分钟</option>
                                            <option value="1h" selected>1小时</option>
                                            <option value="4h">4小时</option>
                                            <option value="1d">1天</option>
                                        </select>
                                    </div>
                                    <div class="col-md-3 mb-3">
                                        <label class="form-label fw-bold">方向</label>
                                        <select class="form-select" id="side" name="side" required>
                                            <option value="">选择方向</option>
                                            <option value="long">📈 做多</option>
                                            <option value="short">📉 做空</option>
                                        </select>
                                    </div>
                                </div>
                                <button type="submit" class="btn btn-primary btn-lg w-100" id="submitBtn">
                                    <i class="fas fa-paper-plane"></i> 发送交易信号
                                </button>
                            </form>
                        </div>
                    </div>
                </div>

                <!-- 信号历史 -->
                <div class="col-lg-6">
                    <div class="card">
                        <div class="card-header bg-secondary text-white">
                            <h5 class="mb-0"><i class="fas fa-history"></i> 信号历史</h5>
                        </div>
                        <div class="card-body">
                            <div class="signal-history" id="signalHistory">
                                <div class="text-muted text-center" id="noHistory">暂无信号历史</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 结果显示区域 -->
            <div class="row mt-4">
                <div class="col-12">
                    <div id="result" class="alert alert-custom" style="display: none;"></div>
                </div>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        // 页面加载时初始化
        document.addEventListener('DOMContentLoaded', function() {
            updateSystemStatus();
            loadSignalHistory();
            setInterval(updateSystemStatus, 5000); // 每5秒更新状态
        });

        // 更新系统状态
        async function updateSystemStatus() {
            try {
                const response = await fetch('/api/system/status');
                const data = await response.json();

                document.getElementById('exchangeBadge').textContent = data.exchange.toUpperCase();
                document.getElementById('tradingStatus').textContent = data.trading_enabled ? '实盘' : '纸上';
                document.getElementById('tradingStatus').className = data.trading_enabled ? 'badge bg-danger' : 'badge bg-warning';
                document.getElementById('signalCount').textContent = data.total_signals;
                document.getElementById('activePositions').textContent = data.active_positions;
                document.getElementById('lastSignalTime').textContent = data.last_signal ?
                    new Date(data.last_signal).toLocaleString() : '-';

                // 更新运行时间
                const uptime = data.uptime;
                const hours = Math.floor(uptime / 3600);
                const minutes = Math.floor((uptime % 3600) / 60);
                const seconds = uptime % 60;
                document.getElementById('uptime').textContent =
                    `${hours.toString().padStart(2,'0')}:${minutes.toString().padStart(2,'0')}:${seconds.toString().padStart(2,'0')}`;

            } catch (error) {
                console.error('获取系统状态失败:', error);
            }
        }

        // 加载信号历史
        async function loadSignalHistory() {
            try {
                const response = await fetch('/api/signals/history?limit=20');
                const data = await response.json();

                const historyDiv = document.getElementById('signalHistory');
                if (data.history.length === 0) {
                    historyDiv.innerHTML = '<div class="text-muted text-center">暂无信号历史</div>';
                    return;
                }

                let html = '';
                data.history.forEach(signal => {
                    const time = new Date(signal.timestamp).toLocaleString();
                    const statusClass = signal.status === 'success' ? 'text-success' : 'text-danger';
                    const statusIcon = signal.status === 'success' ? '✅' : '❌';
                    const result = signal.result;

                    html += `
                        <div class="mb-3 p-3 bg-light rounded">
                            <div class="d-flex justify-content-between align-items-start">
                                <div>
                                    <small class="text-muted">${time}</small><br>
                                    <strong>${signal.signal.instId}</strong>
                                    <span class="badge bg-primary">${signal.signal.side}</span>
                                    <span class="badge bg-secondary">${signal.signal.tf}</span>
                                </div>
                                <div class="${statusClass}">
                                    ${statusIcon} ${signal.status}
                                </div>
                            </div>
                            ${result.ok ? `
                                <div class="mt-2 small">
                                    <span class="text-muted">入场:</span> ${result.entry?.toFixed(6) || 'N/A'} |
                                    <span class="text-muted">止损:</span> ${result.sl?.toFixed(6) || 'N/A'} |
                                    <span class="text-muted">数量:</span> ${result.order_sz || 'N/A'}
                                </div>
                            ` : `
                                <div class="mt-2 small text-danger">
                                    错误: ${result.error || '未知错误'}
                                </div>
                            `}
                        </div>
                    `;
                });

                historyDiv.innerHTML = html;

            } catch (error) {
                console.error('加载信号历史失败:', error);
            }
        }

        // 信号表单提交
        document.getElementById('signalForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const submitBtn = document.getElementById('submitBtn');
            const resultDiv = document.getElementById('result');

            const formData = new FormData(this);
            const data = {
                instId: formData.get('instId'),
                tf: formData.get('tf'),
                side: formData.get('side')
            };

            if (!data.instId || !data.tf || !data.side) {
                showResult('请填写所有必填字段', 'danger');
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>发送中...';
            resultDiv.style.display = 'none';

            try {
                const response = await fetch('/signals/send/form', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok && result.ok) {
                    showResult(`✅ 信号发送成功！\\n\\n交易对: ${data.instId}\\n方向: ${data.side}\\n入场价: ${result.entry?.toFixed(6)}\\n止损价: ${result.sl?.toFixed(6)}\\n数量: ${result.order_sz}`, 'success');
                    updateSystemStatus();
                    loadSignalHistory();
                } else {
                    const errorMsg = result.error || result.detail || '未知错误';
                    showResult(`❌ 发送失败: ${errorMsg}`, 'danger');
                }

            } catch (error) {
                showResult(`❌ 网络错误: ${error.message}`, 'danger');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> 发送交易信号';
            }
        });

        function showResult(message, type) {
            const resultDiv = document.getElementById('result');
            resultDiv.className = `alert alert-${type} alert-custom`;
            resultDiv.innerHTML = `<pre class="mb-0">${message}</pre>`;
            resultDiv.style.display = 'block';

            // 3秒后自动隐藏成功消息
            if (type === 'success') {
                setTimeout(() => {
                    resultDiv.style.display = 'none';
                }, 3000);
            }
        }

        async function refreshSymbols() {
            const btn = document.getElementById('refreshSymbolsBtn');
            const list = document.getElementById('instIdList');
            if (!btn || !list) return;
            const prev = btn.textContent;
            btn.disabled = true;
            btn.textContent = '拉取中...';
            try {
                const resp = await fetch('/api/symbols/grvt');
                const data = await resp.json();
                if (!resp.ok || !data || data.ok === false) {
                    throw new Error(data?.error || data?.detail || '拉取失败');
                }
                const instIds = Array.isArray(data.instIds) ? data.instIds : [];
                if (!instIds.length) {
                    throw new Error('远程未返回交易对列表');
                }
                const existing = new Set(Array.from(list.querySelectorAll('option')).map(o => o.value));
                let added = 0;
                for (const instId of instIds) {
                    if (!instId || existing.has(instId)) continue;
                    const opt = document.createElement('option');
                    opt.value = instId;
                    list.appendChild(opt);
                    existing.add(instId);
                    added++;
                }
                showResult(`✅ 已拉取 GRVT 交易对：${instIds.length} 个（新增 ${added}）`, 'success');
            } catch (e) {
                showResult(`❌ 刷新交易对失败: ${e.message}`, 'danger');
            } finally {
                btn.disabled = false;
                btn.textContent = prev;
            }
        }

        document.getElementById('refreshSymbolsBtn')?.addEventListener('click', refreshSymbols);

        // 仓位管理功能
        async function refreshPositions() {
            const tbody = document.getElementById('positionsTableBody');
            tbody.innerHTML = '<tr><td colspan="6" class="text-center"><div class="spinner-border spinner-border-sm text-primary"></div> 加载中...</td></tr>';
            
            try {
                const response = await fetch('/api/positions');
                const data = await response.json();
                
                if (data.error) {
                    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">加载失败: ${data.error}</td></tr>`;
                    return;
                }
                
                if (!data.positions || data.positions.length === 0) {
                     tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">当前无持仓</td></tr>';
                     document.getElementById('activePositions').textContent = '0';
                     return;
                }

                document.getElementById('activePositions').textContent = data.positions.length;
                
                let html = '';
                data.positions.forEach(p => {
                    const pnlClass = parseFloat(p.uPnl) >= 0 ? 'text-success' : 'text-danger';
                    const sideBadge = p.posSide === 'long' || parseFloat(p.pos) > 0 ? 
                        '<span class="badge bg-success">多</span>' : 
                        '<span class="badge bg-danger">空</span>';
                    
                    html += `
                        <tr>
                            <td><strong>${p.instId}</strong></td>
                            <td>${sideBadge}</td>
                            <td>${p.pos}</td>
                            <td>${parseFloat(p.avgPx).toFixed(4)}</td>
                            <td class="${pnlClass}">${parseFloat(p.uPnl).toFixed(2)}</td>
                            <td>
                                <button class="btn btn-sm btn-outline-danger" onclick="closePosition('${p.instId}', '${p.posSide}')">
                                    平仓
                                </button>
                            </td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;

            } catch (error) {
                console.error('刷新仓位失败:', error);
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">网络错误</td></tr>`;
            }
        }

        async function refreshOpenOrders() {
            const tbody = document.getElementById('openOrdersTableBody');
            tbody.innerHTML = '<tr><td colspan="6" class="text-center"><div class="spinner-border spinner-border-sm text-primary"></div> 加载中...</td></tr>';
            try {
                const instInput = document.getElementById('instId');
                const onlyThis = document.getElementById('openOrdersOnlyThis');
                const instId = instInput ? instInput.value.trim() : '';
                const useFilter = !!(onlyThis && onlyThis.checked && instId);
                const url = useFilter ? (`/api/open_orders?instId=${encodeURIComponent(instId)}`) : '/api/open_orders';
                const resp = await fetch(url);
                const data = await resp.json();
                if (!data || data.ok === false) {
                    tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">加载失败: ${data?.error || data?.detail || '未知错误'}</td></tr>`;
                    return;
                }
                const orders = Array.isArray(data.orders) ? data.orders : [];
                if (!orders.length) {
                    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">当前无挂单</td></tr>';
                    return;
                }
                let html = '';
                orders.forEach(o => {
                    const isReduce = !!o.reduce_only;
                    const typeBadge = isReduce ? '<span class="badge bg-secondary">保护单</span>' : '<span class="badge bg-primary">入场单</span>';
                    const sideBadge = (o.side === 'buy') ? '<span class="badge bg-success">买</span>' : (o.side === 'sell') ? '<span class="badge bg-danger">卖</span>' : '<span class="badge bg-dark">?</span>';
                    const priceVal = (o.limit_price ?? '').toString();
                    const canEdit = !isReduce;
                    const priceInput = canEdit
                        ? `<input class="form-control form-control-sm" style="max-width:120px" value="${priceVal}" data-order-price="${o.order_id || ''}">`
                        : `${priceVal}`;
                    const sizeVal = (o.size ?? '').toString();
                    const sizeInput = canEdit
                        ? `<input class="form-control form-control-sm" style="max-width:120px" value="${sizeVal}" data-order-size="${o.order_id || ''}">`
                        : `${sizeVal}`;
                    const cancelBtn = `<button class="btn btn-sm btn-outline-danger" onclick="cancelOpenOrder('${o.instId || ''}','${o.order_id || ''}')">取消</button>`;
                    const replaceBtn = canEdit
                        ? `<button class="btn btn-sm btn-outline-primary ms-1" onclick="replaceOpenOrder('${o.instId || ''}','${o.order_id || ''}')">改价</button>`
                        : '';
                    html += `
                        <tr>
                            <td><strong>${o.instId || o.instrument || ''}</strong></td>
                            <td>${sideBadge}</td>
                            <td>${priceInput}</td>
                            <td>${sizeInput}</td>
                            <td>${typeBadge}</td>
                            <td>${o.status || ''}<div class="mt-1">${cancelBtn}${replaceBtn}</div></td>
                        </tr>
                    `;
                });
                tbody.innerHTML = html;
            } catch (e) {
                tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">网络错误</td></tr>`;
            }
        }

        async function cancelOpenOrder(instId, orderId) {
            if (!instId || !orderId) { alert('缺少订单信息'); return; }
            if (!confirm(`确定取消挂单？\\n${instId}\\n${orderId}`)) return;
            try {
                const resp = await fetch('/api/open_orders/cancel', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({instId: instId, order_id: orderId})
                });
                const data = await resp.json();
                if (!resp.ok || !data || data.ok === false) {
                    alert('取消失败: ' + (data?.detail || data?.error || '未知错误'));
                    return;
                }
                refreshOpenOrders();
            } catch (e) {
                alert('网络错误');
            }
        }

        async function replaceOpenOrder(instId, orderId) {
            if (!instId || !orderId) { alert('缺少订单信息'); return; }
            const input = document.querySelector(`[data-order-price="${CSS.escape(orderId)}"]`);
            const newPrice = input ? input.value.trim() : '';
            const sizeInput = document.querySelector(`[data-order-size="${CSS.escape(orderId)}"]`);
            const newSize = sizeInput ? sizeInput.value.trim() : '';
            if (!newPrice) { alert('请输入新价格'); return; }
            if (!newSize) { alert('请输入新数量'); return; }
            if (!confirm(`确定改价/改数量？\\n${instId}\\n${orderId}\\n新价: ${newPrice}\\n新数量: ${newSize}`)) return;
            try {
                const resp = await fetch('/api/open_orders/replace', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({instId: instId, order_id: orderId, new_price: newPrice, new_size: newSize})
                });
                const data = await resp.json();
                if (!resp.ok || !data || data.ok === false) {
                    alert('改价失败: ' + (data?.detail || data?.error || '未知错误'));
                    return;
                }
                refreshOpenOrders();
            } catch (e) {
                alert('网络错误');
            }
        }
        
        async function closePosition(instId, posSide) {
            if (!confirm(`确定要平仓 ${instId} 吗？`)) return;

            try {
                const response = await fetch('/api/positions/close', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        instId: instId,
                        posSide: posSide,
                    })
                });
                
                const result = await response.json();
                if (result.ok) {
                    alert('平仓指令已发送');
                    refreshPositions();
                } else {
                    alert('平仓失败: ' + (result.error || '未知错误'));
                }
            } catch (e) {
                alert('网络请求失败');
            }
        }
    </script>
</body>
</html>"""

    with open("templates/index.html", "w", encoding="utf-8") as f:
        f.write(index_html)

    # Create static CSS file
    css_content = """/* Additional custom styles */
.signal-entry {
    transition: all 0.3s ease;
}

.signal-entry:hover {
    background-color: rgba(0,0,0,0.05) !important;
}

.status-indicator {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.5; }
    100% { opacity: 1; }
}
"""

    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    with open("static/style.css", "w", encoding="utf-8") as f:
        f.write(css_content)

if __name__ == "__main__":
    import uvicorn

    # Set start time
    ui_app.start_time = time.time()

    # Create templates
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
