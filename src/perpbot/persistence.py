from __future__ import annotations

import csv
import logging
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime
from typing import Dict, Optional

from perpbot.models import ArbitrageOpportunity, ProfitResult

logger = logging.getLogger(__name__)


class TradeRecorder:
    """Persist trade outcomes to CSV or SQLite and expose simple stats."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.is_sqlite = path.endswith(".db") or path.endswith(".sqlite")
        if self.is_sqlite:
            self._init_db()
        else:
            self._init_csv()

    def _init_db(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    timestamp TEXT,
                    symbol TEXT,
                    buy_exchange TEXT,
                    sell_exchange TEXT,
                    buy_price REAL,
                    sell_price REAL,
                    amount REAL,
                    expected_profit REAL,
                    actual_profit REAL,
                    net_profit_pct REAL,
                    success INTEGER,
                    error_message TEXT
                );
                """
            )

    def _init_csv(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if not os.path.exists(self.path):
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "timestamp",
                        "symbol",
                        "buy_exchange",
                        "sell_exchange",
                        "buy_price",
                        "sell_price",
                        "amount",
                        "expected_profit",
                        "actual_profit",
                        "net_profit_pct",
                        "success",
                        "error_message",
                    ]
                )

    def record_trade(
        self,
        opportunity: ArbitrageOpportunity,
        success: bool,
        actual_profit: float,
        error_message: Optional[str] = None,
    ) -> None:
        ts = datetime.utcnow().isoformat()
        if self.is_sqlite:
            with sqlite3.connect(self.path) as conn:
                conn.execute(
                    """
                    INSERT INTO trades (
                        timestamp, symbol, buy_exchange, sell_exchange,
                        buy_price, sell_price, amount, expected_profit,
                        actual_profit, net_profit_pct, success, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts,
                        opportunity.symbol,
                        opportunity.buy_exchange,
                        opportunity.sell_exchange,
                        opportunity.buy_price,
                        opportunity.sell_price,
                        opportunity.size,
                        opportunity.expected_pnl,
                        actual_profit,
                        opportunity.net_profit_pct,
                        1 if success else 0,
                        error_message,
                    ),
                )
        else:
            with open(self.path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        ts,
                        opportunity.symbol,
                        opportunity.buy_exchange,
                        opportunity.sell_exchange,
                        opportunity.buy_price,
                        opportunity.sell_price,
                        opportunity.size,
                        opportunity.expected_pnl,
                        actual_profit,
                        opportunity.net_profit_pct,
                        int(success),
                        error_message or "",
                    ]
                )
        logger.info("Recorded trade for %s (%s)", opportunity.symbol, "success" if success else "fail")

    def stats(self) -> Dict[str, float]:
        if self.is_sqlite:
            with sqlite3.connect(self.path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM trades WHERE success=1")
                success_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM trades")
                total = cur.fetchone()[0] or 1
                cur.execute("SELECT AVG(actual_profit) FROM trades WHERE success=1")
                avg_profit = cur.fetchone()[0] or 0.0
                return {
                    "success_rate": success_count / total,
                    "avg_profit": avg_profit,
                }

        # CSV fallback reads all rows
        if not os.path.exists(self.path):
            return {"success_rate": 0.0, "avg_profit": 0.0}
        with open(self.path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        total = len(rows) or 1
        success_rows = [r for r in rows if r.get("success") == "1"]
        success_rate = len(success_rows) / total
        profits = [float(r.get("actual_profit", 0) or 0) for r in success_rows]
        avg_profit = sum(profits) / len(profits) if profits else 0.0
        return {"success_rate": success_rate, "avg_profit": avg_profit}


def profit_to_dict(profit: ProfitResult) -> dict:
    return asdict(profit)

