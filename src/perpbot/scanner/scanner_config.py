from dataclasses import dataclass


@dataclass
class ScannerConfig:
    min_spread_bps: float              # 最小价差（bps）
    max_latency_ms: float              # 允许的最大延迟
    max_quality_penalty: float         # 最大行情质量惩罚（0～1）
    max_order_notional: float          # 每笔套利最大下单名义金额
    max_depth: int = 5                 # 未来可用于深度行情
