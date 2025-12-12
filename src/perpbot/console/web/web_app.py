from fastapi import FastAPI

from .web_router import create_console_router
from .websocket_stream import create_websocket_router


def create_web_app(health_monitor, console_state):
    app = FastAPI(title="PerpBot Web Console V2")
    app.include_router(create_console_router(health_monitor, console_state))
    app.include_router(create_websocket_router(health_monitor, console_state))
    return app
