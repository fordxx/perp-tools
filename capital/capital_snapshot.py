from dataclasses import dataclass
from typing import Dict
import time


@dataclass
class ExchangeCapitalSnapshot:
    """
    Represents a unified view of capital for a single exchange.
    """
    exchange: str
    equity: float              # 总权益 (Total Equity)
    available_balance: float   # 可用余额（可下单）(Available Balance for trading)
    open_notional: float = 0.0
    used_margin: float         # 已用保证金 (Used Margin)
    unrealized_pnl: float      # 未实现盈亏 (Unrealized PnL)
    realized_pnl: float        # 已实现盈亏 (Realized PnL)
    open_notional: float       # 在途名义 (Open Notional)
    leverage: float | None     # 杠杆倍数 (Leverage)
    timestamp: float           # 快照时间戳 (Timestamp of the snapshot)


@dataclass
class GlobalCapitalSnapshot:
    """
    Represents a global unified view of capital across all exchanges.
    """
    per_exchange: Dict[str, ExchangeCapitalSnapshot]
    total_equity: float
    total_unrealized_pnl: float
    total_realized_pnl: float
    total_open_notional: float
    timestamp: float

    @staticmethod
    def from_per_exchange(snapshots: Dict[str, ExchangeCapitalSnapshot]) -> "GlobalCapitalSnapshot":
        total_equity = sum(s.equity for s in snapshots.values())
        total_unrealized_pnl = sum(s.unrealized_pnl for s in snapshots.values())
        total_realized_pnl = sum(s.realized_pnl for s in snapshots.values())
        total_open_notional = sum(s.open_notional for s in snapshots.values())
        max_timestamp = max((s.timestamp for s in snapshots.values()), default=time.time())
        return GlobalCapitalSnapshot(
            per_exchange=snapshots,
            total_equity=total_equity,
            total_unrealized_pnl=total_unrealized_pnl,
            total_realized_pnl=total_realized_pnl,
            total_open_notional=total_open_notional,
            timestamp=max_timestamp,
        )
