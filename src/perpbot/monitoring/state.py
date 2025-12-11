from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from perpbot.models import PriceQuote


@dataclass
class WashTaskView:
    task_id: str
    pair: str
    symbol: str
    notional: float
    status: str
    hold_seconds: float = 0.0
    filled_volume: float = 0.0
    fee_paid: float = 0.0
    floating_pnl: float = 0.0
    risk_flags: Dict[str, bool] = field(default_factory=dict)
    start_ts: datetime = field(default_factory=datetime.utcnow)
    last_update_ts: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ExchangeRuntime:
    equity: float = 0.0
    available_margin: float = 0.0
    wash_usage: float = 0.0
    long_short_balanced: bool = True
    funding_rate: float = 0.0
    api_latency_ms: float = 0.0
    risk_warnings: List[str] = field(default_factory=list)
    active_wash_tasks: int = 0
    active_notional: float = 0.0


class MonitoringState:
    """集中存储监控与面板需要的实时数据。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.system_status: str = "paused"
        self.risk_mode: str = "balanced"
        self.daily_volume_usd: float = 0.0
        self.daily_fee_usd: float = 0.0
        self.daily_pnl_usd: float = 0.0
        self.daily_loss_limit_usd: float = 0.0
        self.remaining_loss_buffer_usd: float = 0.0
        self.capital_pools: Dict[str, Dict[str, Dict[str, float]]] = {}
        self.exchanges: Dict[str, ExchangeRuntime] = {}
        self.wash_tasks: Dict[str, WashTaskView] = {}
        self.risk_radar: Dict[str, object] = {
            "fast_market_symbols": [],
            "latency_anomalies": [],
            "funding_blackout": {},
            "consecutive_failures": 0,
            "auto_paused": False,
            "manual_override_active": False,
        }
        self.quotes: Dict[str, Dict[str, object]] = {}

    def update_system(self, status: str, risk_mode: Optional[str] = None, daily_loss_limit: Optional[float] = None,
                      remaining_loss_buffer: Optional[float] = None) -> None:
        with self._lock:
            self.system_status = status
            if risk_mode:
                self.risk_mode = risk_mode
            if daily_loss_limit is not None:
                self.daily_loss_limit_usd = daily_loss_limit
            if remaining_loss_buffer is not None:
                self.remaining_loss_buffer_usd = remaining_loss_buffer

    def update_capital(self, snapshot: Dict[str, Dict[str, Dict[str, float]]]) -> None:
        with self._lock:
            self.capital_pools = snapshot

    def update_exchange_state(
        self,
        exchange: str,
        equity: float,
        available_margin: float,
        wash_usage: float,
        long_short_balanced: bool,
        funding_rate: float,
        api_latency_ms: float,
        risk_warnings: Optional[List[str]] = None,
        active_wash_tasks: int = 0,
        active_notional: float = 0.0,
    ) -> None:
        with self._lock:
            self.exchanges[exchange] = ExchangeRuntime(
                equity=equity,
                available_margin=available_margin,
                wash_usage=wash_usage,
                long_short_balanced=long_short_balanced,
                funding_rate=funding_rate,
                api_latency_ms=api_latency_ms,
                risk_warnings=risk_warnings or [],
                active_wash_tasks=active_wash_tasks,
                active_notional=active_notional,
            )

    def register_wash_task(self, task: WashTaskView) -> None:
        with self._lock:
            self.wash_tasks[task.task_id] = task

    def update_wash_task(self, task_id: str, **kwargs) -> None:
        with self._lock:
            task = self.wash_tasks.get(task_id)
            if not task:
                return
            for k, v in kwargs.items():
                if hasattr(task, k):
                    setattr(task, k, v)
            task.last_update_ts = datetime.utcnow()

    def finalize_wash_task(self, task_id: str, volume: float, fee: float, pnl: float) -> None:
        with self._lock:
            task = self.wash_tasks.get(task_id)
            if task:
                task.filled_volume = volume
                task.fee_paid = fee
                task.floating_pnl = pnl
                task.status = "done"
                task.last_update_ts = datetime.utcnow()
            self.daily_volume_usd += volume
            self.daily_fee_usd += fee
            self.daily_pnl_usd += pnl

    def update_risk_radar(self, radar: Dict[str, object]) -> None:
        with self._lock:
            self.risk_radar.update(radar)

    def update_quote(self, quote: PriceQuote) -> None:
        with self._lock:
            ex_quotes = self.quotes.setdefault(quote.exchange, {})
            ex_quotes[quote.symbol] = {
                "bid": quote.bid,
                "ask": quote.ask,
                "spread": quote.ask - quote.bid,
                "funding": quote.funding_rate,
                "vol_5s": quote.slippage_bps,  # 占位字段，后续可接入真实短周期波动
                "vol_10s": quote.slippage_bps,
                "ts": quote.ts.isoformat(),
            }

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "system": {
                    "status": self.system_status,
                    "risk_mode": self.risk_mode,
                    "daily_volume_usd": self.daily_volume_usd,
                    "daily_fee_usd": self.daily_fee_usd,
                    "daily_pnl_usd": self.daily_pnl_usd,
                    "daily_loss_limit_usd": self.daily_loss_limit_usd,
                    "remaining_loss_buffer_usd": self.remaining_loss_buffer_usd,
                },
                "capital": self.capital_pools,
                "exchanges": {k: vars(v) for k, v in self.exchanges.items()},
                "wash_tasks": {k: self._task_to_dict(t) for k, t in self.wash_tasks.items()},
                "risk_radar": self.risk_radar,
                "quotes": self.quotes,
            }

    def _task_to_dict(self, task: WashTaskView) -> Dict[str, object]:
        return {
            "task_id": task.task_id,
            "pair": task.pair,
            "symbol": task.symbol,
            "notional": task.notional,
            "status": task.status,
            "hold_seconds": task.hold_seconds,
            "filled_volume": task.filled_volume,
            "fee_paid": task.fee_paid,
            "floating_pnl": task.floating_pnl,
            "risk_flags": task.risk_flags,
            "start_ts": task.start_ts.isoformat(),
            "last_update_ts": task.last_update_ts.isoformat(),
        }
