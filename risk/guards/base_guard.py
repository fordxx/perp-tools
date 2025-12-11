from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..pre_trade_context import PreTradeContext


@dataclass
class GuardResult:
    """
    Represents the outcome of a risk guard check.
    """

    passed: bool
    guard_name: str
    reason: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class BaseGuard(ABC):
    """
    Abstract base class for all pre-trade risk guards.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for the guard."""
        raise NotImplementedError

    @abstractmethod
    def evaluate(self, context: PreTradeContext) -> GuardResult:
        """Evaluates the risk for a given trade context."""
        raise NotImplementedError