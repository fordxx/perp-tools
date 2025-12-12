from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..capital_snapshot import GlobalCapitalSnapshot


class CapitalSnapshotProvider(ABC):
    """资金快照提供器抽象基类：负责返回最新的 GlobalCapitalSnapshot。"""

    @abstractmethod
    def get_snapshot(self) -> Optional[GlobalCapitalSnapshot]:
        """返回当前资金快照。如果无法获取（超时/错误），返回 None。"""
        raise NotImplementedError
