import asyncio
import logging
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class BaseRetryPolicy(ABC):
    """Abstract base class for retry policies."""

    @abstractmethod
    async def execute(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """
        Executes an awaitable function with the defined retry logic.

        Args:
            func: The awaitable function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful.

        Raises:
            The last exception if all retry attempts fail.
        """
        raise NotImplementedError


@dataclass
class ExponentialBackoffPolicy(BaseRetryPolicy):
    """
    Implements an exponential backoff retry strategy.
    """

    max_retries: int = 3
    initial_delay: float = 0.1  # seconds
    backoff_factor: float = 2.0
    max_delay: float = 5.0  # seconds
    jitter: bool = True

    async def execute(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        delay = self.initial_delay
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    logger.error(f"Final attempt ({attempt + 1}/{self.max_retries}) failed. No more retries.", exc_info=True)
                    raise e

                sleep_time = delay
                if self.jitter:
                    sleep_time = random.uniform(0, delay)

                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed. Retrying in {sleep_time:.2f}s...", exc_info=True)
                await asyncio.sleep(sleep_time)
                delay = min(self.max_delay, delay * self.backoff_factor)
        # This line should be unreachable due to the raise in the loop
        raise RuntimeError("Retry loop exited unexpectedly.")