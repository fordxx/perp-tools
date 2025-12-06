# PerpBot - Multi-Exchange Modular Trading Bot

This project bootstraps a modular automated trading bot that supports multiple exchanges (EdgeX, Backpack, Paradex, Aster, GRVT, Extended, OKX, and Binance). It provides simulated connectors, automatic take-profit execution, alerting, and cross-exchange arbitrage discovery alongside a minimal monitoring API.

## Features

- **Modular exchange layer** with stub clients for all requested venues.
- **Take-profit strategy** that opens positions and auto-closes after reaching a configurable profit threshold.
- **Arbitrage scanner** that discovers cross-exchange price edges and can be extended to execute legs automatically.
- **Smart alerts** that trigger notifications or optional auto-orders when price rules are met.
- **FastAPI dashboard** for real-time visibility into quotes, positions, alerts, and arbitrage opportunities.
- **Config-driven setup** via `config.example.yaml`.

## Project Layout

- `src/perpbot/models.py` — shared domain models for orders, positions, quotes, alerts, and state.
- `src/perpbot/exchanges/base.py` — exchange interface plus simulated clients for each exchange.
- `src/perpbot/strategy/take_profit.py` — take-profit trading loop and position lifecycle.
- `src/perpbot/arbitrage/scanner.py` — cross-exchange arbitrage detector.
- `src/perpbot/monitoring/alerts.py` — rule-based alert evaluation with optional auto-orders.
- `src/perpbot/monitoring/dashboard.py` — FastAPI monitoring API.
- `src/perpbot/cli.py` — CLI entrypoint to run a single trading cycle or launch the dashboard server.

## Getting Started

### Project Status

This repository ships a working simulation-oriented scaffold: the CLI, monitoring API, arbitrage detector, alerts, and take-profit loop all run end-to-end against the bundled mock exchange connectors. To trade live you still need to swap the simulated clients for real exchange integrations and harden the strategy/alert logic to your risk profile.

1. Install dependencies (Python 3.10+ recommended):

   ```bash
   pip install -r requirements.txt
   ```

2. Review and adjust settings in `config.example.yaml` (copy to `config.yaml` if desired).

3. Run a single trading/monitoring cycle to see quotes, arbitrage edges, and auto-take-profit behavior (set `PYTHONPATH=src` so the package is discoverable):

   ```bash
   PYTHONPATH=src python -m perpbot.cli cycle --config config.example.yaml
   ```

4. Launch the monitoring API (defaults to port 8000):

   ```bash
   PYTHONPATH=src python -m perpbot.cli serve --config config.example.yaml --port 8000
   ```

   The API exposes `GET /`, `/quotes`, `/positions`, `/arbitrage`, and `/alerts`.

### Notes

- The current exchange connectors are simulated; adapt `SimulatedExchangeClient` into real REST/WebSocket clients to trade live.
- Strategy signals are intentionally simple placeholders to illustrate lifecycle; replace with production-grade logic as needed.
