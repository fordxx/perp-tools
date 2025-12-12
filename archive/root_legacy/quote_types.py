from dataclasses import dataclass


@dataclass
class RawQuote:
    exchange: str
    symbol: str
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    timestamp: float


@dataclass
class NormalizedQuote:
    exchange: str
    symbol: str
    best_bid: float
    best_ask: float
    mid_price: float
    spread_bps: float
    timestamp: float

    @staticmethod
    def from_raw(raw: "RawQuote") -> "NormalizedQuote":
        if raw.bid <= 0 or raw.ask <= 0:
            raise ValueError("Bid and ask must be positive to normalize.")

        if raw.bid >= raw.ask:
            raise ValueError("Bid must be strictly less than ask to normalize.")

        mid_price = NormalizedQuote.compute_mid(raw.bid, raw.ask)
        spread_bps = ((raw.ask - raw.bid) / mid_price) * 10000 if mid_price else 0.0

        return NormalizedQuote(
            exchange=raw.exchange,
            symbol=raw.symbol,
            best_bid=raw.bid,
            best_ask=raw.ask,
            mid_price=mid_price,
            spread_bps=spread_bps,
            timestamp=raw.timestamp,
        )

    @staticmethod
    def compute_mid(bid: float, ask: float) -> float:
        return (bid + ask) / 2.0
