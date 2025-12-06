from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from perpbot.arbitrage.arbitrage_executor import ArbitrageExecutor
from perpbot.arbitrage.scanner import find_arbitrage_opportunities
from perpbot.arbitrage.volatility import SpreadVolatilityTracker
from perpbot.config import BotConfig
from perpbot.exchanges.base import provision_exchanges, update_state_with_quotes
from perpbot.monitoring.alerts import process_alerts
from perpbot.models import ArbitrageOpportunity, Position, PriceQuote, TradingState
from perpbot.position_guard import PositionGuard
from perpbot.persistence import AlertRecorder, TradeRecorder
from perpbot.risk_manager import RiskManager
from perpbot.strategy.take_profit import TakeProfitStrategy

logger = logging.getLogger(__name__)


def _quote_to_dict(quote: PriceQuote) -> Dict:
    data = asdict(quote)
    data["ts"] = quote.ts.isoformat()
    if quote.order_book:
        data["order_book"] = {
            "bids": list(quote.order_book.bids),
            "asks": list(quote.order_book.asks),
        }
    return data


def _position_to_dict(position: Position) -> Dict:
    return {
        "id": position.id,
        "exchange": position.order.exchange,
        "symbol": position.order.symbol,
        "side": position.order.side,
        "size": position.order.size,
        "entry_price": position.order.price,
        "open_ts": position.open_ts.isoformat(),
        "closed_ts": position.closed_ts.isoformat() if position.closed_ts else None,
    }


def _arb_to_dict(op: ArbitrageOpportunity) -> Dict:
    data = asdict(op)
    data["discovered_at"] = op.discovered_at.isoformat()
    return data


def _series_to_list(points):
    return [{"ts": ts.isoformat(), "value": value} for ts, value in points]


class TradingService:
    """Background arbitrage loop with web-facing controls."""

    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.state = TradingState(min_profit_pct=cfg.arbitrage_min_profit_pct, per_exchange_limit=cfg.per_exchange_limit)
        self.state.trading_enabled = True
        self.exchanges = provision_exchanges()
        self.volatility_tracker = SpreadVolatilityTracker(window_minutes=cfg.volatility_window_minutes)
        self.recorder = TradeRecorder(cfg.trade_record_path)
        self.alert_recorder = AlertRecorder(cfg.alert_record_path)
        self.guard = PositionGuard(
            max_risk_pct=cfg.max_risk_pct,
            assumed_equity=cfg.assumed_equity,
            cooldown_seconds=cfg.risk_cooldown_seconds,
        )
        self.risk_manager = RiskManager(
            assumed_equity=cfg.assumed_equity,
            max_drawdown_pct=cfg.max_drawdown_pct,
            max_consecutive_failures=cfg.max_consecutive_failures,
            max_symbol_exposure_pct=cfg.max_symbol_exposure_pct,
            enforce_direction_consistency=cfg.enforce_direction_consistency,
            freeze_threshold_pct=cfg.freeze_threshold_pct,
            freeze_window_seconds=cfg.freeze_window_seconds,
            max_trade_risk_pct=cfg.max_risk_pct,
            daily_loss_limit_pct=cfg.daily_loss_limit_pct,
            max_slippage_bps=cfg.max_slippage_bps,
            order_fill_timeout_seconds=cfg.order_fill_timeout_seconds,
            circuit_breaker_failures=cfg.circuit_breaker_failures,
            balance_concentration_pct=cfg.balance_concentration_pct,
        )
        self.executor = ArbitrageExecutor(
            self.exchanges,
            self.guard,
            risk_manager=self.risk_manager,
            exchange_costs=self.cfg.exchange_costs,
            recorder=self.recorder,
        )
        self.strategy = TakeProfitStrategy(profit_target_pct=cfg.profit_target_pct)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._max_history = 500

    def start(self, trading_enabled: bool = True) -> None:
        self.state.trading_enabled = trading_enabled
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause_trading(self) -> None:
        self.state.trading_enabled = False

    def resume_trading(self) -> None:
        self.state.trading_enabled = True

    def shutdown(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def set_min_profit_pct(self, value: float) -> None:
        if value < 0:
            raise ValueError("Minimum profit threshold must be non-negative")
        self.state.min_profit_pct = value

    def _run_loop(self) -> None:  # pragma: no cover - runtime loop
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.exception("Trading cycle failed: %s", exc)
                self.state.status = f"error: {exc}"
            self._stop_event.wait(self.cfg.loop_interval_seconds)

    def run_cycle(self) -> None:
        with self._lock:
            update_state_with_quotes(self.state, self.exchanges, self.cfg.symbols)
            positions = self.risk_manager.collect_positions(self.exchanges)
            self.state.account_positions = positions
            self.guard.update_equity_from_positions(positions)
            equity = self.risk_manager.update_equity(positions, self.state.quotes.values())
            self.risk_manager.evaluate_market(self.state.quotes.values())
            self.state.equity = equity
            self.state.pnl = equity - self.cfg.assumed_equity
            self._record_equity_point(datetime.utcnow(), self.state.equity, self.state.pnl)
            self.state.last_cycle_at = datetime.utcnow()
            self.state.status = "running" if self.state.trading_enabled else "paused"

            # Surface arbitrage opportunities for the UI regardless of toggle
            opportunities = find_arbitrage_opportunities(
                self.state.quotes.values(),
                self.cfg.arbitrage_trade_size,
                min_profit_pct=self.state.min_profit_pct,
                default_maker_fee_bps=self.cfg.default_maker_fee_bps,
                default_taker_fee_bps=self.cfg.default_taker_fee_bps,
                default_slippage_bps=self.cfg.default_slippage_bps,
                failure_probability=self.cfg.failure_probability,
                exchange_costs=self.cfg.exchange_costs,
                min_profit_abs=self.cfg.arbitrage_trade_size * next(iter(self.state.quotes.values())).mid
                if self.state.quotes
                else 0.0,
                volatility_tracker=self.volatility_tracker,
                high_vol_min_profit_pct=self.cfg.high_vol_min_profit_pct,
                low_vol_min_profit_pct=self.cfg.low_vol_min_profit_pct,
                volatility_high_threshold=self.cfg.volatility_high_threshold_pct,
                priority_threshold=self.cfg.priority_score_threshold,
                priority_weights=self.cfg.priority_weights,
                reliability_scores=self.cfg.reliability_scores,
            )
            self.state.recent_arbitrage = opportunities

            process_alerts(
                self.state,
                self.cfg.alerts,
                self.exchanges,
                notification_cfg=self.cfg.notifications,
                execute_orders=self.state.trading_enabled,
                start_trading_cb=self.resume_trading,
                alert_recorder=self.alert_recorder.record,
            )

            if self.risk_manager.trading_halted:
                self.state.status = f"halted: {self.risk_manager.halt_reason}"
                return
            if self.risk_manager.is_frozen():
                self.state.status = self.risk_manager.freeze_reason() or "market frozen"
                return
            if not self.state.trading_enabled:
                return

            for op in opportunities:
                positions = self.risk_manager.collect_positions(self.exchanges)
                allowed, reason = self.risk_manager.can_trade(
                    op.symbol,
                    side="buy",
                    size=op.size,
                    price=op.buy_price,
                    positions=positions,
                    quotes=self.state.quotes.values(),
                )
                if not allowed:
                    logger.info("Skipping arbitrage due to risk: %s", reason)
                    continue
                self.executor.execute(op, positions=positions, quotes=self.state.quotes.values())

            for quote in self.state.quotes.values():
                spread_signal = (quote.ask - quote.bid) / quote.mid
                self.strategy.maybe_trade(
                    self.state,
                    next(ex for ex in self.exchanges if ex.name == quote.exchange),
                    spread_signal,
                    quote,
                    self.cfg.position_size,
                )

            closed = self.strategy.evaluate_positions(self.state, self.state.quotes.values(), self.exchanges)
            if closed:
                logger.info("Closed %s positions at target", len(closed))

    def snapshot(self) -> Dict:
        with self._lock:
            quotes = [_quote_to_dict(q) for q in self.state.quotes.values() if q.symbol in self.cfg.symbols]
            arbitrage = [_arb_to_dict(op) for op in self.state.recent_arbitrage]
            positions = [_position_to_dict(p) for p in self.state.account_positions or self.state.open_positions.values()]
            return {
                "status": self.state.status,
                "trading_enabled": self.state.trading_enabled,
                "min_profit_pct": self.state.min_profit_pct,
                "equity": self.state.equity,
                "pnl": self.state.pnl,
                "last_cycle_at": self.state.last_cycle_at.isoformat() if self.state.last_cycle_at else None,
                "equity_history": _series_to_list(self.state.equity_history),
                "pnl_history": _series_to_list(self.state.pnl_history),
                "quotes": quotes,
                "arbitrage": arbitrage,
                "positions": positions,
                "alerts": self.state.triggered_alerts,
            }

    def _record_equity_point(self, ts: datetime, equity: float, pnl: float) -> None:
        self.state.equity_history.append((ts, equity))
        self.state.pnl_history.append((ts, pnl))
        if len(self.state.equity_history) > self._max_history:
            self.state.equity_history = self.state.equity_history[-self._max_history :]
        if len(self.state.pnl_history) > self._max_history:
            self.state.pnl_history = self.state.pnl_history[-self._max_history :]


def create_web_app(cfg: BotConfig, service: Optional[TradingService] = None) -> FastAPI:
    service = service or TradingService(cfg)
    static_dir = Path(__file__).parent / "static"

    app = FastAPI(title="PerpBot Web Console", version="0.2.0")

    @app.on_event("startup")
    def _start() -> None:  # pragma: no cover - framework hook
        service.start(trading_enabled=True)

    @app.on_event("shutdown")
    def _shutdown() -> None:  # pragma: no cover - framework hook
        service.shutdown()

    @app.get("/api/overview")
    def overview():
        return service.snapshot()

    @app.get("/api/quotes")
    def quotes():
        return service.snapshot()["quotes"]

    @app.get("/api/arbitrage")
    def arbitrage():
        return service.snapshot()["arbitrage"]

    @app.get("/api/positions")
    def positions():
        return service.snapshot()["positions"]

    @app.post("/api/control/start")
    def start_trading():
        service.resume_trading()
        return {"trading_enabled": True}

    @app.post("/api/control/pause")
    def pause_trading():
        service.pause_trading()
        return {"trading_enabled": False}

    @app.post("/api/control/threshold")
    def update_threshold(payload: Dict[str, float]):
        if "min_profit_pct" not in payload:
            raise HTTPException(status_code=400, detail="min_profit_pct is required")
        try:
            service.set_min_profit_pct(float(payload["min_profit_pct"]))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"min_profit_pct": service.state.min_profit_pct}

    @app.get("/")
    def index():  # pragma: no cover - file response
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app
