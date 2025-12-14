from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from perpbot.capital_orchestrator import CapitalOrchestrator, CapitalReservation
from perpbot.events import Event, EventBus, EventKind
from perpbot.exposure import ExposureAggregator
from perpbot.execution.execution_engine import OrderResult, OrderStatus
from perpbot.models.order import Order
from perpbot.risk_manager import RiskManager

logger = logging.getLogger(__name__)


class MockOrderOutcome(Enum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class MockExecutionResult:
    """模拟执行结果，兼容实盘 ExecutionEngine 的结构感知。"""

    order_id: str
    status: MockOrderOutcome
    filled_qty: Decimal
    avg_price: Decimal
    timestamp: datetime
    error: Optional[str]
    order_result: OrderResult


class MockExecutionEngine:
    """
    Mock ExecutionEngine for dry-run / integration validation.

    模拟一个真实交易所下单逻辑，执行概率/延迟/资金/敞口规则，同时通过 EventBus 发送生命周期事件。
    """

    def __init__(
        self,
        event_bus: EventBus,
        capital_orchestrator: Optional[CapitalOrchestrator] = None,
        exposure_aggregator: Optional[ExposureAggregator] = None,
        risk_manager: Optional[RiskManager] = None,
        random_seed: Optional[int] = None,
    ):
        self.event_bus = event_bus
        self.capital_orchestrator = capital_orchestrator
        self.exposure_aggregator = exposure_aggregator
        self.risk_manager = risk_manager
        self.random = random.Random(random_seed)
        self._lock = threading.Lock()
        self._ticket = 0

    def _generate_order_id(self, symbol: str) -> str:
        with self._lock:
            self._ticket += 1
            ts = int(time.time())
            sanitized = symbol.replace("/", "").replace("-", "").upper()
            return f"MOCK-{sanitized}-{ts}-{self._ticket:04d}"

    def _publish_event(self, kind: EventKind, payload: Dict[str, Any], correlation_id: Optional[str]) -> None:
        event = Event.now(kind=kind, source="mock-execution", payload=payload, correlation_id=correlation_id)
        self.event_bus.publish(event)

    def _reserve_capital(
        self, exchange: str, amount: float, strategy: str, execution_context: Dict[str, Any]
    ) -> Optional[CapitalReservation]:
        if not self.capital_orchestrator:
            return None
        reservation = self.capital_orchestrator.reserve_for_strategy(
            [exchange], amount=amount, strategy=strategy or "dry_run"
        )
        if not reservation.approved:
            logger.warning("MockExecutionEngine capital reservation blocked: %s", reservation.reason)
        return reservation

    def _release_capital(self, reservation: Optional[CapitalReservation]) -> None:
        if reservation and self.capital_orchestrator:
            self.capital_orchestrator.release(reservation)

    def _simulate_status(self) -> MockOrderOutcome:
        roll = self.random.random()
        if roll < 0.6:
            return MockOrderOutcome.FILLED
        if roll < 0.8:
            return MockOrderOutcome.PARTIALLY_FILLED
        if roll < 0.9:
            return MockOrderOutcome.REJECTED
        return MockOrderOutcome.CANCELLED

    def _map_status(self, outcome: MockOrderOutcome) -> OrderStatus:
        if outcome == MockOrderOutcome.FILLED:
            return OrderStatus.FILLED
        if outcome == MockOrderOutcome.PARTIALLY_FILLED:
            return OrderStatus.PARTIAL
        if outcome == MockOrderOutcome.CANCELLED:
            return OrderStatus.CANCELLED
        return OrderStatus.FAILED

    def submit_order(
        self,
        symbol: str,
        contract_id: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        order_type: str,
        time_in_force: str,
        execution_context: Dict[str, Any],
    ) -> MockExecutionResult:
        correlation_id = execution_context.get("correlation_id")
        exchange = execution_context.get("exchange", "mock")
        strategy = execution_context.get("strategy", "dry_run")
        positions = execution_context.get("positions", [])
        quotes = execution_context.get("quotes", [])
        notional = float(quantity * price)

        order_id = self._generate_order_id(symbol)
        created_ts = datetime.utcnow()
        self._publish_event(
            EventKind.EXECUTION_SUBMITTED,
            {
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "quantity": float(quantity),
                "price": float(price),
                "contract_id": contract_id,
                "order_type": order_type,
                "time_in_force": time_in_force,
                "exchange": exchange,
            },
            correlation_id,
        )

        if self.risk_manager:
            allow, reason = self.risk_manager.can_trade(symbol, side, float(quantity), float(price), positions, quotes)
            if not allow:
                error = reason or "risk blocked"
                result = self._build_result(order_id, symbol, side, order_type, exchange, quantity, price, 0, Decimal("0"), MockOrderOutcome.REJECTED, error, 0.0)
                self._publish_event(EventKind.RISK_REJECT, {"order_id": order_id, "reason": error}, correlation_id)
                return result

        reservation = self._reserve_capital(exchange, notional, strategy, execution_context)
        if reservation and not reservation.approved:
            error = reservation.reason or "capital rejected"
            self._release_capital(reservation)
            result = self._build_result(order_id, symbol, side, order_type, exchange, quantity, price, 0, Decimal("0"), MockOrderOutcome.REJECTED, error, 0.0)
            self._publish_event(EventKind.CAPITAL_REJECT, {"order_id": order_id, "reason": error}, correlation_id)
            return result

        delay = self.random.uniform(0.02, 0.3)
        time.sleep(delay)

        outcome = self._simulate_status()
        if outcome == MockOrderOutcome.PARTIALLY_FILLED:
            filled_ratio = Decimal(str(self.random.uniform(0.1, 0.9)))
            filled_qty = (quantity * filled_ratio).quantize(Decimal("0.00000001"))
        elif outcome == MockOrderOutcome.FILLED:
            filled_qty = quantity
        else:
            filled_qty = Decimal("0")

        filled_qty = min(quantity, filled_qty)

        avg_price = price if filled_qty > 0 else Decimal("0")
        if filled_qty > 0 and self.exposure_aggregator:
            order_model = Order(
                id=order_id,
                exchange=exchange,
                symbol=symbol,
                side=side,
                size=float(filled_qty),
                price=float(avg_price),
            )
            self.exposure_aggregator.update_after_fill(order_model, float(avg_price), float(filled_qty))

        order_result = self._build_result(
            order_id,
            symbol,
            side,
            order_type,
            exchange,
            quantity,
            price,
            filled_qty,
            avg_price,
            outcome,
            None,
            delay * 1000,
        )

        if outcome in (MockOrderOutcome.FILLED, MockOrderOutcome.PARTIALLY_FILLED):
            event_kind = EventKind.EXECUTION_FILLED
            payload = {
                "order_id": order_id,
                "fill_qty": float(filled_qty),
                "avg_price": float(avg_price),
            }
        else:
            event_kind = EventKind.EXECUTION_FAILED
            payload = {
                "order_id": order_id,
                "reason": "mock outcome " + outcome.value,
            }

        self._publish_event(event_kind, payload, correlation_id)
        self._release_capital(reservation)
        return MockExecutionResult(
            order_id=order_id,
            status=outcome,
            filled_qty=filled_qty,
            avg_price=avg_price,
            timestamp=datetime.utcnow(),
            error=None if outcome in (MockOrderOutcome.FILLED, MockOrderOutcome.PARTIALLY_FILLED) else payload.get("reason"),
            order_result=order_result,
        )

    def _build_result(
        self,
        order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        exchange: str,
        requested_qty: Decimal,
        price: Decimal,
        filled_qty: Decimal,
        avg_price: Decimal,
        outcome: MockOrderOutcome,
        error: Optional[str],
        execution_time_ms: float,
    ) -> OrderResult:
        status = self._map_status(outcome)
        return OrderResult(
            order_id=order_id,
            exchange=exchange,
            symbol=symbol,
            side=side,
            order_type=order_type,
            notional=float(requested_qty * price),
            fill_price=float(avg_price),
            status=status,
            actual_fee=0.0,
            execution_time_ms=execution_time_ms,
            error=error,
        )
