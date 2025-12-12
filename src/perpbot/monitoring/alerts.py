from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable, Iterable, List, Optional

import httpx

from perpbot.models import (
    AlertCondition,
    AlertNotificationConfig,
    AlertRecord,
    OrderRequest,
    TradingState,
)

logger = logging.getLogger(__name__)


def _pct_change(history: List[tuple], minutes: int) -> float:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    past = [p for p in history if p[0] <= cutoff]
    if not past or not history:
        return 0.0
    start = past[-1][1]
    latest = history[-1][1]
    if start == 0:
        return 0.0
    return (latest - start) / start


def _volatility(history: List[tuple], minutes: int) -> float:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    recent = [p[1] for p in history if p[0] >= cutoff]
    if len(recent) < 2:
        return 0.0
    mean = sum(recent) / len(recent)
    var = sum((p - mean) ** 2 for p in recent) / max(len(recent) - 1, 1)
    return var ** 0.5 / mean if mean else 0.0


def _send_notifications(message: str, cfg: AlertNotificationConfig, channels: Optional[List[str]]) -> None:
    active_channels = channels or ["console"]
    if cfg.console and "console" in active_channels:
        logger.info(message)
    if cfg.play_sound and "audio" in active_channels:
        print("\a", end="")
    if cfg.telegram_bot_token and cfg.telegram_chat_id and "telegram" in active_channels:
        url = f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage"
        try:
            httpx.post(url, json={"chat_id": cfg.telegram_chat_id, "text": message}, timeout=5.0)
        except Exception:
            logger.exception("Telegram notification failed")
    if cfg.lark_webhook and "lark" in active_channels:
        try:
            httpx.post(cfg.lark_webhook, json={"msg_type": "text", "content": {"text": message}}, timeout=5.0)
        except Exception:
            logger.exception("Lark notification failed")
    if cfg.webhook_url and "webhook" in active_channels:
        try:
            httpx.post(cfg.webhook_url, json={"text": message}, timeout=5.0)
        except Exception:
            logger.exception("Generic webhook notification failed")


def _evaluate_condition(alert: AlertCondition, state: TradingState, price: float) -> bool:
    if alert.condition == "price_above":
        return price >= (alert.price or 0)
    if alert.condition == "price_below":
        return price <= (alert.price or 0)
    if alert.condition == "range":
        return (alert.lower is None or price >= alert.lower) and (alert.upper is None or price <= alert.upper)
    history = state.price_history.get(alert.symbol, [])
    if alert.condition == "percent_change" and alert.change_pct is not None:
        pct = _pct_change(history, alert.lookback_minutes)
        return abs(pct) >= alert.change_pct
    if alert.condition == "spread" and alert.spread_symbol and alert.spread_threshold:
        other_quote = next((q for q in state.quotes.values() if q.symbol == alert.spread_symbol), None)
        if not other_quote:
            return False
        spread = (price - other_quote.mid) / other_quote.mid if other_quote.mid else 0
        target = alert.spread_threshold
        return spread >= target if (alert.direction or "above") == "above" else spread <= -target
    if alert.condition == "volatility" and alert.volatility_threshold is not None:
        vol = _volatility(history, alert.volatility_window)
        return vol >= alert.volatility_threshold
    return False


def process_alerts(
    state: TradingState,
    alerts: Iterable[AlertCondition],
    exchanges: Iterable,
    notification_cfg: Optional[AlertNotificationConfig] = None,
    execute_orders: bool = True,
    start_trading_cb: Optional[Callable[[], None]] = None,
    alert_recorder: Optional[Callable[[AlertRecord], None]] = None,
) -> List[str]:
    messages: List[str] = []
    notification_cfg = notification_cfg or AlertNotificationConfig()
    for alert in alerts:
        quote = next((q for q in state.quotes.values() if q.symbol == alert.symbol), None)
        if not quote:
            continue
        price = quote.mid
        matched = _evaluate_condition(alert, state, price)
        if not matched:
            continue
        message = f"Alert {alert.condition}: {alert.symbol} @ {price:.4f}"
        messages.append(message)
        state.triggered_alerts.append(message)
        record = AlertRecord(
            timestamp=datetime.utcnow(),
            symbol=alert.symbol,
            condition=alert.condition,
            price=price,
            message=message,
            success=True,
        )
        state.alert_history.append(record)
        if alert_recorder:
            alert_recorder(record)
        _send_notifications(message, notification_cfg, alert.channels)

        if alert.action == "start-trading" and start_trading_cb:
            start_trading_cb()
        if execute_orders and alert.action == "auto-order" and alert.side and alert.size > 0:
            exchange = next((ex for ex in exchanges if ex.name == quote.exchange), None)
            if exchange:
                try:
                    exchange.place_open_order(
                        OrderRequest(symbol=alert.symbol, side=alert.side, size=alert.size, limit_price=quote.mid)
                    )
                except Exception:
                    logger.exception("Auto-order for alert failed")
    return messages

