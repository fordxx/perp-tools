from dataclasses import dataclass


@dataclass
class Order:
    id: str
    exchange: str
    symbol: str
    side: str
    size: float
    price: float
    created_at: float
