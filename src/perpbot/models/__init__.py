# Expose both new and legacy models
from .order import Order
from .order_request import OrderRequest
from .position_snapshot import UnifiedPosition

# Import legacy classes from models_old.py
try:
    from ..models_old import Position, PriceQuote, Side, OrderBookDepth, Balance, ExchangeCost, ArbitrageOpportunity
except ImportError:
    pass

__all__ = ["Order", "OrderRequest", "UnifiedPosition", "Position", "PriceQuote", "Side"]
