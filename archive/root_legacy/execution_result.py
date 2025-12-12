from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    ok: bool
    order_id: Optional[str]
    status: str  # SUCCESS / FAILED / PARTIAL / CANCELLED
    filled_size: Optional[float]
    avg_price: Optional[float]
    reason: Optional[str]  # 错误信息
    attempts: int  # 重试次数
    exchange: str
    symbol: str

    @staticmethod
    def success(
        order_id: str, filled_size: float, avg_price: float, exchange: str, symbol: str, attempts: int = 1
    ) -> "ExecutionResult":
        return ExecutionResult(
            ok=True,
            order_id=order_id,
            status="SUCCESS",
            filled_size=filled_size,
            avg_price=avg_price,
            reason=None,
            attempts=attempts,
            exchange=exchange,
            symbol=symbol,
        )

    @staticmethod
    def failed(
        reason: str, exchange: str, symbol: str, attempts: int = 1, order_id: Optional[str] = None
    ) -> "ExecutionResult":
        return ExecutionResult(ok=False, order_id=order_id, status="FAILED", filled_size=0.0, avg_price=0.0, reason=reason, attempts=attempts, exchange=exchange, symbol=symbol)