from __future__ import annotations

from dataclasses import asdict
from typing import Dict

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse


from ..console_state import ConsoleState
from ...health.health_monitor import HealthMonitor


HEALTH_METRIC_HEADER = "# HELP perpbot_{} {}\n# TYPE perpbot_{} gauge"


def _format_metrics(value_map: Dict[str, float], prefix: str) -> str:
    lines = []
    for key, value in value_map.items():
        lines.append(f"perpbot_{prefix}{{exchange=\"{key}\"}} {value}")
    return "\n".join(lines)


def create_console_router(health_monitor: HealthMonitor, console_state: ConsoleState) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def get_health_snapshot():
        snapshot = health_monitor.get_latest_snapshot()
        if snapshot is None:
            return {"message": "Health snapshot not ready"}
        return asdict(snapshot)

    @router.get("/state")
    def get_console_state():
        return console_state.collect_state()

    @router.get("/metrics")
    def get_metrics():
        snapshot = health_monitor.get_latest_snapshot()
        state = console_state.collect_state()
        lines = [
            HEALTH_METRIC_HEADER.format("health_score", "Overall health score", "health_score"),
            f"perpbot_health_score {snapshot.overall_score if snapshot else 0.0}",
            "# HELP perpbot_health_capital Capital health score\n# TYPE perpbot_health_capital gauge",
        ]
        if snapshot:
            lines.append(f"perpbot_health_capital {snapshot.capital_health}")
            lines.append(f"perpbot_health_execution {snapshot.execution_health}")
            lines.append(f"perpbot_health_exposure {snapshot.exposure_health}")
            lines.append(f"perpbot_health_risk {snapshot.risk_health}")
        if "capital" in state and state["capital"]:
            lines.append("# HELP perpbot_open_notional Open notional amount\n# TYPE perpbot_open_notional gauge")
            lines.append(f"perpbot_open_notional {state['capital'].get('open_notional', 0.0)}")
        latency = state.get("latency", {}).get("per_exchange", {})
        if latency:
            lines.append("# HELP perpbot_latency_ms Exchange latency\n# TYPE perpbot_latency_ms gauge")
            for exchange, value in latency.items():
                lines.append(f"perpbot_latency_ms{{exchange=\"{exchange}\"}} {value}")
        return PlainTextResponse("\n".join(lines))

    return router
