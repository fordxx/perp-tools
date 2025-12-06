from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from perpbot.arbitrage.arbitrage_executor import ArbitrageExecutor
from perpbot.arbitrage.scanner import find_arbitrage_opportunities
from perpbot.arbitrage.volatility import SpreadVolatilityTracker
from perpbot.capital_orchestrator import CapitalOrchestrator
from perpbot.config import BotConfig
from perpbot.exchanges.base import provision_exchanges
from perpbot.monitoring.alerts import process_alerts
from perpbot.monitoring.market_data_bus import MarketDataBus
from perpbot.monitoring.state import MonitoringState
from perpbot.models import ArbitrageOpportunity, AlertRecord, Position, PriceQuote, TradingState
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


def _alert_to_dict(record: AlertRecord) -> Dict:
    return {
        "timestamp": record.timestamp.isoformat(),
        "symbol": record.symbol,
        "condition": record.condition,
        "price": record.price,
        "message": record.message,
        "success": record.success,
    }


def _arb_to_dict(op: ArbitrageOpportunity, weights: Optional[dict] = None) -> Dict:
    data = asdict(op)
    data["discovered_at"] = op.discovered_at.isoformat()
    try:
        data["priority_score"] = op.priority_score(weights=weights)
    except Exception:
        data["priority_score"] = None
    return data


def _series_to_list(points):
    return [{"ts": ts.isoformat(), "value": value} for ts, value in points]


class TradingService:
    """Background arbitrage loop with web-facing controls."""

    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.state = TradingState(min_profit_pct=cfg.arbitrage_min_profit_pct, per_exchange_limit=cfg.per_exchange_limit)
        self.state.trading_enabled = True
        self.monitoring = MonitoringState()
        self.market_bus = MarketDataBus(self.monitoring, per_exchange_limit=cfg.per_exchange_limit)
        self.exchanges = provision_exchanges()
        self.volatility_tracker = SpreadVolatilityTracker(window_minutes=cfg.volatility_window_minutes)
        self.recorder = TradeRecorder(cfg.trade_record_path)
        self.alert_recorder = AlertRecorder(cfg.alert_record_path)
        self.guard = PositionGuard(
            max_risk_pct=cfg.max_risk_pct,
            assumed_equity=cfg.assumed_equity,
            cooldown_seconds=cfg.risk_cooldown_seconds,
        )
        self.capital = CapitalOrchestrator(
            wu_size=cfg.capital_wu_size,
            layer_targets=cfg.capital_layer_targets,
            layer_max_usage=cfg.capital_layer_max_usage,
            safe_layers=cfg.capital_safe_layers,
            allow_borrow_from_l5=cfg.capital_allow_borrow_from_l5,
            drawdown_limit_pct=cfg.capital_drawdown_limit_pct,
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
        self.executor = ArbitrageExecutor(
            self.exchanges,
            self.guard,
            risk_manager=self.risk_manager,
            exchange_costs=self.cfg.exchange_costs,
            recorder=self.recorder,
            capital_orchestrator=self.capital,
        )
        for ex in self.exchanges:
            try:
                self.capital.update_equity(ex.name, cfg.assumed_equity)
            except Exception:
                pass
        self.strategy = TakeProfitStrategy(profit_target_pct=cfg.profit_target_pct)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._max_history = 500
        self._max_alert_history = 200

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
            quotes = self.market_bus.collect_quotes(self.exchanges, self.cfg.symbols)
            for quote in quotes:
                self.state.quotes[f"{quote.exchange}:{quote.symbol}"] = quote
                history = self.state.price_history.setdefault(quote.symbol, [])
                history.append((datetime.utcnow(), quote.mid))
                if len(history) > 500:
                    del history[: len(history) - 500]
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
            self._refresh_monitoring(quotes)

            # 即便暂停交易也向前端展示套利机会
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
            if len(self.state.alert_history) > self._max_alert_history:
                self.state.alert_history = self.state.alert_history[-self._max_alert_history :]
            if len(self.state.triggered_alerts) > self._max_alert_history:
                self.state.triggered_alerts = self.state.triggered_alerts[-self._max_alert_history :]

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
            arbitrage = [_arb_to_dict(op, self.cfg.priority_weights) for op in self.state.recent_arbitrage]
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
                "alert_history": [_alert_to_dict(a) for a in self.state.alert_history[-self._max_alert_history :]],
                "trade_stats": self.recorder.stats() if self.recorder else {},
                "monitoring": self.monitoring.snapshot(),
            }

    def _refresh_monitoring(self, quotes: Optional[list] = None) -> None:
        snapshot = self.capital.current_snapshot()
        self.monitoring.update_capital(snapshot)
        if quotes:
            for quote in quotes:
                self.monitoring.update_quote(quote)
        # 汇总交易所运行态
        for ex in self.exchanges:
            cap = snapshot.get(ex.name, {})
            wash = cap.get("wash", {})
            arb = cap.get("arb", {})
            meta = cap.get("meta", {})
            active_tasks = sum(
                1
                for t in self.monitoring.wash_tasks.values()
                if ex.name in t.pair and t.status not in {"done", "blocked"}
            )
            active_notional = sum(t.notional for t in self.monitoring.wash_tasks.values() if ex.name in t.pair and t.status not in {"done", "blocked"})
            self.monitoring.update_exchange_state(
                ex.name,
                equity=float(meta.get("equity", 0.0)),
                available_margin=float(wash.get("available", 0.0)),
                wash_usage=float(wash.get("allocated", 0.0)),
                long_short_balanced=True,
                funding_rate=0.0,
                api_latency_ms=0.0,
                risk_warnings=[],
                active_wash_tasks=active_tasks,
                active_notional=active_notional,
            )
        remaining_loss = 0.0
        if self.risk_manager.daily_loss_limit > 0 and self.risk_manager._daily_anchor_equity:
            remaining_loss = max(
                0.0,
                self.risk_manager.daily_loss_limit
                - max(self.risk_manager._daily_anchor_equity - self.risk_manager.last_equity, 0.0),
            )
        self.monitoring.update_system(
            status=self.state.status,
            risk_mode=self.risk_manager.risk_mode,
            daily_loss_limit=self.risk_manager.daily_loss_limit,
            remaining_loss_buffer=remaining_loss,
        )
        self.monitoring.update_risk_radar(
            {
                "consecutive_failures": self.risk_manager.consecutive_failures,
                "auto_paused": self.risk_manager.trading_halted,
                "manual_override_active": self.risk_manager._override_active(),
            }
        )

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

    @app.get("/api/alerts")
    def alerts():
        return service.snapshot().get("alert_history", [])

    @app.get("/api/monitoring")
    def monitoring():
        return service.snapshot().get("monitoring", {})

    @app.get("/api/monitoring/exchanges")
    def monitoring_exchanges():
        return service.snapshot().get("monitoring", {}).get("exchanges", {})

    @app.get("/api/monitoring/wash_tasks")
    def monitoring_wash_tasks():
        return service.snapshot().get("monitoring", {}).get("wash_tasks", {})

    @app.get("/api/monitoring/radar")
    def monitoring_radar():
        return service.snapshot().get("monitoring", {}).get("risk_radar", {})

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

    @app.websocket("/ws")
    async def websocket_updates(websocket: WebSocket):  # pragma: no cover - runtime socket
        await websocket.accept()
        interval = max(1.0, cfg.loop_interval_seconds)
        try:
            while True:
                await websocket.send_json(service.snapshot())
                await asyncio.sleep(interval)
        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        except Exception as exc:
            logger.exception("WebSocket error: %s", exc)
            await websocket.close()

    @app.get("/")
    def index():  # pragma: no cover - file response
        return FileResponse(static_dir / "index.html")

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    return app
