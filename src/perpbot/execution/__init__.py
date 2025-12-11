"""
perpbot.execution - 执行引擎

负责订单执行、填单风险管理、自动降级

集成：
- ExecutionMode: 执行模式（SAFE_TAKER_ONLY, HYBRID_HEDGE_TAKER, DOUBLE_MAKER）
- ExecutionEngine: 执行引擎
- MakerTracker: Maker 填单跟踪
- MakerFillEstimator: 填单概率估计
"""

from perpbot.execution.execution_mode import (
    ExecutionMode,
    ExecutionConfig,
    OrderTypeDecision,
    decide_order_types,
    validate_execution_constraints,
)
from perpbot.execution.execution_engine import (
    ExecutionEngine,
    OrderStatus,
    OrderResult,
    HedgeExecutionResult,
)
from perpbot.execution.maker_tracker import (
    MakerTracker,
    MakerStats,
    DegradationState,
)
from perpbot.execution.maker_fill_estimator import MakerFillEstimator

__all__ = [
    "ExecutionMode",
    "ExecutionConfig",
    "OrderTypeDecision",
    "decide_order_types",
    "validate_execution_constraints",
    "ExecutionEngine",
    "OrderStatus",
    "OrderResult",
    "HedgeExecutionResult",
    "MakerTracker",
    "MakerStats",
    "DegradationState",
    "MakerFillEstimator",
]
