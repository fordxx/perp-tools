"""
perpbot.connections - Connection management module

Unified exchange connection management with:
- Market data (readonly) and trading (read-write) separation
- Heartbeat, reconnection, rate limiting, and circuit breaker
- Health monitoring and KILL SWITCH support
"""

from perpbot.connections.base_connection import (
    BaseConnection,
    ConnectionConfig,
    ConnectionState,
    RateLimiter,
)
from perpbot.connections.exchange_connection_manager import (
    ExchangeConnectionManager,
    MockConnection,
)
from perpbot.connections.health_checker import (
    ConnectionRegistry,
    HealthChecker,
)

__all__ = [
    "BaseConnection",
    "ConnectionConfig",
    "ConnectionState",
    "RateLimiter",
    "ExchangeConnectionManager",
    "MockConnection",
    "ConnectionRegistry",
    "HealthChecker",
]
