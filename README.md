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
- `src/perpbot/arbitrage/scanner.py` — cross-exchange arbitrage detector with depth-aware, cost-adjusted signal generation.
- `src/perpbot/monitoring/alerts.py` — rule-based alert evaluation with optional auto-orders.
- `src/perpbot/monitoring/dashboard.py` — FastAPI monitoring API.
- `src/perpbot/cli.py` — CLI entrypoint to run a single trading cycle or launch the dashboard server.

## Getting Started

### Project Status

This repository ships a working simulation-oriented scaffold: the CLI, monitoring API, arbitrage detector, alerts, and take-profit loop all run end-to-end against the bundled mock exchange connectors. Real REST/WebSocket connectors for Binance USDT-M futures and OKX SWAP are provided and will be used automatically when credentials are present.

1. Install dependencies (Python 3.10+ recommended):

   ```bash
   pip install -r requirements.txt
   ```

2. Review and adjust settings in `config.example.yaml` (copy to `config.yaml` if desired).

3. Run a single trading/monitoring cycle to see quotes, cost-adjusted arbitrage edges, and auto-take-profit behavior (set `PYTHONPATH=src` so the package is discoverable):

   ```bash
   PYTHONPATH=src python -m perpbot.cli cycle --config config.example.yaml
   ```

4. Launch the monitoring API (defaults to port 8000):

   ```bash
   PYTHONPATH=src python -m perpbot.cli serve --config config.example.yaml --port 8000
   ```

   The API exposes `GET /`, `/quotes`, `/positions`, `/arbitrage`, and `/alerts`.

### Environment & credentials

Create a `.env` file with the keys you intend to use. When absent, the bot falls back to simulated connectors.

```env
# Binance USDT-M futures
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_ENV=testnet  # or "live"

# OKX perpetual swaps
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_ENV=testnet  # or "live"
```

### Notes

- Binance and OKX connectors use official REST + WebSocket APIs with error handling and logging. Without credentials the bot runs in simulation mode.
- Strategy signals are intentionally simple placeholders to illustrate lifecycle; replace with production-grade logic as needed.
