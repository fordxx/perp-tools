# src/perpbot/incentives/base.py
from abc import ABC, abstractmethod
from typing import List
from .models import IncentiveSnapshot

class IncentiveFetcher(ABC):
    """
    Abstract base class for fetching incentive data from a single exchange.
    """
    @abstractmethod
    def fetch(self) -> List[IncentiveSnapshot]:
        """
        Fetches and standardizes incentive data for all relevant markets
        on the exchange.

        Returns:
            A list of IncentiveSnapshot objects.
        """
        raise NotImplementedError
