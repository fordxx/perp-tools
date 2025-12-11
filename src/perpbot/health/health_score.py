from __future__ import annotations

from .health_snapshot import HealthSnapshot


class HealthScoreCalculator:
    """Simple weighted calculator to keep overall score within [0, 100]."""

    @staticmethod
    def compute_overall_score(
        capital_health: float,
        exposure_health: float,
        execution_health: float,
        quote_health: float,
        scanner_health: float,
        risk_health: float,
        latency_health: float,
    ) -> float:
        weights = {
            "capital": 0.15,
            "exposure": 0.15,
            "execution": 0.15,
            "quote": 0.15,
            "scanner": 0.15,
            "risk": 0.15,
            "latency": 0.10,
        }
        score = (
            weights["capital"] * capital_health
            + weights["exposure"] * exposure_health
            + weights["execution"] * execution_health
            + weights["quote"] * quote_health
            + weights["scanner"] * scanner_health
            + weights["risk"] * risk_health
            + weights["latency"] * latency_health
        )
        return max(0.0, min(100.0, score))
