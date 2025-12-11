import asyncio
import logging

from .engines.execution_engine import ExecutionEngine
from .models.order_request import OrderRequest
from .models.position_snapshot import UnifiedPosition
from .positions.position_aggregator import PositionAggregator
from .risk.guards.max_exposure_guard import MaxExposureGuard
from .risk.guards.max_leverage_guard import MaxLeverageGuard
from .risk.guards.max_notional_guard import MaxNotionalGuard
from .risk.guards.order_frequency_guard import OrderFrequencyGuard
from .risk.kill_switch import KillSwitchV2
from .risk.risk_engine import RiskEngine
from .web.console_updater import WebConsoleUpdater

# --- Basic Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("perpbot_main")


async def main():
    """
    Main application function to assemble and run all components.
    """
    print("\n--- Initializing PerpBot Components ---")

    # 1. Initialize core components
    position_aggregator = PositionAggregator()
    risk_engine = RiskEngine()
    kill_switch = KillSwitchV2()

    # 2. Configure and add risk guards
    risk_engine.add_guard(MaxNotionalGuard(max_notional=50000.0))
    risk_engine.add_guard(MaxExposureGuard(max_gross_exposure=100000.0))
    risk_engine.add_guard(MaxLeverageGuard(max_leverage=10.0))
    risk_engine.add_guard(OrderFrequencyGuard(max_orders=5, time_window_seconds=60))
    logger.info(f"RiskEngine configured with {len(risk_engine.get_guards())} guards.")

    # 3. Initialize main engines
    execution_engine = ExecutionEngine(
        risk_engine=risk_engine,
        position_aggregator=position_aggregator,
        kill_switch=kill_switch,
    )
    logger.info("ExecutionEngine initialized.")

    # 4. Initialize status updater
    console_updater = WebConsoleUpdater(
        risk_engine=risk_engine,
        kill_switch=kill_switch,
        position_aggregator=position_aggregator,
        update_interval=5.0,
    )
    console_updater.start()
    logger.info("WebConsoleUpdater started in the background.")

    # --- Simulation ---
    print("\n--- Starting Simulation ---")

    # Simulate existing positions from two exchanges
    position_aggregator.update_positions_for_exchange(
        "binance",
        [
            UnifiedPosition("binance", "BTC-PERP", "LONG", 0.5, 35000, 70000, 71000, 500)
        ],
    )
    position_aggregator.update_positions_for_exchange(
        "paradex",
        [
            UnifiedPosition("paradex", "ETH-PERP", "SHORT", 10, 35000, 3500, 3400, 1000)
        ],
    )
    logger.info("Updated position aggregator with initial mock data.")
    await asyncio.sleep(1)

    # a) Try to place a valid order
    print("\n1. Attempting to place a valid order...")
    try:
        valid_order_req = OrderRequest(exchange="binance", symbol="ETH-PERP", side="buy", size=1, limit_price=3500)
        await execution_engine.place_order(valid_order_req)
        logger.info("✅ Valid order placed successfully.")
    except (ValueError, PermissionError) as e:
        logger.error(f"❌ Valid order failed unexpectedly: {e}")

    await asyncio.sleep(1)

    # b) Try to place an order that violates a risk rule (MaxNotionalGuard)
    print("\n2. Attempting to place an order that violates a risk rule...")
    try:
        invalid_order_req = OrderRequest(exchange="binance", symbol="BTC-PERP", side="buy", size=1, limit_price=60000)
        await execution_engine.place_order(invalid_order_req)
    except (ValueError, PermissionError) as e:
        logger.warning(f"✅ Correctly blocked invalid order: {e}")

    await asyncio.sleep(1)

    # c) Activate Kill Switch and try to place an order
    print("\n3. Activating Kill Switch and attempting to place an order...")
    await kill_switch.activate(reason="Manual intervention required.")
    try:
        ks_order_req = OrderRequest(exchange="binance", symbol="ETH-PERP", side="buy", size=1, limit_price=3500)
        await execution_engine.place_order(ks_order_req)
    except (ValueError, PermissionError) as e:
        logger.warning(f"✅ Correctly blocked order due to Kill Switch: {e}")

    # --- Shutdown ---
    await asyncio.sleep(5) # Let the updater run a bit longer
    console_updater.stop()
    print("\n--- Simulation Finished ---")


if __name__ == "__main__":
    # Note: We need a dummy OrderRequest model for this to run.
    # Let's define a simple one if it doesn't exist.
    try:
        from .models import order_request
    except ImportError:
        from dataclasses import dataclass
        @dataclass
        class OrderRequest:
            exchange: str
            symbol: str
            side: str
            size: float
            limit_price: float | None

        # Monkey-patch it into the module scope for the engine
        import sys
        from . import models
        setattr(models, 'OrderRequest', OrderRequest)
        # A real implementation would have this model defined properly.

    asyncio.run(main())