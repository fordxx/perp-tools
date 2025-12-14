import importlib
import inspect


def test_exchange_clients_not_abstract():
    # Lightweight static guard: ensure ExchangeClient implementers can be instantiated
    # (i.e., they don't miss abstract methods like setup_order_update_handler).
    configs = {
        "perpbot.exchanges.binance": "BinanceClient",
        "perpbot.exchanges.bitget": "BitgetClient",
        "perpbot.exchanges.bybit": "BybitClient",
        "perpbot.exchanges.aster": "AsterClient",
        "perpbot.exchanges.grvt": "GRVTClient",
        "perpbot.exchanges.extended": "ExtendedClient",
        "perpbot.exchanges.lighter": "LighterClient",
        "perpbot.exchanges.okx": "OKXClient",
        "perpbot.exchanges.paradex": "ParadexClient",
        "perpbot.exchanges.hyperliquid": "HyperliquidClient",
    }

    for module_name, class_name in configs.items():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            # Many exchange modules have optional dependencies; skip if not importable.
            continue
        cls = getattr(module, class_name, None)
        if cls is None:
            continue
        assert inspect.isclass(cls)
        assert not inspect.isabstract(cls), f"{module_name}.{class_name} is abstract (missing required methods)"

