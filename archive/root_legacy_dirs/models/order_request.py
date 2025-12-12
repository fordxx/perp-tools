from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderRequest:
    exchange: str
    symbol: str
    side: str
    size: float
    limit_price: Optional[float] = None
    strategy: str = "default"
    is_fallback: bool = False
