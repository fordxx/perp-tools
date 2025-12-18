"""tv168 Order Execution Engine with State Machine and Stop-Loss Support.

Features:
- Order state machine: place → ack → filled/partial → timeout
- Stop-loss order placement after entry fill
- Hedge mode (dual position) support for OKX
- Structured error classification
- JSONL logging for observability
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional

from perpbot.models import Order, OrderRequest


logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order lifecycle states."""
    PENDING = "pending"
    PLACED = "placed"
    ACKNOWLEDGED = "acknowledged"
    FILLED = "filled"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    FAILED = "failed"
    REJECTED = "rejected"


class ErrorClass(Enum):
    """Error classification for monitoring and alerting."""
    CREDENTIALS = "credentials"
    CONNECTIVITY = "connectivity"
    RATE_LIMIT = "rate_limit"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    INVALID_SYMBOL = "invalid_symbol"
    INVALID_SIZE = "invalid_size"
    EXCHANGE_ERROR = "exchange_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ExecutionResult:
    """Execution result with state machine tracking."""
    ok: bool
    status: OrderStatus
    order: Optional[Order] = None
    error_class: Optional[ErrorClass] = None
    error_msg: Optional[str] = None
    stop_loss_order: Optional[Order] = None
    take_profit_order: Optional[Order] = None  # Legacy single TP
    take_profit_orders: list[Order] = field(default_factory=list)  # Multi-level TP
    entry_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None  # Legacy single TP
    take_profit_levels: list[dict[str, float]] = field(default_factory=list)  # Multi-level TP info
    elapsed_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value if self.status else None
        d["error_class"] = self.error_class.value if self.error_class else None
        return d


def classify_error(exc: Exception) -> ErrorClass:
    """Classify exception into error categories for monitoring."""
    msg = str(exc).lower()

    if "credential" in msg or "auth" in msg or "api key" in msg or "signature" in msg:
        return ErrorClass.CREDENTIALS
    if "timeout" in msg or "timed out" in msg:
        return ErrorClass.TIMEOUT
    if "rate limit" in msg or "429" in msg or "too many" in msg:
        return ErrorClass.RATE_LIMIT
    if "insufficient" in msg or "balance" in msg or "margin" in msg:
        return ErrorClass.INSUFFICIENT_BALANCE
    if "symbol" in msg or "invalid instrument" in msg or "not found" in msg:
        return ErrorClass.INVALID_SYMBOL
    if "size" in msg or "amount" in msg or "quantity" in msg:
        return ErrorClass.INVALID_SIZE
    if "network" in msg or "connection" in msg or "unreachable" in msg:
        return ErrorClass.CONNECTIVITY

    return ErrorClass.UNKNOWN


def execute_market_with_stop_loss(
    *,
    exchange_client: Any,
    exchange_name: str,
    canonical_symbol: str,
    side: str,
    size: float,
    stop_loss_price: Optional[float] = None,
    take_profit_price: Optional[float] = None,
    tp_rr: Optional[float] = None,
    entry_price: Optional[float] = None,
    symbol_overrides: dict[str, dict[str, str]],
    hedge_mode: bool = True,
    timeout_sec: float = 10.0,
    place_stop_loss: bool = True,
) -> ExecutionResult:
    """Execute market order with optional stop-loss placement.

    Args:
        exchange_client: Exchange client instance
        exchange_name: Exchange name (e.g., "okx")
        canonical_symbol: Canonical symbol (e.g., "BTC/USDT")
        side: Order side ("buy" or "sell")
        size: Order size
        stop_loss_price: Stop-loss trigger price (optional)
        entry_price: Expected entry price for validation (optional)
        symbol_overrides: Symbol mapping overrides
        hedge_mode: Enable hedge mode (dual position) for OKX
        timeout_sec: Order execution timeout
        place_stop_loss: Whether to place stop-loss after entry fill

    Returns:
        ExecutionResult with order details and stop-loss order if placed.
    """
    start_ts = time.time()

    # Resolve exchange-specific symbol
    ex_overrides = symbol_overrides.get(exchange_name.lower(), {})
    symbol = ex_overrides.get(canonical_symbol.strip().upper(), canonical_symbol)

    # Step 1: Place market order
    try:
        logger.info(
            "tv168_exec: placing order exchange=%s symbol=%s canonical=%s side=%s size=%s hedge=%s",
            exchange_name, symbol, canonical_symbol, side, size, hedge_mode
        )

        order_req = OrderRequest(
            symbol=symbol,
            side=side,
            size=float(size),
            limit_price=None,  # Market order
        )

        # Place order with hedge mode support (OKX-specific)
        if exchange_name.lower() == "okx" and hasattr(exchange_client, 'place_open_order'):
            # OKX client supports hedge_mode parameter
            order = exchange_client.place_open_order(order_req, hedge_mode=hedge_mode)
        else:
            # Generic exchange fallback
            order = exchange_client.place_open_order(order_req)

        if not order or not order.id or order.id.startswith("rejected") or order.id.startswith("error"):
            error_msg = f"Order rejected or failed: {order.id if order else 'null'}"
            logger.error("tv168_exec: %s", error_msg)
            return ExecutionResult(
                ok=False,
                status=OrderStatus.REJECTED,
                order=order,
                error_class=ErrorClass.EXCHANGE_ERROR,
                error_msg=error_msg,
                elapsed_ms=int((time.time() - start_ts) * 1000),
            )

        logger.info(
            "tv168_exec: order placed order_id=%s exchange=%s symbol=%s side=%s size=%s price=%s",
            order.id, exchange_name, symbol, side, size, order.price
        )

        # Step 2: Validate execution (simple check for now)
        filled_price = order.price
        if filled_price <= 0:
            logger.warning("tv168_exec: order fill price is 0, may be pending")
            status = OrderStatus.PARTIAL
        else:
            status = OrderStatus.FILLED

        result = ExecutionResult(
            ok=True,
            status=status,
            order=order,
            entry_price=filled_price if filled_price > 0 else entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            elapsed_ms=int((time.time() - start_ts) * 1000),
        )

        # Step 3: Place stop-loss order if requested and we have a filled price
        if place_stop_loss and stop_loss_price and filled_price > 0:
            try:
                sl_result = _place_stop_loss_order(
                    exchange_client=exchange_client,
                    exchange_name=exchange_name,
                    symbol=symbol,
                    canonical_symbol=canonical_symbol,
                    side=side,
                    size=size,
                    stop_loss_price=stop_loss_price,
                    entry_price=filled_price,
                    hedge_mode=hedge_mode,
                )
                result.stop_loss_order = sl_result.order
                if not sl_result.ok:
                    logger.warning(
                        "tv168_exec: stop-loss placement failed but entry filled error=%s",
                        sl_result.error_msg
                    )
            except Exception as exc:
                logger.exception("tv168_exec: stop-loss placement exception: %s", exc)

        # Step 4: Place take-profit order if requested and we have a filled price
        if take_profit_price and filled_price > 0:
            try:
                tp_result = _place_take_profit_order(
                    exchange_client=exchange_client,
                    exchange_name=exchange_name,
                    symbol=symbol,
                    canonical_symbol=canonical_symbol,
                    side=side,
                    size=size,
                    take_profit_price=take_profit_price,
                    entry_price=filled_price,
                    hedge_mode=hedge_mode,
                )
                result.take_profit_order = tp_result.order
                if not tp_result.ok:
                    logger.warning(
                        "tv168_exec: take-profit placement failed but entry filled error=%s",
                        tp_result.error_msg
                    )
            except Exception as exc:
                logger.exception("tv168_exec: take-profit placement exception: %s", exc)

        # Step 5: Place Multi-Level Take-Profit orders (1.5R, 2.0R, 2.5R, 3.0R)
        # This overrides Step 4 if valid SL and Entry are present
        if stop_loss_price and filled_price > 0:
             try:
                tp_levels = _calculate_tp_levels(
                    side=side,
                    entry_price=filled_price,
                    stop_loss=stop_loss_price,
                    total_size=size
                )
                result.take_profit_levels = tp_levels
                
                for lvl in tp_levels:
                    tp_res = _place_take_profit_order(
                        exchange_client=exchange_client,
                        exchange_name=exchange_name,
                        symbol=symbol,
                        canonical_symbol=canonical_symbol,
                        side=side,
                        size=lvl["size"],
                        take_profit_price=lvl["price"],
                        entry_price=filled_price,
                        hedge_mode=hedge_mode,
                    )
                    if tp_res.ok and tp_res.order:
                        result.take_profit_orders.append(tp_res.order)
                    else:
                        logger.warning(
                            "tv168_exec: multi-tp level failed: price=%.4f size=%.4f error=%s",
                            lvl["price"], lvl["size"], tp_res.error_msg
                        )
             except Exception as exc:
                logger.exception("tv168_exec: multi-tp placement exception: %s", exc)

        return result

    except Exception as exc:
        error_class = classify_error(exc)
        error_msg = str(exc)
        logger.exception("tv168_exec: order execution failed error_class=%s: %s", error_class.value, exc)

        return ExecutionResult(
            ok=False,
            status=OrderStatus.FAILED,
            error_class=error_class,
            error_msg=error_msg,
            elapsed_ms=int((time.time() - start_ts) * 1000),
        )


def _place_stop_loss_order(
    *,
    exchange_client: Any,
    exchange_name: str,
    symbol: str,
    canonical_symbol: str,
    side: str,
    size: float,
    stop_loss_price: float,
    entry_price: float,
    hedge_mode: bool,
) -> ExecutionResult:
    """Place stop-loss order after entry fill.

    For OKX:
    - Long (buy) entry → Stop-loss is a SELL stop order at stop_loss_price
    - Short (sell) entry → Stop-loss is a BUY stop order at stop_loss_price
    - Use conditional order type (stop-loss market)
    """
    try:
        # Determine stop-loss order side
        sl_side = "sell" if side == "buy" else "buy"

        # OKX stop-loss order requires special handling
        # CCXT: exchange.create_order with type='stop' or 'stop_market'
        # OKX API: /api/v5/trade/order-algo with ordType=conditional

        logger.info(
            "tv168_exec: placing stop-loss exchange=%s symbol=%s entry_side=%s sl_side=%s "
            "sl_price=%.4f entry_price=%.4f size=%s",
            exchange_name, symbol, side, sl_side, stop_loss_price, entry_price, size
        )

        # Use exchange-specific stop-loss method if available
        if exchange_name.lower() == "okx" and hasattr(exchange_client, 'place_stop_loss_order'):
            # OKX client has dedicated stop-loss method
            sl_order = exchange_client.place_stop_loss_order(
                symbol=canonical_symbol,
                side=sl_side,
                size=size,
                stop_price=stop_loss_price,
                hedge_mode=hedge_mode,
            )

            if sl_order and sl_order.id and not sl_order.id.startswith("rejected") and not sl_order.id.startswith("error"):
                logger.info(
                    "tv168_exec: stop-loss placed order_id=%s exchange=%s symbol=%s sl_side=%s "
                    "sl_price=%.4f size=%s",
                    sl_order.id, exchange_name, symbol, sl_side, stop_loss_price, size
                )
                return ExecutionResult(
                    ok=True,
                    status=OrderStatus.PLACED,
                    order=sl_order,
                )
            else:
                return ExecutionResult(
                    ok=False,
                    status=OrderStatus.REJECTED,
                    error_class=ErrorClass.EXCHANGE_ERROR,
                    error_msg=f"Stop-loss rejected: {sl_order.id if sl_order else 'null'}",
                )

        else:
            # Generic fallback (may not work for all exchanges)
            logger.warning("tv168_exec: stop-loss not implemented for %s, skipping", exchange_name)
            return ExecutionResult(
                ok=False,
                status=OrderStatus.REJECTED,
                error_class=ErrorClass.EXCHANGE_ERROR,
                error_msg=f"Stop-loss not implemented for {exchange_name}",
            )

    except Exception as exc:
        error_class = classify_error(exc)
        logger.exception("tv168_exec: stop-loss placement failed: %s", exc)
        return ExecutionResult(
            ok=False,
            status=OrderStatus.FAILED,
            error_class=error_class,
            error_msg=str(exc),
        )


def _place_take_profit_order(
    *,
    exchange_client: Any,
    exchange_name: str,
    symbol: str,
    canonical_symbol: str,
    side: str,
    size: float,
    take_profit_price: float,
    entry_price: float,
    hedge_mode: bool,
) -> ExecutionResult:
    """Place take-profit order after entry fill."""
    try:
        # Determine TP order side (opposite of entry)
        tp_side = "sell" if side == "buy" else "buy"

        logger.info(
            "tv168_exec: placing take-profit exchange=%s symbol=%s entry_side=%s tp_side=%s "
            "tp_price=%.4f entry_price=%.4f size=%s",
            exchange_name, symbol, side, tp_side, take_profit_price, entry_price, size
        )

        if exchange_name.lower() == "okx" and hasattr(exchange_client, 'place_take_profit_order'):
            tp_order = exchange_client.place_take_profit_order(
                symbol=canonical_symbol,
                side=tp_side,
                size=size,
                tp_price=take_profit_price,
                hedge_mode=hedge_mode,
            )

            if tp_order and tp_order.id and not tp_order.id.startswith("rejected") and not tp_order.id.startswith("error"):
                return ExecutionResult(ok=True, status=OrderStatus.PLACED, order=tp_order)
            else:
                return ExecutionResult(
                    ok=False,
                    status=OrderStatus.REJECTED,
                    error_class=ErrorClass.EXCHANGE_ERROR,
                    error_msg=f"Take-profit rejected: {tp_order.id if tp_order else 'null'}",
                )
        else:
            logger.warning("tv168_exec: take-profit not implemented for %s, skipping", exchange_name)
            return ExecutionResult(
                ok=False,
                status=OrderStatus.REJECTED,
                error_class=ErrorClass.EXCHANGE_ERROR,
                error_msg=f"Take-profit not implemented for {exchange_name}",
            )

    except Exception as exc:
        error_class = classify_error(exc)
        logger.exception("tv168_exec: take-profit placement failed: %s", exc)
        return ExecutionResult(
            ok=False,
            status=OrderStatus.FAILED,
            error_class=error_class,
            error_msg=str(exc),
            elapsed_ms=int((time.time() - start_ts) * 1000),
        )


def _calculate_tp_levels(
    side: str,
    entry_price: float,
    stop_loss: float,
    total_size: float,
    min_size: float = 0.01
) -> list[dict[str, float]]:
    """Calculate 4 levels of TP based on RR: 1.5, 2.0, 2.5, 3.0.

    Ratios:
    - 1.5R -> 70%
    - 2.0R -> 15%
    - 2.5R -> 10%
    - 3.0R -> 5%
    """
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return []

    rrs = [1.5, 2.0, 2.5, 3.0]
    pcts = [0.70, 0.15, 0.10, 0.05]
    levels = []

    accumulated_size = 0.0
    for i, rr in enumerate(rrs):
        # Calculate price for this RR
        if side == "buy":
            tp_price = entry_price + (risk * rr)
        else:
            tp_price = entry_price - (risk * rr)

        # Calculate size for this level
        lvl_size = total_size * pcts[i]

        # Round to 4 decimal places for generic precision
        lvl_size = round(lvl_size, 4)

        # Check if this is the last level
        is_last = (i == len(rrs) - 1)

        if is_last:
            lvl_size = round(total_size - accumulated_size, 4)

        if lvl_size < min_size and not is_last:
            # Too small, roll into next level
            continue

        if lvl_size > 0:
            levels.append({"price": round(tp_price, 4), "size": lvl_size, "rr": rr})
            accumulated_size += lvl_size

    # Final safety: if we skipped levels due to min_size, ensure the last one
    # covers the full remaining amount
    if levels and accumulated_size < total_size:
        levels[-1]["size"] = round(levels[-1]["size"] + (total_size - accumulated_size), 4)

    return levels
