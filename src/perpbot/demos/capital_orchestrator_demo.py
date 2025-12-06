"""资金分层总控独立演示脚本。

运行方式：
    PYTHONPATH=src python -m perpbot.demos.capital_orchestrator_demo

即使删除本文件或 capital_orchestrator 模块，原套利系统仍可正常工作；
此脚本仅演示显式接口调用方式。
"""

from __future__ import annotations

import logging
from pprint import pprint

from perpbot.capital_orchestrator import CapitalOrchestrator

logging.basicConfig(level=logging.INFO)


def main() -> None:
    orchestrator = CapitalOrchestrator()

    # 初始化两个交易所资金池
    orchestrator.update_equity("dex_a", 10_000)
    orchestrator.update_equity("dex_b", 10_000)

    # 模拟策略向 L2 申请 500 USDT 名义
    reservation = orchestrator.reserve_for_strategy(["dex_a", "dex_b"], 500, strategy="arbitrage")
    print("申请结果: ", reservation.approved, reservation.reason)
    pprint(orchestrator.current_snapshot())

    # 模拟执行完成后释放
    orchestrator.release(reservation)
    pprint(orchestrator.current_snapshot())


if __name__ == "__main__":
    main()

