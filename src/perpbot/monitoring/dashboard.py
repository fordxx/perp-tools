from __future__ import annotations

from dataclasses import asdict
from typing import List

from fastapi import FastAPI

from perpbot.models import TradingState


def create_dashboard_app(state: TradingState) -> FastAPI:
    app = FastAPI(title="PerpBot Monitor", version="0.1.0")

    @app.get("/quotes")
    def quotes():
        return [asdict(q) for q in state.quotes.values()]

    @app.get("/positions")
    def positions():
        return [asdict(p) for p in state.open_positions.values()]

    @app.get("/arbitrage")
    def arbitrage():
        return [asdict(op) for op in state.recent_arbitrage]

    @app.get("/alerts")
    def alerts():
        return state.triggered_alerts

    @app.get("/")
    def root():
        return {
            "summary": {
                "open_positions": len(state.open_positions),
                "known_quotes": len(state.quotes),
                "recent_arbitrage": len(state.recent_arbitrage),
                "alerts": len(state.triggered_alerts),
            }
        }

    return app
