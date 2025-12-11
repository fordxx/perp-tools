import asyncio
import logging
from typing import Dict, List, Optional

from ..models.order import Order
from ..models.order_request import OrderRequest
from ..positions.position_aggregator import PositionAggregator
from ..risk.kill_switch import KillSwitchState, KillSwitchV2
from ..risk.pre_trade_context import PreTradeContext
from ..risk.risk_engine import RiskEngine
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
        kill_switch: KillSwitchV2,
        retry_policy: BaseRetryPolicy,
        fallback_policy: Optional[BaseFallbackPolicy] = None,
        # In a real system, you would pass exchange client instances
        # exchanges: Dict[str, BaseExchange],
    ):
        self.risk_engine = risk_engine
        self.position_aggregator = position_aggregator
        self.kill_switch = kill_switch
        self.retry_policy = retry_policy
        self.fallback_policy = fallback_policy
        # self.exchanges = exchanges
        self._recent_order_timestamps: List[float] = []

    async def execute_order(self, request: OrderRequest) -> ExecutionResult:
        """
        Executes an order request with the full pipeline of risk checks, retries, and fallbacks.
        """
        # 1. Check Kill Switch status
        kill_switch_status = self.kill_switch.get_status()
        if kill_switch_status.state == KillSwitchState.ACTIVATED:
            reason = f"Kill Switch is ACTIVATED: {kill_switch_status.reason}"
            logger.error(f"Order rejected: {reason}")
            return ExecutionResult.failed(reason, request.exchange, request.symbol)

        # 2. Build Pre-Trade Context and run risk checks
        context = self._build_pre_trade_context(request)
        failed_checks = self.risk_engine.check(context)
        if failed_checks:
            reasons = [f"{res.guard_name}: {res.reason}" for res in failed_checks]
            error_msg = f"Pre-trade risk check failed: {'; '.join(reasons)}"
            logger.error(error_msg, extra={"details": [res.details for res in failed_checks]})
            return ExecutionResult.failed(error_msg, request.exchange, request.symbol)

        logger.info(f"Pre-trade checks passed for {request.symbol}. Proceeding with execution.")

        # 3. Execute with retry and fallback logic
        try:
            return await self._execute_with_policies(request)
        except Exception as e:
            logger.exception(f"Unhandled exception during order execution for {request.symbol}")
            return ExecutionResult.failed(f"Unhandled exception: {e}", request.exchange, request.symbol)

    async def _execute_with_policies(self, request: OrderRequest) -> ExecutionResult:
        """Internal execution loop with retry and fallback policies."""
        attempts = 0
        current_request = request

        while attempts < self.retry_policy.max_retries:
            attempts += 1
            try:
                # This is a placeholder for the actual exchange API call
                order_result: Order = await self.retry_policy.execute(
                    self._place_order_on_exchange, current_request
                )

                # TODO: Handle partial fills. For now, assume full fill or failure.
                if order_result.size == current_request.size:
                    return ExecutionResult.success(
                        order_id=order_result.id,
                        filled_size=order_result.size,
                        avg_price=order_result.price,
                        exchange=current_request.exchange,
                        symbol=current_request.symbol,
                        attempts=attempts,
                    )
                else: # Partial fill or no fill
                    remaining_size = current_request.size - order_result.size
                    reason = f"Order only partially filled ({order_result.size}/{current_request.size})."
                    
                    if self.fallback_policy:
                        fallback_action = self.fallback_policy.get_fallback_action(
                            original_request=request,
                            remaining_size=remaining_size,
                            reason=reason
                        )
                        if fallback_action:
                            logger.warning(f"{reason} Triggering fallback: {fallback_action.reason}")
                            current_request = fallback_action.new_request
                            # Continue to the next iteration of the while loop to execute the fallback
                            continue

                    # No fallback or fallback not applicable
                    return ExecutionResult.failed(reason, request.exchange, request.symbol, order_id=order_result.id)

            except Exception as e:
                logger.error(f"Execution attempt {attempts} failed for {request.symbol}: {e}")
                if attempts >= self.retry_policy.max_retries:
                    return ExecutionResult.failed(f"All {attempts} attempts failed. Last error: {e}", request.exchange, request.symbol)
                # The retry policy's sleep is handled within its `execute` method,
                # but for this simplified loop, we add a small delay.
                await asyncio.sleep(1)

        return ExecutionResult.failed("Max retries reached in outer loop.", request.exchange, request.symbol)

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
        import time, random
        if random.random() < 0.3: # Simulate a failure
            raise ConnectionError("Simulated network error")
        
        return Order(id=f"sim_{int(time.time())}", symbol=request.symbol, side=request.side, size=request.size, price=request.limit_price or 3000.0, created_at=time.time())
        # --- End Placeholder ---

    def _build_pre_trade_context(self, request: OrderRequest) -> PreTradeContext:
        """Constructs the context for risk evaluation (simplified mock)."""
        order_notional = request.size * (request.limit_price or 3000.0) # Mock price
        post_trade_gross_exposure = self.position_aggregator.get_gross_exposure() + order_notional
        
        return PreTradeContext(
            exchange=request.exchange, symbol=request.symbol, side=request.side, size=request.size,
            price=request.limit_price or 3000.0, notional=order_notional, account_equity=10000.0,
            available_margin=5000.0, net_exposure=0, gross_exposure=post_trade_gross_exposure,
            leverage=5.0, market_volatility=0.05, recent_order_timestamps=self._recent_order_timestamps
        )