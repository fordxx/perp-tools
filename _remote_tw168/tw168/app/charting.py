from __future__ import annotations

import os
import time
from typing import Iterable


def plot_kline(
    *,
    inst_id: str,
    tf: str,
    closes: Iterable[float],
    entry: float,
    sl: float,
    tps: list[float],
    side: str,
) -> str | None:
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return None

    closes_list = list(closes)
    if not closes_list:
        return None

    os.makedirs("/home/ubuntu/tw168/logs", exist_ok=True)
    ts = int(time.time())
    filename = f"/home/ubuntu/tw168/logs/{inst_id.replace('/', '_')}_{tf}_{ts}.png"

    plt.figure(figsize=(10, 4))
    plt.plot(closes_list, color="#1f77b4", linewidth=1.2)
    plt.axhline(entry, color="#00aa00", linestyle="--", linewidth=1, label="entry")
    plt.axhline(sl, color="#cc0000", linestyle="--", linewidth=1, label="sl")
    for idx, tp in enumerate(tps, 1):
        plt.axhline(tp, color="#999999", linestyle=":", linewidth=1, label=f"tp{idx}")
    plt.title(f"{inst_id} {tf} {side}")
    plt.tight_layout()
    plt.savefig(filename, dpi=150)
    plt.close()
    return filename
