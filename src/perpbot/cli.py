from __future__ import annotations

import argparse
from datetime import datetime
from typing import List

import uvicorn
from rich.console import Console
from rich.table import Table

from perpbot.arbitrage.arbitrage_executor import ArbitrageExecutor
from perpbot.arbitrage.scanner import find_arbitrage_opportunities
from perpbot.config import BotConfig, load_config
from perpbot.exchanges.base import provision_exchanges, update_state_with_quotes
from perpbot.monitoring.alerts import process_alerts
from perpbot.monitoring.web_console import create_web_app
from perpbot.models import TradingState
from perpbot.position_guard import PositionGuard
from perpbot.risk_manager import RiskManager
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
    table.add_column("Size")
    table.add_column("Net %")
    table.add_column("Exp. PnL")
    for op in state.recent_arbitrage:
        table.add_row(
            op.symbol,
            op.buy_exchange,
            op.sell_exchange,
            f"{op.size:.4f}",
            f"{op.net_profit_pct*100:.3f}%",
            f"{op.expected_pnl:.4f}",
        )
    console.print(table)


def single_cycle(cfg: BotConfig, state: TradingState) -> None:
    exchanges = provision_exchanges()
    state.min_profit_pct = cfg.arbitrage_min_profit_pct
    guard = PositionGuard(
        max_risk_pct=cfg.max_risk_pct,
        assumed_equity=cfg.assumed_equity,
        cooldown_seconds=cfg.risk_cooldown_seconds,
    )
    risk_manager = RiskManager(
        assumed_equity=cfg.assumed_equity,
        max_drawdown_pct=cfg.max_drawdown_pct,
        max_consecutive_failures=cfg.max_consecutive_failures,
        max_symbol_exposure_pct=cfg.max_symbol_exposure_pct,
        enforce_direction_consistency=cfg.enforce_direction_consistency,
        freeze_threshold_pct=cfg.freeze_threshold_pct,
        freeze_window_seconds=cfg.freeze_window_seconds,
        max_trade_risk_pct=cfg.max_risk_pct,
        daily_loss_limit_pct=cfg.daily_loss_limit_pct,
    )
    positions = []
    for ex in exchanges:
        try:
            ex_positions = ex.get_account_positions()
            positions.extend(ex_positions)
            guard.update_equity_from_positions(ex_positions)
        except Exception:
            # Non-fatal in case an exchange does not support the query
            pass
    state.account_positions = positions
    executor = ArbitrageExecutor(exchanges, guard, risk_manager=risk_manager, exchange_costs=cfg.exchange_costs)
    strategy = TakeProfitStrategy(profit_target_pct=cfg.profit_target_pct)
    update_state_with_quotes(state, exchanges, cfg.symbols)
    risk_manager.update_equity(positions, state.quotes.values())
    risk_manager.evaluate_market(state.quotes.values())
    state.equity = risk_manager.last_equity
    state.pnl = risk_manager.last_equity - cfg.assumed_equity
    state.last_cycle_at = datetime.utcnow()
    if risk_manager.trading_halted:
        console.print(f"[red]Trading halted: {risk_manager.halt_reason}[/red]")
        return
    if risk_manager.is_frozen():
        console.print(f"[yellow]Market temporarily frozen: {risk_manager.freeze_reason()}[/yellow]")
        return

    # Auto alerts and monitoring
    process_alerts(state, cfg.alerts, exchanges)

    # Discover arbitrage
    opportunities = find_arbitrage_opportunities(
        state.quotes.values(),
        cfg.arbitrage_trade_size,
        min_profit_pct=cfg.arbitrage_min_profit_pct,
        default_maker_fee_bps=cfg.default_maker_fee_bps,
        default_taker_fee_bps=cfg.default_taker_fee_bps,
        default_slippage_bps=cfg.default_slippage_bps,
        failure_probability=cfg.failure_probability,
        exchange_costs=cfg.exchange_costs,
        min_profit_abs=cfg.arbitrage_trade_size * next(iter(state.quotes.values())).mid
        if state.quotes
        else 0.0,
    )
    state.recent_arbitrage = opportunities

    # Execute opportunities with hedging and risk controls
    for op in opportunities:
        positions = risk_manager.collect_positions(exchanges)
        allowed, reason = risk_manager.can_trade(
            op.symbol,
            side="buy",
            size=op.size,
            price=op.buy_price,
            positions=positions,
            quotes=state.quotes.values(),
        )
        if not allowed:
            console.print(f"[yellow]Skipping arbitrage: {reason or 'risk block'}[/yellow]")
            continue

        result = executor.execute(op, positions=positions, quotes=state.quotes.values())
        if result.status == "filled":
            console.print(
                f"[green]Executed arbitrage {op.symbol}: buy {op.buy_exchange} / sell {op.sell_exchange}[/green]"
            )
        elif result.status == "blocked":
            console.print(f"[yellow]Skipped arbitrage due to risk guard: {result.error}[/yellow]")
        else:
            console.print(f"[red]Arbitrage execution failed: {result.error}[/red]")

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
        app = create_web_app(cfg)
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
