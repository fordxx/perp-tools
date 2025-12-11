from __future__ import annotations

from typing import Callable, List, Tuple

from .event_types import Event, EventKind


def logging_subscriber(event: Event) -> None:
    print(f"[EVENT] {event.timestamp:.3f} {event.kind.value} {event.source} {event.payload}")


def metrics_subscriber(event: Event) -> None:
    # Placeholder for future metrics aggregation.
    pass


def make_default_subscribers() -> List[Tuple[EventKind, Callable[[Event], None]]]:
    return [
        (EventKind.EXECUTION_FAILED, logging_subscriber),
        (EventKind.RISK_REJECT, logging_subscriber),
        (EventKind.CAPITAL_REJECT, logging_subscriber),
        (EventKind.HEALTH_SNAPSHOT_UPDATE, logging_subscriber),
    ]
