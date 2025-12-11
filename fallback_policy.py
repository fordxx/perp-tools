from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..models.order_request import OrderRequest


@dataclass
class FallbackAction:
    """
    Defines the action to take when a fallback is triggered.
    It contains a new, modified order request to be executed.
    """

    new_request: OrderRequest
    reason: str


class BaseFallbackPolicy(ABC):
    """Abstract base class for execution fallback policies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for the fallback policy."""
        raise NotImplementedError

    @abstractmethod
    def get_fallback_action(
        self, original_request: OrderRequest, remaining_size: float, reason: str
    ) -> Optional[FallbackAction]:
        """
        Determines the fallback action based on the original request and failure reason.

        Returns None if no fallback is defined for this scenario.
        """
        raise NotImplementedError


@dataclass
class MakerToTakerFallback(BaseFallbackPolicy):
    """
    A fallback policy that converts a failed Maker (Post-Only) order
    into an aggressive Taker order (Market order).
    """

    @property
    def name(self) -> str:
        return "MakerToTakerFallback"

    def get_fallback_action(
        self, original_request: OrderRequest, remaining_size: float, reason: str
    ) -> Optional[FallbackAction]:
        # This policy only applies if the original order was a limit order (maker)
        if original_request.limit_price is None:
            return None

        # Create a new market order request for the remaining size
        fallback_request = OrderRequest(
            exchange=original_request.exchange,
            symbol=original_request.symbol,
            side=original_request.side,
            size=remaining_size,
            limit_price=None,  # None indicates a Market order
            is_fallback=True,
        )

        return FallbackAction(
            new_request=fallback_request,
            reason=f"Fallback from Maker to Taker due to: {reason}",
        )