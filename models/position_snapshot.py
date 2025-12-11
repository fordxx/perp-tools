from dataclasses import dataclass


@dataclass
class UnifiedPosition:
    exchange: str
    symbol: str
    side: str  # "LONG" / "SHORT"
    size: float  # 原始数量
    notional: float  # 统一 USD 等值
    entry_price: float
    mark_price: float
    unrealized_pnl: float