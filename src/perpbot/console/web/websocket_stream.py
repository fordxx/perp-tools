from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..console_state import ConsoleState
from ...health.health_monitor import HealthMonitor


def create_websocket_router(health_monitor: HealthMonitor, console_state: ConsoleState) -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/stream")
    async def stream(websocket: WebSocket):
        await websocket.accept()
        try:
            while True:
                snapshot = health_monitor.get_latest_snapshot()
                state = console_state.collect_state()
                payload = {
                    "health_snapshot": asdict(snapshot) if snapshot else None,
                    "console_state": state,
                }
                await websocket.send_text(json.dumps(payload))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            await websocket.close()
        except Exception:
            await websocket.close()
    
    return router
