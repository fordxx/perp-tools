import asyncio
import logging
import time
from typing import Dict, List, Optional

from perpbot.events import Event, EventBus, EventKind

from capital.capital_orchestrator_v2 import CapitalOrchestratorV2
from capital.capital_snapshot import ExchangeCapitalSnapshot, GlobalCapitalSnapshot
from exposure.exposure_aggregator import ExposureAggregator
from exposure.exposure_service import ExposureService
from exposure.exposure_snapshot import GlobalExposureSnapshot
from models.order import Order
from models.order_request import OrderRequest
from positions.position_aggregator import PositionAggregator
from risk.kill_switch import KillSwitchState, KillSwitchV2
from risk.pre_trade_context import PreTradeContext
from risk.risk_engine import RiskEngine
from .execution_result import ExecutionResult
from .fallback_policy import BaseFallbackPolicy
from .retry_policy import BaseRetryPolicy

logger = logging.getLogger(__name__)


class ExecutionEngineV2:
    """
    A robust execution engine featuring retries, fallbacks, and comprehensive risk management.
    """

    def __init__(
        self,
        risk_engine: RiskEngine,
        position_aggregator: PositionAggregator,
        exposure_aggregator: ExposureAggregator,
        exposure_service: ExposureService,
        kill_switch: KillSwitchV2,
        capital_orchestrator: CapitalOrchestratorV2,
        retry_policy: BaseRetryPolicy,
        fallback_policy: Optional[BaseFallbackPolicy] = None,
        event_bus: EventBus | None = None,
        # In a real system, you would pass exchange client instances
        # exchanges: Dict[str, BaseExchange],
    ):
        self.risk_engine = risk_engine
        self.position_aggregator = position_aggregator
        self.exposure_aggregator = exposure_aggregator
        self.exposure_service = exposure_service
        self.kill_switch = kill_switch
        self.capital_orchestrator = capital_orchestrator
        self.retry_policy = retry_policy
        self.fallback_policy = fallback_policy
        # self.exchanges = exchanges
        self._recent_order_timestamps: List[float] = []

        self._event_bus = event_bus
        self._source = self.__class__.__name__

    def _publish_event(self, kind: EventKind, payload: Dict[str, object]) -> None:
        if not self._event_bus:
            return
        try:
            self._event_bus.publish(Event.now(kind=kind, source=self._source, payload=payload))
        except Exception:
            logger.exception("Failed to publish event to EventBus.")

    def _publish_failure(self, reason: str, stage: str, request: OrderRequest, attempts: int) -> None:
        self._publish_event(
            EventKind.EXECUTION_FAILED,
            {
                "exchange": request.exchange,
                "symbol": request.symbol,
                "side": request.side,
                "price": request.limit_price,
                "size": request.size,
                "strategy": request.strategy,
                "reason": reason,
                "stage": stage,
                "attempts": attempts,
                "is_fallback": request.is_fallback,
            },
        )

    async def execute_order(self, request: OrderRequest) -> ExecutionResult:
        """
        Executes an order request with the full pipeline of risk checks, retries, and fallbacks.
        """
        try:
            return await self._execute_with_policies(request)
        except Exception as e:
            logger.exception(f"Unhandled exception during order execution for {request.symbol}")
            return ExecutionResult.failed(f"Unhandled exception: {e}", request.exchange, request.symbol)

    async def _execute_with_policies(self, request: OrderRequest) -> ExecutionResult:
        """Internal execution loop with retry, capital, and fallback policies."""
        attempts = 0
        current_request = request

        while attempts < self.retry_policy.max_retries:
            attempts += 1
            self._publish_event(
                EventKind.EXECUTION_SUBMITTED,
                {
                    "exchange": current_request.exchange,
                    "symbol": current_request.symbol,
                    "side": current_request.side,
                    "price": current_request.limit_price,
                    "size": current_request.size,
                    "strategy": current_request.strategy,
                    "is_fallback": current_request.is_fallback,
                    "attempt": attempts,
                },
            )
            kill_switch_status = self.kill_switch.get_status()
            if kill_switch_status.state == KillSwitchState.ACTIVATED:
                reason = f"Kill Switch is ACTIVATED during attempt {attempts}: {kill_switch_status.reason}"
                logger.error(reason)
                self._publish_failure(reason, "kill_switch", current_request, attempts)
                return ExecutionResult.failed(reason, current_request.exchange, current_request.symbol, attempts=attempts)

            context = self._build_pre_trade_context(current_request)
            failed_checks = self.risk_engine.check(context)
            if failed_checks:
                reasons = [f"{res.guard_name}: {res.reason}" for res in failed_checks]
                error_msg = f"Pre-trade risk check failed: {'; '.join(reasons)}"
                logger.error(error_msg, extra={"details": [res.details for res in failed_checks]})
                self._publish_failure(error_msg, "risk", current_request, attempts)
                return ExecutionResult.failed(error_msg, current_request.exchange, current_request.symbol, attempts=attempts)

            reservation = self._reserve_capital(current_request, context)
            if not reservation.ok:
                reason = reservation.reason or "Capital reservation denied"
                logger.warning(f"Capital reservation failed: {reason}")
                self._publish_event(
                    EventKind.CAPITAL_REJECT,
                    {
                        "exchange": current_request.exchange,
                        "strategy": current_request.strategy,
                        "reason": reason,
                        "requested_notional": context.notional,
                        "allowed_notional": reservation.allowed_notional,
                    },
                )
                self._publish_failure(reason, "capital", current_request, attempts)
                return ExecutionResult.failed(reason, current_request.exchange, current_request.symbol, attempts=attempts)

            allowed_request = self._apply_allowed_notional(current_request, reservation.allowed_notional)
            if allowed_request.size <= 0:
                reason = "Allowed notional did not translate to any executable size"
                logger.warning(reason)
                self._publish_failure(reason, "capital", current_request, attempts)
                return ExecutionResult.failed(reason, current_request.exchange, current_request.symbol, attempts=attempts)

            try:
                order_result: Order = await self.retry_policy.execute(
                    self._place_order_on_exchange, allowed_request
                )

                if order_result.size >= allowed_request.size:
                    fill_price = allowed_request.limit_price or order_result.price
                    fill_size = order_result.size
                    exposure_snapshot = self._record_successful_fill(order_result, fill_price, fill_size)
                    self._publish_event(
                        EventKind.EXECUTION_FILLED,
                        {
                            "exchange": allowed_request.exchange,
                            "symbol": allowed_request.symbol,
                            "side": allowed_request.side,
                            "filled_size": fill_size,
                            "fill_price": fill_price,
                            "order_id": order_result.id,
                            "attempts": attempts,
                            "is_fallback": allowed_request.is_fallback,
                        },
                    )
                    if exposure_snapshot:
                        self._publish_event(
                            EventKind.EXPOSURE_UPDATE,
                            {
                                "symbol": order_result.symbol,
                                "exchange": order_result.exchange,
                                "global_net_exposure": exposure_snapshot.global_exposure.net_exposure,
                                "global_gross_exposure": exposure_snapshot.global_exposure.gross_exposure,
                                "timestamp": exposure_snapshot.timestamp,
                            },
                        )
                    return ExecutionResult.success(
                        order_id=order_result.id,
                        filled_size=order_result.size,
                        avg_price=order_result.price,
                        exchange=allowed_request.exchange,
                        symbol=allowed_request.symbol,
                        attempts=attempts,
                    )

                remaining_size = current_request.size - order_result.size
                reason = f"Order only partially filled ({order_result.size}/{current_request.size})."

                if self.fallback_policy:
                    fallback_action = self.fallback_policy.get_fallback_action(
                        original_request=current_request,
                        remaining_size=remaining_size,
                        reason=reason
                    )
                    if fallback_action:
                        logger.warning(f"{reason} Triggering fallback: {fallback_action.reason}")
                        current_request = fallback_action.new_request
                        continue

                self._publish_failure(reason, "execution_partial", current_request, attempts)
                return ExecutionResult.failed(
                    reason,
                    current_request.exchange,
                    current_request.symbol,
                    order_id=order_result.id,
                    attempts=attempts,
                )

            except Exception as e:
                logger.error(f"Execution attempt {attempts} failed for {current_request.symbol}: {e}")
                if attempts >= self.retry_policy.max_retries:
                    failure_reason = f"All {attempts} attempts failed. Last error: {e}"
                    self._publish_failure(failure_reason, "execution_exception", current_request, attempts)
                    return ExecutionResult.failed(failure_reason, current_request.exchange, current_request.symbol, attempts=attempts)
                await asyncio.sleep(1)
            finally:
                self.capital_orchestrator.release_reservation(
                    reservation.exchange,
                    reservation.strategy,
                    reservation.allowed_notional,
                )

        final_reason = "Max retries reached in outer loop."
        self._publish_failure(final_reason, "execution_max_retries", request, attempts)
        return ExecutionResult.failed(final_reason, request.exchange, request.symbol, attempts=attempts)

    async def _place_order_on_exchange(self, request: OrderRequest) -> Order:
        """
        A mock function representing the actual interaction with an exchange client.
        """
        logger.info(f"SIMULATING: Placing order on {request.exchange} for {request.symbol} size={request.size}")
        # exchange = self.exchanges[request.exchange]
        # order = await exchange.place_open_order(request)
        # self._recent_order_timestamps.append(time.time())
        # return order
        
        # --- Placeholder for actual order placement ---
        import random
        if random.random() < 0.3: # Simulate a failure
            raise ConnectionError("Simulated network error")
        
        order = Order(
            id=f"sim_{int(time.time())}",
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=request.limit_price or 3000.0,
            created_at=time.time(),
        )
        self._recent_order_timestamps.append(time.time())
        return order
        # --- End Placeholder ---

    def _build_pre_trade_context(self, request: OrderRequest) -> PreTradeContext:
        """Constructs the context for risk evaluation (simplified mock)."""
        order_notional = request.size * (request.limit_price or 3000.0) # Mock price
        post_trade_gross_exposure = self.position_aggregator.get_gross_exposure() + order_notional
        
        symbol_exposure = self.exposure_service.get_symbol_exposure(request.symbol)
        exchange_exposure = self.exposure_service.get_exchange_exposure(request.exchange)
        global_exposure = self.exposure_service.get_global_exposure()

        return PreTradeContext(
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=request.limit_price or 3000.0,
            notional=order_notional,
            account_equity=10000.0,
            available_margin=5000.0,
            net_exposure=0,
            gross_exposure=post_trade_gross_exposure,
            leverage=5.0,
            market_volatility=0.05,
            recent_order_timestamps=self._recent_order_timestamps,
            symbol_exposure=symbol_exposure,
            exchange_exposure=exchange_exposure,
            global_exposure=global_exposure,
        )

    def _record_successful_fill(self, order: Order, fill_price: float, fill_size: float) -> Optional[GlobalExposureSnapshot]:
        updater = getattr(self.position_aggregator, "update_after_fill", None)
        if callable(updater):
            try:
                updater(order, fill_price, fill_size)
            except Exception:
                logger.exception("Failed to push fill data to PositionAggregator.")

        exposure_snapshot: Optional[GlobalExposureSnapshot] = None
        try:
            exposure_snapshot = self.exposure_aggregator.update_after_fill(order, fill_price, fill_size)
        except Exception:
            logger.exception("Failed to push fill to ExposureAggregator.")

        self._increment_open_notional(order.exchange, fill_price * fill_size)
        return exposure_snapshot

    def _increment_open_notional(self, exchange: str, amount: float):
        snapshot = self.capital_orchestrator.get_snapshot()
        if not snapshot or amount <= 0:
            return
        exchange_snapshot = snapshot.per_exchange.get(exchange)
        if exchange_snapshot:
            exchange_snapshot.open_notional += amount
        snapshot.total_open_notional += amount

    def _reserve_capital(self, request: OrderRequest, context: PreTradeContext):
        """Calls the capital orchestrator with current exposure snapshots."""
        current_exchange_notional = self.position_aggregator.get_gross_exposure()
        current_strategy_notional = current_exchange_notional

        if not self.capital_orchestrator.get_snapshot():
            placeholder_snapshot = GlobalCapitalSnapshot(
                per_exchange={
                    request.exchange: ExchangeCapitalSnapshot(
                        exchange=request.exchange,
                        equity=context.account_equity,
                        available_balance=context.available_margin,
                        open_notional=0.0,
                        used_margin=0.0,
                        unrealized_pnl=0.0,
                        realized_pnl=0.0,
                        leverage=context.leverage,
                        timestamp=time.time(),
                    )
                },
                total_equity=context.account_equity,
                total_unrealized_pnl=0.0,
                total_realized_pnl=0.0,
                total_open_notional=0.0,
                timestamp=time.time(),
            )
            self.capital_orchestrator.update_snapshot(placeholder_snapshot)

        return self.capital_orchestrator.reserve_for_order(
            exchange=request.exchange,
            strategy=request.strategy,
            requested_notional=context.notional,
            current_open_notional_per_exchange={request.exchange: current_exchange_notional},
            current_open_notional_per_strategy={request.strategy: current_strategy_notional},
        )

    def _apply_allowed_notional(self, request: OrderRequest, allowed_notional: float) -> OrderRequest:
        """Creates a new request capped by the allowed capital while preserving metadata."""
        if allowed_notional >= request.size * (request.limit_price or 1.0):
            return request

        price = request.limit_price or 1.0
        capped_size = max(allowed_notional / price, 0.0)
        if capped_size <= 0:
            return request

        return OrderRequest(
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            size=min(request.size, capped_size),
            limit_price=request.limit_price,
            strategy=request.strategy,
            is_fallback=request.is_fallback,
        )
