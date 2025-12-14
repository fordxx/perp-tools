from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    min_delay_sec: float = 0.25
    max_delay_sec: float = 2.0
    jitter_sec: float = 0.25


def _sleep_with_backoff(
    attempt: int,
    *,
    min_delay_sec: float,
    max_delay_sec: float,
    jitter_sec: float,
    override_delay_sec: Optional[float] = None,
) -> float:
    if override_delay_sec is not None:
        delay = max(0.0, min(float(override_delay_sec), max_delay_sec))
    else:
        base = min_delay_sec * (2 ** max(0, attempt - 1))
        delay = min(max_delay_sec, base) + random.uniform(0.0, max(0.0, jitter_sec))
    return delay


def retry_call(
    fn: Callable[[], T],
    *,
    config: RetryConfig,
    is_retryable: Callable[[Exception], bool],
    label: str = "operation",
    log: Optional[logging.Logger] = None,
    delay_override: Optional[Callable[[Exception], Optional[float]]] = None,
) -> T:
    """Retry `fn` with exponential backoff + jitter.

    Intentionally does not swallow errors: if attempts are exhausted, re-raises the last exception.
    """
    log = log or logger
    last_exc: Optional[Exception] = None

    for attempt in range(1, max(1, int(config.max_attempts)) + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            retryable = is_retryable(exc)
            if (not retryable) or attempt >= config.max_attempts:
                raise

            override = delay_override(exc) if delay_override else None
            delay = _sleep_with_backoff(
                attempt,
                min_delay_sec=config.min_delay_sec,
                max_delay_sec=config.max_delay_sec,
                jitter_sec=config.jitter_sec,
                override_delay_sec=override,
            )
            log.warning(
                "%s failed (attempt %d/%d), retrying in %.2fs: %s",
                label,
                attempt,
                config.max_attempts,
                delay,
                exc,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc
