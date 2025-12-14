from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


@dataclass(frozen=True)
class ExchangeRuntimeConfig:
    exchange: str
    default_symbol: Optional[str] = None
    symbols: List[str] = field(default_factory=list)


def load_exchange_runtime_config(exchange: str, base_dir: str = "config/exchanges") -> Optional[ExchangeRuntimeConfig]:
    path = Path(base_dir) / f"{exchange}.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return ExchangeRuntimeConfig(
        exchange=str(data.get("exchange") or exchange),
        default_symbol=data.get("default_symbol"),
        symbols=list(data.get("symbols") or []),
    )

