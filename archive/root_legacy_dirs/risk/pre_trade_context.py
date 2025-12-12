from dataclasses import dataclass, field

from exposure.exposure_model import ExposureModel


@dataclass
class PreTradeContext:
    exchange: str
    symbol: str
    side: str
    size: float
    price: float
    notional: float
    account_equity: float
    available_margin: float
    net_exposure: float
    gross_exposure: float
    leverage: float
    market_volatility: float
    recent_order_timestamps: list[float]
    symbol_exposure: ExposureModel = field(default_factory=ExposureModel.empty)
    exchange_exposure: ExposureModel = field(default_factory=ExposureModel.empty)
    global_exposure: ExposureModel = field(default_factory=ExposureModel.empty)
