# PerpBot - Multi-Exchange Modular Trading Bot

This project bootstraps a modular automated trading bot that supports multiple exchanges (EdgeX, Backpack, Paradex, Aster, GRVT, Extended, OKX, and Binance). It provides modular real exchange connectors, automatic take-profit execution, alerting, and cross-exchange arbitrage discovery alongside a minimal monitoring API.

## Features

- **Modular exchange layer** with stub clients for all requested venues.
- **Take-profit strategy** that opens positions and auto-closes after reaching a configurable profit threshold.
- **Arbitrage scanner and executor** that discovers cross-exchange price edges, enforces risk limits, and fires two-sided orders with automatic hedging.
- **Smart alerts** that trigger notifications or optional auto-orders when price rules are met.
- **FastAPI web console** with live BTC/ETH quotes across exchanges, an arbitrage opportunity panel, real-time position view, an equity/PnL curve, and controls to start/pause arbitrage or retune the minimum profit threshold.
- **Config-driven setup** via `config.example.yaml`.

## Project Layout

- `src/perpbot/models.py` — shared domain models for orders, positions, quotes, alerts, and state.
- `src/perpbot/exchanges/base.py` — unified exchange interface and real clients for each venue.
- `src/perpbot/strategy/take_profit.py` — take-profit trading loop and position lifecycle.
- `src/perpbot/arbitrage/scanner.py` — cross-exchange arbitrage detector with depth-aware, cost-adjusted signal generation.
- `src/perpbot/arbitrage/arbitrage_executor.py` — two-sided arbitrage executor with hedging when a leg fails.
- `src/perpbot/position_guard.py` — per-trade risk limits and cooldown enforcement.
- `src/perpbot/risk_manager.py` — portfolio-level guardrails for per-trade caps, drawdown, daily loss, exposure, direction consistency, streak limits, and fast-market freezes.
- `src/perpbot/monitoring/alerts.py` — rule-based alert evaluation with optional auto-orders.
- `src/perpbot/monitoring/web_console.py` — FastAPI web console and background trading service.
- `src/perpbot/monitoring/static/index.html` — lightweight HTML dashboard for real-time control and visibility.
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

4. Launch the web console (defaults to port 8000):

   ```bash
   PYTHONPATH=src python -m perpbot.cli serve --config config.example.yaml --port 8000
   ```

   Open `http://localhost:8000/` to view the live BTC/ETH board, arbitrage spreads, open positions, and the rolling equity/PnL curve. Toggle arbitrage on/off with one click or adjust the profit threshold. API endpoints are available under `/api/*` for programmatic control (`/api/overview`, `/api/control/start`, `/api/control/pause`, `/api/control/threshold`, plus `/api/quotes`, `/api/arbitrage`, and `/api/positions`).

### Risk and execution settings

`config.example.yaml` exposes `max_risk_pct`, `assumed_equity`, and `risk_cooldown_seconds` to cap per-trade exposure (default 5% of account), provide an equity seed when balances are unavailable, and pause trading briefly after a failed arbitrage attempt. Additional risk controls include `max_drawdown_pct`, `daily_loss_limit_pct` (default 8% stop for the UTC day), `max_consecutive_failures` (halts after three misses), `max_symbol_exposure_pct`, `enforce_direction_consistency`, and freeze settings (default 0.5% move inside one second) to halt trading during violent moves. `loop_interval_seconds` controls how often the background loop refreshes quotes and evaluates spreads, while `arbitrage_min_profit_pct` can be tuned live from the web console.

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
