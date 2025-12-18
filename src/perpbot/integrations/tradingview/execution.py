from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Optional

from perpbot.models import Order, OrderRequest


logger = logging.getLogger(__name__)


def resolve_symbol_for_exchange(
    *,
    exchange: str,
    canonical_symbol: str,
    overrides: dict[str, dict[str, str]],
) -> str:
    ex_overrides = overrides.get(exchange.lower(), {})
    # Canonical symbol is BASE/QUOTE uppercase.
    key = canonical_symbol.strip().upper()
    # Override mapping is stored uppercase; return as-is.
    return ex_overrides.get(key, canonical_symbol)


def resolve_size_for_exchange(
    *,
    exchange: str,
    default_size: float,
    per_exchange: dict[str, float],
) -> float:
    return float(per_exchange.get(exchange.lower(), default_size))


def execute_market(
    *,
    exchange_client: Any,
    exchange_name: str,
    canonical_symbol: str,
    side: str,
    size: float,
    symbol_overrides: dict[str, dict[str, str]],
) -> Order:
    symbol = resolve_symbol_for_exchange(
        exchange=exchange_name,
        canonical_symbol=canonical_symbol,
        overrides=symbol_overrides,
    )
    order_req = OrderRequest(symbol=symbol, side=side, size=float(size), limit_price=None)
    order = exchange_client.place_open_order(order_req)
    logger.info(
        "tv168 order placed exchange=%s symbol=%s canonical=%s side=%s size=%s order=%s",
        exchange_name,
        symbol,
        canonical_symbol,
        side,
        size,
        asdict(order),
    )
    return order
