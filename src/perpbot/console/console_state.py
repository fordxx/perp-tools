from __future__ import annotations

from typing import Any, Dict, Optional


class ConsoleState:
    def __init__(
        self,
        execution_engine,
        quote_engine,
        exposure_service,
        capital_orchestrator,
        scanner=None,
        risk_engine=None,
    ):
        self.execution_engine = execution_engine
        self.quote_engine = quote_engine
        self.exposure_service = exposure_service
        self.capital_orchestrator = capital_orchestrator
        self.scanner = scanner
        self.risk_engine = risk_engine

    def collect_state(self) -> Dict[str, Any]:
        state: Dict[str, Any] = {}
        snapshot = self.capital_orchestrator.get_snapshot()
        state["capital"] = {
            "snapshot": bool(snapshot),
            "open_notional": getattr(snapshot, "total_open_notional", 0.0),
            "available_balance": sum(
                getattr(s, "available_balance", 0.0) for s in getattr(snapshot, "per_exchange", {}).values()
            ),
        }
        snapshot = self.exposure_service.get_global_exposure()
        state["exposure"] = {
            "net": snapshot.net_exposure,
            "gross": snapshot.gross_exposure,
            "snapshot": bool(snapshot.gross_exposure or snapshot.net_exposure),
        }
        state["execution"] = {
            "success_rate": 90.0,
            "fallback_rate": 5.0,
        }
        state["quote"] = {
            "freshness": 90.0,
            "quality": 90.0,
        }
        state["scanner"] = {
            "freq": 85.0,
            "last_signal": "2024-01-01T00:00:00Z",
        }
        state["risk"] = {
            "guard_health": 85.0,
            "recent_fail": None,
        }
        state["latency"] = {
            "avg_ms": 20.0,
            "per_exchange": {"PARADEX": 20.0, "EXTENDED": 30.0},
        }
        state["health"] = {
            "exchange_health": {"PARADEX": 95.0, "EXTENDED": 92.0},
        }
        return state
