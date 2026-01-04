from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Tuple

import httpx
from fastapi import FastAPI
from pydantic import BaseModel


class ManualSignalRequest(BaseModel):
    instId: str
    tf: str = "1h"
    side: str
    type: str = "DIV"
    admin_key: str


def _base_url(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip().rstrip("/")


LIGHTER_BACKEND_URL = _base_url("LIGHTER_BACKEND_URL", "http://tv-okx:8000")
GRVT_BACKEND_URL = _base_url("GRVT_BACKEND_URL", "http://tv-grvt:8000")
MIRROR_PRIMARY = (os.getenv("MIRROR_PRIMARY", "lighter") or "lighter").strip().lower()
MIRROR_TIMEOUT_SECONDS = float(os.getenv("MIRROR_TIMEOUT_SECONDS", "30") or "30")


app = FastAPI(title="TW168 Router", description="Fan-out manual signals to multiple trading backends")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "ts": int(time.time())}


async def _post_manual_signal(client: httpx.AsyncClient, *, base_url: str, payload: dict) -> dict:
    url = f"{base_url}/manual/signal"
    try:
        resp = await client.post(url, json=payload)
    except Exception as e:
        return {"status": 0, "ok": False, "error": str(e), "body": None}

    try:
        body = resp.json()
    except Exception:
        body = {"detail": resp.text}

    ok = bool(body.get("ok")) if isinstance(body, dict) else False
    return {"status": resp.status_code, "ok": ok, "error": None, "body": body}


def _pick_primary(results: dict[str, dict]) -> str:
    preferred = MIRROR_PRIMARY if MIRROR_PRIMARY in results else next(iter(results.keys()))
    ordered = [preferred] + [k for k in results.keys() if k != preferred]
    for key in ordered:
        if results.get(key, {}).get("ok"):
            return key
    return preferred


@app.post("/manual/signal")
async def manual_signal(req: ManualSignalRequest) -> dict:
    payload = req.model_dump()

    async with httpx.AsyncClient(timeout=MIRROR_TIMEOUT_SECONDS) as client:
        # Only send to Lighter (OKX compatible) backend to reduce load
        lighter_res = await _post_manual_signal(client, base_url=LIGHTER_BACKEND_URL, payload=payload)
        
        # GRVT disabled
        grvt_res = {"status": 0, "ok": False, "error": "Disabled to reduce load", "body": {}}
        # grvt_task = _post_manual_signal(client, base_url=GRVT_BACKEND_URL, payload=payload)
        # lighter_res, grvt_res = await asyncio.gather(lighter_task, grvt_task)

    results = {"lighter": lighter_res, "grvt": grvt_res}
    any_ok = any(r.get("ok") for r in results.values())
    primary = _pick_primary(results)

    primary_body = results.get(primary, {}).get("body")
    merged: Dict[str, Any] = primary_body.copy() if isinstance(primary_body, dict) else {}
    merged["ok"] = any_ok
    merged["primary_exchange"] = primary
    merged["mirrors"] = results
    return merged

