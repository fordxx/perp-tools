import logging
import time
from typing import Dict, List

from models import Order, OrderRequest
from risk.kill_switch import KillSwitchState, KillSwitchV2
from risk.pre_trade_context import PreTradeContext
from risk.risk_engine import RiskEngine

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Handles order execution, integrating pre-trade risk checks and a kill switch.

    This class is a simplified representation. A real implementation would need
    access to exchange clients, account state, market data, etc.
    """

    def __init__(
        self,
        risk_engine: RiskEngine,
        kill_switch: KillSwitchV2,
        # In a real scenario, you would pass exchange client instances
        # exchanges: Dict[str, BaseExchange],
    ):
        self.risk_engine = risk_engine
        self.kill_switch = kill_switch
        # self.exchanges = exchanges
        self._recent_order_timestamps: List[float] = []

    async def place_order(self, request: OrderRequest) -> Order:
        """
        Places an order after performing risk checks.
        """
        # 1. Check Kill Switch status first
        kill_switch_status = self.kill_switch.get_status()
        if kill_switch_status.state == KillSwitchState.ACTIVATED:
            reason = f"Order rejected: Kill Switch is ACTIVATED. Reason: {kill_switch_status.reason}"
            logger.error(reason)
            # In a real system, you might return a rejected Order object
            raise PermissionError(reason)

        # 2. Build the Pre-Trade Context
        # This is a placeholder. A real implementation would fetch live data.
        context = self._build_pre_trade_context(request)

        # 3. Run risk checks
        failed_checks = self.risk_engine.check(context)
        if failed_checks:
            reasons = [f"{res.guard_name}: {res.reason}" for res in failed_checks]
            error_msg = f"Pre-trade risk check failed for order {request.symbol}: {'; '.join(reasons)}"
            logger.error(error_msg, extra={"details": [res.details for res in failed_checks]})

            # Potentially activate Kill Switch on critical failure
            # For example, if MaxLeverageGuard fails repeatedly.
            # await self.kill_switch.activate("Critical risk breach: Max Leverage exceeded", details=...)

            raise ValueError(error_msg)

        logger.info("Pre-trade risk checks passed. Proceeding with order placement.")

        # 4. Place the order (placeholder)
        # exchange = self.exchanges[request.exchange]
        # order = await exchange.place_open_order(request)
        
        # --- Placeholder for actual order placement ---
        print(f"SIMULATING: Placing order on {request.exchange} for {request.symbol}")
        order = Order(
            id=f"sim_{int(time.time())}",
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=request.limit_price or 0, # Assuming 0 for market order if not priced
            created_at=time.time(),
        )
        # --- End Placeholder ---

        # 5. Record timestamp for frequency checks
        self._recent_order_timestamps.append(order.created_at)

        return order

    def _build_pre_trade_context(self, request: OrderRequest) -> PreTradeContext:
        """
        Constructs the context for risk evaluation.
        NOTE: This is a simplified mock. A real system needs to fetch live data
        from account managers, position trackers, and market data feeds.
        """
        # Mock data for demonstration purposes
        return PreTradeContext(
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            size=request.size,
            price=request.limit_price or 100.0,  # Mock price
            notional=(request.size * (request.limit_price or 100.0)),
            account_equity=10000.0,
            available_margin=5000.0,
            net_exposure=15000.0,
            gross_exposure=25000.0,
            leverage=2.5,
            market_volatility=0.05,
            recent_order_timestamps=self._recent_order_timestamps,
        )
