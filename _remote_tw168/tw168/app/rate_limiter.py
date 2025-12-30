"""Rate limiting for API calls to prevent hitting exchange limits."""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class RateLimiter:
    """Token bucket rate limiter."""

    max_calls: int  # Maximum calls per window
    window_seconds: float  # Time window in seconds
    _timestamps: deque = field(default_factory=deque)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def acquire(self, *, timeout: float = 5.0) -> bool:
        """
        Acquire permission to make an API call.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if acquired, False if timeout
        """
        start_time = time.time()

        async with self._lock:
            while True:
                now = time.time()

                # Remove timestamps outside the window
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()

                # Check if we can make the call
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return True

                # Check timeout
                if time.time() - start_time >= timeout:
                    return False

                # Calculate wait time
                oldest_in_window = self._timestamps[0]
                wait_time = (oldest_in_window + self.window_seconds) - now

                # Wait a bit and retry
                await asyncio.sleep(min(wait_time, 0.1))

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        now = time.time()
        cutoff = now - self.window_seconds

        # Count recent calls
        recent_calls = sum(1 for ts in self._timestamps if ts >= cutoff)

        return {
            "max_calls": self.max_calls,
            "window_seconds": self.window_seconds,
            "recent_calls": recent_calls,
            "available_calls": max(0, self.max_calls - recent_calls),
            "utilization": f"{(recent_calls / self.max_calls * 100):.1f}%",
        }


@dataclass
class SyncRateLimiter:
    """Token bucket rate limiter for sync callers."""

    max_calls: int
    window_seconds: float
    _timestamps: deque = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self, *, timeout: float = 5.0) -> bool:
        start_time = time.time()
        while True:
            with self._lock:
                now = time.time()
                cutoff = now - self.window_seconds
                while self._timestamps and self._timestamps[0] < cutoff:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return True
                oldest_in_window = self._timestamps[0]
                wait_time = (oldest_in_window + self.window_seconds) - now
            if time.time() - start_time >= timeout:
                return False
            time.sleep(min(wait_time, 0.1))

    def get_stats(self) -> dict:
        now = time.time()
        cutoff = now - self.window_seconds
        recent_calls = sum(1 for ts in self._timestamps if ts >= cutoff)
        return {
            "max_calls": self.max_calls,
            "window_seconds": self.window_seconds,
            "recent_calls": recent_calls,
            "available_calls": max(0, self.max_calls - recent_calls),
            "utilization": f"{(recent_calls / self.max_calls * 100):.1f}%",
        }


# Global rate limiters for different API endpoints
# OKX limits: ~10 requests/second for trading endpoints
_okx_trading_limiter = RateLimiter(max_calls=8, window_seconds=1.0)
_okx_market_limiter = RateLimiter(max_calls=20, window_seconds=2.0)
_okx_trading_limiter_sync = SyncRateLimiter(max_calls=8, window_seconds=1.0)
_okx_market_limiter_sync = SyncRateLimiter(max_calls=20, window_seconds=2.0)


async def acquire_okx_trading() -> bool:
    """Acquire permission for OKX trading API call."""
    return await _okx_trading_limiter.acquire(timeout=5.0)


async def acquire_okx_market() -> bool:
    """Acquire permission for OKX market data API call."""
    return await _okx_market_limiter.acquire(timeout=3.0)


def get_rate_limiter_stats() -> dict:
    """Get statistics for all rate limiters."""
    return {
        "okx_trading": _okx_trading_limiter_sync.get_stats(),
        "okx_market": _okx_market_limiter_sync.get_stats(),
    }


def acquire_okx_trading_sync() -> bool:
    """Acquire permission for OKX trading API call (sync)."""
    return _okx_trading_limiter_sync.acquire(timeout=5.0)


def acquire_okx_market_sync() -> bool:
    """Acquire permission for OKX market data API call (sync)."""
    return _okx_market_limiter_sync.acquire(timeout=3.0)
