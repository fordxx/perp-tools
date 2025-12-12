from dataclasses import dataclass

# Define constants for quality labels to ensure consistency
QUALITY_GOOD = "GOOD"
QUALITY_WARN = "WARN"
QUALITY_BAD = "BAD"


@dataclass
class QuoteQuality:
    """
    Represents the scored quality of a quote from a specific exchange.
    """

    exchange: str
    score: float  # A score from 0 to 100, where 100 is best.
    label: str  # GOOD, WARN, or BAD


class QuoteQualityScorer:
    """
    Scores the quality of a quote based on latency, freshness, and price variance.
    """

    # --- Thresholds for scoring ---
    LATENCY_WARN_MS = 50
    LATENCY_BAD_MS = 200

    FRESHNESS_WARN_MS = 500
    FRESHNESS_BAD_MS = 1500

    VARIANCE_WARN_RATIO = 0.001  # 0.1%
    VARIANCE_BAD_RATIO = 0.005  # 0.5%

    # --- Score boundaries for labels ---
    SCORE_GOOD_THRESHOLD = 80
    SCORE_WARN_THRESHOLD = 50

    @staticmethod
    def score(
        exchange: str, latency_ms: float, freshness_ms: float, variance_ratio: float
    ) -> QuoteQuality:
        """
        Calculates a quality score and assigns a label (GOOD, WARN, BAD).
        The score starts at 100 and points are deducted based on metric thresholds.
        """
        score = 100.0

        if latency_ms > QuoteQualityScorer.LATENCY_BAD_MS:
            score -= 40
        elif latency_ms > QuoteQualityScorer.LATENCY_WARN_MS:
            score -= 15

        if freshness_ms > QuoteQualityScorer.FRESHNESS_BAD_MS:
            score -= 40
        elif freshness_ms > QuoteQualityScorer.FRESHNESS_WARN_MS:
            score -= 15

        if variance_ratio > QuoteQualityScorer.VARIANCE_BAD_RATIO:
            score -= 40
        elif variance_ratio > QuoteQualityScorer.VARIANCE_WARN_RATIO:
            score -= 15

        if score >= QuoteQualityScorer.SCORE_GOOD_THRESHOLD:
            label = QUALITY_GOOD
        elif score >= QuoteQualityScorer.SCORE_WARN_THRESHOLD:
            label = QUALITY_WARN
        else:
            label = QUALITY_BAD

        return QuoteQuality(exchange=exchange, score=max(0, score), label=label)