import asyncio
import logging
import os
import threading
import uvicorn

from capital.capital_limits import CapitalLimitConfig
from capital.capital_orchestrator_v2 import CapitalOrchestratorV2
from capital.capital_snapshot_provider import MockCapitalSnapshotProvider
from capital.providers import (
    CapitalSnapshotProvider,
    CompositeCapitalSnapshotProvider,
    ExtendedCapitalSnapshotProvider,
    ParadexCapitalSnapshotProvider,
)
from console_updater import WebConsoleUpdater
from execution_engine_v2 import ExecutionEngineV2
from exposure.exposure_aggregator import ExposureAggregator
from exposure.exposure_service import ExposureService
from health.health_monitor import HealthMonitor
from quote_engine_v2 import QuoteEngineV2
from console.console_state import ConsoleState
from console.web import create_web_app
from perpbot.events import EventBus
from perpbot.events.subscribers import make_default_subscribers
from models.order_request import OrderRequest
from models.position_snapshot import UnifiedPosition
from positions.position_aggregator import PositionAggregator


def build_capital_provider(
    env: str,
    paradex_client: object | None = None,
    extended_client: object | None = None,
) -> CapitalSnapshotProvider:
    mode = (env or "mock").lower()
    if mode == "single_paradex" and paradex_client is not None:
        return ParadexCapitalSnapshotProvider(paradex_client)
    if mode == "multi":
        providers = {}
        if paradex_client is not None:
            providers["PARADEX"] = ParadexCapitalSnapshotProvider(paradex_client)
        if extended_client is not None:
            providers["EXTENDED"] = ExtendedCapitalSnapshotProvider(extended_client)
        if providers:
            return CompositeCapitalSnapshotProvider(providers)
    return MockCapitalSnapshotProvider()
from retry_policy import ExponentialBackoffPolicy
from risk.guards.max_exposure_guard import MaxExposureGuard
from risk.guards.max_leverage_guard import MaxLeverageGuard
from risk.guards.max_notional_guard import MaxNotionalGuard
from risk.guards.order_frequency_guard import OrderFrequencyGuard
from risk.kill_switch import KillSwitchV2
from risk.risk_engine import RiskEngine

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

    event_bus = EventBus()
    for kind, handler in make_default_subscribers():
        event_bus.subscribe(kind, handler)
    event_bus.start()

    # 1. Initialize core components
    position_aggregator = PositionAggregator()
    risk_engine = RiskEngine(event_bus=event_bus)
    kill_switch = KillSwitchV2()
    provider = build_capital_provider(env=os.getenv("CAPITAL_PROVIDER_ENV", "mock"))
    orchestrator_v2 = CapitalOrchestratorV2(CapitalLimitConfig(), event_bus=event_bus)
    snapshot = provider.get_snapshot()
    if snapshot:
        orchestrator_v2.update_snapshot(snapshot)

    async def _refresh_snapshot_loop():
        while True:
            await asyncio.sleep(5)
            snapshot = provider.get_snapshot()
            if snapshot:
                orchestrator_v2.update_snapshot(snapshot)

    snapshot_task = asyncio.create_task(_refresh_snapshot_loop())

    # 2. Configure and add risk guards
    risk_engine.add_guard(MaxNotionalGuard(max_notional=50000.0))
    risk_engine.add_guard(MaxExposureGuard(max_gross_exposure=100000.0))
    risk_engine.add_guard(MaxLeverageGuard(max_leverage=10.0))
    risk_engine.add_guard(OrderFrequencyGuard(max_orders=5, time_window_seconds=60))
    logger.info(f"RiskEngine configured with {len(risk_engine.get_guards())} guards.")

    exposure_aggregator = ExposureAggregator()
    exposure_service = ExposureService(exposure_aggregator)
    retry_policy = ExponentialBackoffPolicy()
    quote_engine = QuoteEngineV2()

    # 3. Initialize main engines
    execution_engine = ExecutionEngineV2(
        risk_engine=risk_engine,
        position_aggregator=position_aggregator,
        exposure_aggregator=exposure_aggregator,
        exposure_service=exposure_service,
        kill_switch=kill_switch,
        capital_orchestrator=orchestrator_v2,
        retry_policy=retry_policy,
        event_bus=event_bus,
    )
    logger.info("ExecutionEngine initialized.")

    # 4. Initialize status updater
    console_state = ConsoleState(
        execution_engine=execution_engine,
        quote_engine=quote_engine,
        exposure_service=exposure_service,
        capital_orchestrator=orchestrator_v2,
        scanner=None,
        risk_engine=risk_engine,
    )
    health_monitor = HealthMonitor(console_state=console_state, event_bus=event_bus)
    health_monitor.start()

    web_app = create_web_app(health_monitor, console_state)

    def _run_web_console() -> None:
        uvicorn.run(web_app, host="0.0.0.0", port=8080, log_level="info")

    web_thread = threading.Thread(target=_run_web_console, daemon=True)
    web_thread.start()
    logger.info("Web console listening on 0.0.0.0:8080.")

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
        await execution_engine.execute_order(valid_order_req)
        logger.info("✅ Valid order placed successfully.")
    except (ValueError, PermissionError) as e:
        logger.error(f"❌ Valid order failed unexpectedly: {e}")

    await asyncio.sleep(1)

    # b) Try to place an order that violates a risk rule (MaxNotionalGuard)
    print("\n2. Attempting to place an order that violates a risk rule...")
    try:
        invalid_order_req = OrderRequest(exchange="binance", symbol="BTC-PERP", side="buy", size=1, limit_price=60000)
        await execution_engine.execute_order(invalid_order_req)
    except (ValueError, PermissionError) as e:
        logger.warning(f"✅ Correctly blocked invalid order: {e}")

    await asyncio.sleep(1)

    # c) Activate Kill Switch and try to place an order
    print("\n3. Activating Kill Switch and attempting to place an order...")
    await kill_switch.activate(reason="Manual intervention required.")
    try:
        ks_order_req = OrderRequest(exchange="binance", symbol="ETH-PERP", side="buy", size=1, limit_price=3500)
        await execution_engine.execute_order(ks_order_req)
    except (ValueError, PermissionError) as e:
        logger.warning(f"✅ Correctly blocked order due to Kill Switch: {e}")

    # --- Shutdown ---
    await asyncio.sleep(5) # Let the updater run a bit longer
    console_updater.stop()
    health_monitor.stop()
    event_bus.stop()
    snapshot_task.cancel()
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
