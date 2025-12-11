<!-- Copilot instructions for AI coding agents working on PerpBot -->
# PerpBot — Copilot instructions

This file guides AI agents to be productive in this repository. Keep responses concise, reference files, and follow project patterns.

1. Big picture (what to change and why)
- Purpose: a modular multi-exchange perpetual arbitrage/trading framework implemented in Python 3.10+.
- Key boundaries: `src/perpbot/` contains core logic; `exchanges/` implements per-exchange clients; `strategy/`, `arbitrage/` contain signal and executor logic; `capital_orchestrator.py` manages the three-layer capital model.
- When changing behavior, update `capital_orchestrator.py`, `risk_manager.py`, and the relevant exchange client together to keep semantics consistent.

2. Important files and examples
- Entry points: `src/perpbot/cli.py` (single-cycle or serve), tests like `test_extended.py` for interactive exchange tests.
- Config: `config.example.yaml` → loaded by `src/perpbot/config.py::load_config()` into `BotConfig` dataclass. Use these fields for defaults and validate any new config keys there.
- Exchange base API: `src/perpbot/exchanges/base.py` (implementations must provide `connect()`, `get_current_price()`, `get_orderbook()`, `place_open_order()`, `place_close_order()`, `cancel_order()`, `get_active_orders()`, `get_account_positions()`, `get_account_balances()`). Concrete example: `src/perpbot/exchanges/paradex.py`.
- Capital model: `src/perpbot/capital_orchestrator.py` (three pools: wash/arb/reserve). Any strategy or executor that reserves funds must call `reserve_for_strategy` and `release`.

3. Runtime & developer workflows
- Quick checks and interactive tests:
  - Run the Extended exchange interactive test: `python test_extended.py --symbol ETH/USD --size 0.002 --side buy` (root workspace).
  - Many test scripts prepend `src` to `sys.path` (see `test_extended.py`), so run tests from repository root.
- Environment secrets:
  - Clients load credentials from environment variables and often use `.env` (e.g. `PARADEX_L2_PRIVATE_KEY`, `PARADEX_ACCOUNT_ADDRESS`, `EXTENDED_ENV`). See `src/perpbot/exchanges/paradex.py` for exact names.
- Dependencies: install via `pip install -r requirements.txt`. Some exchange SDKs (paradex-py, grvt, lighter SDKs) are optional; clients log clear errors when missing.

4. Project-specific conventions
- Synchronous-style client methods: many exchange clients expose blocking `connect()/get_current_price()/place_open_order()` methods (not always asyncio). Follow existing style when adding new exchanges.
- Error reporting: exchange clients may return `Order` objects with `id` values like `rejected` or `error-...` instead of raising; callers check `order.id.startswith('error')` or `rejected`. Mirror this pattern where appropriate.
- WebSocket threads: some clients start background asyncio loops in threads (see `paradex.py::_start_websocket_thread`). Be careful when editing — ensure clean start/stop and thread-safety.
- Config & dataclasses: prefer `BotConfig` fields and `config.example.yaml` for new parameters. Keep defaults in `src/perpbot/config.py`.

5. Integration points & testing
- Exchange SDKs: adding a new exchange should implement the `ExchangeClient` interface and ideally include a small `test_*.py` script similar to `test_extended.py` to validate connect/price/orderflow.
- Monitoring & alerts: modify `src/perpbot/monitoring/*` when adding new alert channels; `process_alerts` is called from `cli.py`.
- Persistence: trade and alert records are CSV by default (`data/trades.csv`, `data/alerts.csv`), controlled by `BotConfig`.

6. Safety and quick rules for agents
- Never enable real trading changes without documenting required env vars and a safe test procedure (point to `test_extended.py`).
- When editing order placement, preserve the existing safety checks: honor `_trading_enabled`, return `rejected` Order or raise with clear logs.
- When adding config keys, update `config.example.yaml`, `src/perpbot/config.py` defaults, and any code that consumes the key.

7. Useful code references (quick links)
- Capital orchestrator: [src/perpbot/capital_orchestrator.py](src/perpbot/capital_orchestrator.py)
- CLI / entry: [src/perpbot/cli.py](src/perpbot/cli.py)
- Config loader: [src/perpbot/config.py](src/perpbot/config.py)
- Paradex client example: [src/perpbot/exchanges/paradex.py](src/perpbot/exchanges/paradex.py)
- Exchange base: [src/perpbot/exchanges/base.py](src/perpbot/exchanges/base.py)
- Tests: [test_extended.py](test_extended.py)

If anything in these instructions is unclear or you'd like more detail (for example, a checklist for adding a new exchange client), tell me which section to expand.
