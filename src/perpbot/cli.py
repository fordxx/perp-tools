from __future__ import annotations

import argparse
from datetime import datetime
from typing import List

import uvicorn
from rich.console import Console
from rich.table import Table

from perpbot.arbitrage.arbitrage_executor import ArbitrageExecutor
from perpbot.arbitrage.scanner import find_arbitrage_opportunities
from perpbot.arbitrage.volatility import SpreadVolatilityTracker
from perpbot.capital_orchestrator import CapitalOrchestrator
from perpbot.config import BotConfig, load_config
from perpbot.exchanges.base import provision_exchanges
from perpbot.monitoring.alerts import process_alerts
from perpbot.monitoring.market_data_bus import MarketDataBus
from perpbot.monitoring.web_console import create_web_app
from perpbot.models import TradingState
from perpbot.position_guard import PositionGuard
from perpbot.persistence import AlertRecorder, TradeRecorder
from perpbot.risk_manager import RiskManager
from perpbot.strategy.take_profit import TakeProfitStrategy

console = Console()


def render_quotes(state: TradingState) -> None:
    table = Table(title="最新行情")
    table.add_column("交易所")
    table.add_column("交易对")
    table.add_column("买价")
    table.add_column("卖价")
    for quote in state.quotes.values():
        table.add_row(quote.exchange, quote.symbol, f"{quote.bid:.2f}", f"{quote.ask:.2f}")
    console.print(table)


def render_arbitrage(state: TradingState) -> None:
    if not state.recent_arbitrage:
        console.print("[yellow]暂无达到阈值的套利机会[/yellow]")
        return
    table = Table(title="跨所套利价差")
    table.add_column("交易对")
    table.add_column("买入所")
    table.add_column("卖出所")
    table.add_column("数量")
    table.add_column("净收益率")
    table.add_column("预期收益")
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
    state.per_exchange_limit = cfg.per_exchange_limit
    guard = PositionGuard(
        max_risk_pct=cfg.max_risk_pct,
        assumed_equity=cfg.assumed_equity,
        cooldown_seconds=cfg.risk_cooldown_seconds,
    )
    capital = CapitalOrchestrator(
        wu_size=cfg.capital_wu_size,
        layer_targets=cfg.capital_layer_targets,
        layer_max_usage=cfg.capital_layer_max_usage,
        safe_layers=cfg.capital_safe_layers,
        allow_borrow_from_l5=cfg.capital_allow_borrow_from_l5,
        drawdown_limit_pct=cfg.capital_drawdown_limit_pct,
    )
    recorder = TradeRecorder(cfg.trade_record_path)
    alert_recorder = AlertRecorder(cfg.alert_record_path)
    volatility_tracker = SpreadVolatilityTracker(window_minutes=cfg.volatility_window_minutes)
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
        daily_loss_limit=cfg.daily_loss_limit,
        max_slippage_bps=cfg.max_slippage_bps,
        order_fill_timeout_seconds=cfg.order_fill_timeout_seconds,
        circuit_breaker_failures=cfg.circuit_breaker_failures,
        balance_concentration_pct=cfg.balance_concentration_pct,
        enabled=cfg.risk_enabled,
        risk_mode=cfg.risk_mode,
        risk_mode_presets=cfg.risk_mode_presets,
        manual_override_minutes=cfg.manual_override_minutes,
        manual_override_trades=cfg.manual_override_trades,
        daily_volume_target=cfg.daily_volume_target,
        max_notional_per_trade=cfg.max_notional_per_trade,
        max_total_notional_in_flight=cfg.max_total_notional_in_flight,
    )
    positions = []
    for ex in exchanges:
        try:
            ex_positions = ex.get_account_positions()
            positions.extend(ex_positions)
            guard.update_equity_from_positions(ex_positions)
            capital.update_equity(ex.name, cfg.assumed_equity)
        except Exception:
            # 某些交易所不支持该查询时忽略即可
            pass
    state.account_positions = positions
    market_bus = MarketDataBus(per_exchange_limit=cfg.per_exchange_limit)
    executor = ArbitrageExecutor(
        exchanges,
        guard,
        risk_manager=risk_manager,
        exchange_costs=cfg.exchange_costs,
        recorder=recorder,
        capital_orchestrator=capital,
    )
    strategy = TakeProfitStrategy(profit_target_pct=cfg.profit_target_pct)
    quotes = market_bus.collect_quotes(exchanges, cfg.symbols)
    reference_quote = next(iter(quotes), None)
    reference_price = reference_quote.mid if reference_quote else 0.0
    trade_notional = cfg.arbitrage_trade_size * reference_price
    min_profit_abs = trade_notional * cfg.arbitrage_min_profit_pct
    for quote in quotes:
        state.quotes[f"{quote.exchange}:{quote.symbol}"] = quote
        history = state.price_history.setdefault(quote.symbol, [])
        history.append((datetime.utcnow(), quote.mid))
        if len(history) > 500:
            del history[: len(history) - 500]
    risk_manager.update_equity(positions, state.quotes.values())
    risk_manager.evaluate_market(state.quotes.values())
    state.equity = risk_manager.last_equity
    state.pnl = risk_manager.last_equity - cfg.assumed_equity
    state.last_cycle_at = datetime.utcnow()
    if risk_manager.trading_halted:
        console.print(f"[red]交易已停止: {risk_manager.halt_reason}[/red]")
        return
    if risk_manager.is_frozen():
        console.print(f"[yellow]行情暂时冻结: {risk_manager.freeze_reason()}[/yellow]")
        return

    # 自动触发提醒与监控
    process_alerts(
        state,
        cfg.alerts,
        exchanges,
        notification_cfg=cfg.notifications,
        execute_orders=state.trading_enabled,
        start_trading_cb=lambda: setattr(state, "trading_enabled", True),
        alert_recorder=alert_recorder.record,
    )

    # 扫描套利机会
    opportunities = find_arbitrage_opportunities(
        state.quotes.values(),
        cfg.arbitrage_trade_size,
        min_profit_pct=cfg.arbitrage_min_profit_pct,
        default_maker_fee_bps=cfg.default_maker_fee_bps,
        default_taker_fee_bps=cfg.default_taker_fee_bps,
        default_slippage_bps=cfg.default_slippage_bps,
        failure_probability=cfg.failure_probability,
        exchange_costs=cfg.exchange_costs,
        min_profit_abs=min_profit_abs,
        volatility_tracker=volatility_tracker,
        high_vol_min_profit_pct=cfg.high_vol_min_profit_pct,
        low_vol_min_profit_pct=cfg.low_vol_min_profit_pct,
        volatility_high_threshold=cfg.volatility_high_threshold_pct,
        priority_threshold=cfg.priority_score_threshold,
        priority_weights=cfg.priority_weights,
        reliability_scores=cfg.reliability_scores,
    )
    state.recent_arbitrage = opportunities

    # 执行套利并启用对冲与风控
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
            console.print(f"[yellow]跳过套利: {reason or '风险拦截'}[/yellow]")
            continue

        result = executor.execute(op, positions=positions, quotes=state.quotes.values())
        if result.status == "filled":
            console.print(
                f"[green]完成套利 {op.symbol}: 买入 {op.buy_exchange} / 卖出 {op.sell_exchange}[/green]"
            )
        elif result.status == "blocked":
            console.print(f"[yellow]因风控跳过套利: {result.error}[/yellow]")
        else:
            console.print(f"[red]套利执行失败: {result.error}[/red]")

    # 使用简易动量信号触发策略
    for quote in state.quotes.values():
        spread_signal = (quote.ask - quote.bid) / quote.mid
        strategy.maybe_trade(state, next(ex for ex in exchanges if ex.name == quote.exchange), spread_signal, quote, cfg.position_size)

    # 自动平掉已达标的持仓
    closed = strategy.evaluate_positions(state, state.quotes.values(), exchanges)
    if closed:
        console.print(f"[green]已按目标平仓 {len(closed)} 笔仓位[/green]")

    render_quotes(state)
    render_arbitrage(state)
    if state.triggered_alerts:
        console.print("\n".join(state.triggered_alerts))


def main() -> None:
    parser = argparse.ArgumentParser(description="多交易所模块化交易机器人")
    parser.add_argument("command", choices=["cycle", "serve"], help="执行模式（cycle=单次循环，serve=启动控制台）")
    parser.add_argument("--config", default="config.example.yaml", help="YAML 配置文件路径")
    parser.add_argument("--port", type=int, default=8000, help="serve 模式下的控制台端口")
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
