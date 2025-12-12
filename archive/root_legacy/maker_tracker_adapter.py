import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from models.order import Order
from models.order_request import OrderRequest

logger = logging.getLogger(__name__)


@dataclass
class MakerEstimation:
    """
    Provides an estimation for a potential maker order.
    """

    should_place_maker: bool
    estimated_fill_time_seconds: Optional[float] = None
    reason: Optional[str] = None


class BaseMakerTracker(ABC):
    """
    Abstract base class for a module that tracks maker order performance
    and provides estimations for future maker orders.
    """

    @abstractmethod
    def estimate_maker_order(self, request: OrderRequest) -> MakerEstimation:
        """
        Analyzes market conditions and historical data to decide if placing a maker order is a good strategy.
        """
        raise NotImplementedError

    @abstractmethod
    def track_order(self, order: Order):
        """Starts tracking a newly placed maker order."""
        raise NotImplementedError

    @abstractmethod
    def on_fill(self, order_id: str, filled_size: float, fill_price: float):
        """Records a fill event for a tracked maker order."""
        raise NotImplementedError

    @abstractmethod
    def on_cancel(self, order_id: str):
        """Records that a tracked maker order was cancelled."""
        raise NotImplementedError


class MakerTrackerAdapter(BaseMakerTracker):
    """
    Adapter to integrate the maker_tracker and maker_fill_estimator from the BOTZF branch.

    This class acts as a placeholder. The actual complex logic for estimation and tracking
    would be implemented by wrapping the original modules.
    """

    def __init__(self):
        logger.info("MakerTrackerAdapter initialized (simulation mode).")

    def estimate_maker_order(self, request: OrderRequest) -> MakerEstimation:
        logger.info(f"Simulating maker estimation for {request.symbol}. Defaulting to 'place maker'.")
        return MakerEstimation(should_place_maker=True, estimated_fill_time_seconds=30.0, reason="Default simulation")

    def track_order(self, order: Order):
        logger.info(f"Simulating tracking for maker order: {order.id}")

    def on_fill(self, order_id: str, filled_size: float, fill_price: float):
        logger.info(f"Simulating fill event for maker order {order_id}: size={filled_size}, price={fill_price}")

    def on_cancel(self, order_id: str):
        logger.info(f"Simulating cancel event for maker order {order_id}")
