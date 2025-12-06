from __future__ import annotations

import argparse
from typing import List

import uvicorn
from rich.console import Console
from rich.table import Table

from perpbot.arbitrage.scanner import find_arbitrage_opportunities
from perpbot.config import BotConfig, load_config
from perpbot.exchanges.base import provision_exchanges, update_state_with_quotes
from perpbot.monitoring.alerts import process_alerts
from perpbot.monitoring.dashboard import create_dashboard_app
from perpbot.models import TradingState
from perpbot.strategy.take_profit import TakeProfitStrategy

console = Console()


def render_quotes(state: TradingState) -> None:
    table = Table(title="Latest Quotes")
    table.add_column("Exchange")
    table.add_column("Symbol")
    table.add_column("Bid")
    table.add_column("Ask")
    for quote in state.quotes.values():
        table.add_row(quote.exchange, quote.symbol, f"{quote.bid:.2f}", f"{quote.ask:.2f}")
    console.print(table)


def render_arbitrage(state: TradingState) -> None:
    if not state.recent_arbitrage:
        console.print("[yellow]No arbitrage edges above threshold[/yellow]")
        return
    table = Table(title="Cross-exchange edges")
    table.add_column("Symbol")
    table.add_column("Buy @")
    table.add_column("Sell @")
    table.add_column("Edge")
    for op in state.recent_arbitrage:
        table.add_row(op.symbol, op.buy_exchange, op.sell_exchange, f"{op.edge*100:.2f}%")
    console.print(table)


def single_cycle(cfg: BotConfig, state: TradingState) -> None:
    exchanges = provision_exchanges()
    strategy = TakeProfitStrategy(profit_target_pct=cfg.profit_target_pct)
    update_state_with_quotes(state, exchanges, cfg.symbols)

    # Auto alerts and monitoring
    process_alerts(state, cfg.alerts, exchanges)

    # Discover arbitrage
    opportunities = find_arbitrage_opportunities(state.quotes.values(), cfg.arbitrage_edge)
    state.recent_arbitrage = opportunities

    # Fire strategy using a lightweight momentum signal derived from spread
    for quote in state.quotes.values():
        spread_signal = (quote.ask - quote.bid) / quote.mid
        strategy.maybe_trade(state, next(ex for ex in exchanges if ex.name == quote.exchange), spread_signal, quote, cfg.position_size)

    # Auto close profitable positions
    closed = strategy.evaluate_positions(state, state.quotes.values(), exchanges)
    if closed:
        console.print(f"[green]Closed {len(closed)} positions at target[/green]")

    render_quotes(state)
    render_arbitrage(state)
    if state.triggered_alerts:
        console.print("\n".join(state.triggered_alerts))


def main() -> None:
    parser = argparse.ArgumentParser(description="Modular multi-exchange trading bot")
    parser.add_argument("command", choices=["cycle", "serve"], help="Action to perform")
    parser.add_argument("--config", default="config.example.yaml", help="Path to YAML config")
    parser.add_argument("--port", type=int, default=8000, help="Dashboard port for serve mode")
    args = parser.parse_args()

    cfg = load_config(args.config)
    state = TradingState()

    if args.command == "cycle":
        single_cycle(cfg, state)
    elif args.command == "serve":
        # warm up some data for the dashboard
        single_cycle(cfg, state)
        app = create_dashboard_app(state)
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
