from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


@dataclass
class PoolState:
    """三层极简模型下的单个资金池。"""

    name: str
    budget_pct: float
    pool: float = 0.0
    allocated: float = 0.0

    @property
    def available(self) -> float:
        return max(self.pool - self.allocated, 0.0)

    def allocate(self, amount: float) -> bool:
        if amount <= self.available + 1e-9:
            self.allocated += amount
            return True
        return False

    def release(self, amount: float) -> None:
        self.allocated = max(self.allocated - amount, 0.0)


@dataclass
class ExchangePoolProfile:
    exchange: str
    equity: float
    pools: Dict[str, PoolState]
    drawdown_pct: float = 0.0
    safe_mode: bool = False
    total_volume: float = 0.0
    total_fee: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class CapitalReservation:
    """记录单次下单前的资金占用，便于执行后释放。"""

    approved: bool
    reason: Optional[str] = None
    allocations: Dict[str, Tuple[str, float]] = field(default_factory=dict)  # ex -> (layer, amount)


class CapitalOrchestrator:
    """三层极简刷量优先模型的资金总控。"""

    def __init__(
        self,
        wu_size: float = 10_000.0,
        wash_budget_pct: float = 0.7,
        arb_budget_pct: float = 0.2,
        reserve_pct: float = 0.1,
        # 兼容旧配置参数，保持接口不报错
        layer_targets: Optional[Dict[str, float]] = None,
        layer_max_usage: Optional[Dict[str, float]] = None,
        safe_layers: Optional[List[str]] = None,
        allow_borrow_from_l5: bool = True,
        drawdown_limit_pct: float = 0.05,
    ) -> None:
        self.wu_size = wu_size
        # 如传入旧的 layer_targets，则尝试从中推导三层比例
        if layer_targets and {"L1", "L2", "L3", "L4", "L5"} <= set(layer_targets):
            wash_budget_pct = layer_targets.get("L1", wash_budget_pct) + layer_targets.get("L2", 0.0)
            arb_budget_pct = layer_targets.get("L3", arb_budget_pct)
            reserve_pct = layer_targets.get("L4", 0.0) + layer_targets.get("L5", reserve_pct)
        self.wash_budget_pct, self.arb_budget_pct, self.reserve_pct = self._normalize_budget(
            wash_budget_pct, arb_budget_pct, reserve_pct
        )
        self.drawdown_limit_pct = drawdown_limit_pct
        self.safe_layers = safe_layers or ["wash", "reserve"]
        self.exchange_profiles: Dict[str, ExchangePoolProfile] = {}

    def _normalize_budget(self, wash: float, arb: float, reserve: float) -> Tuple[float, float, float]:
        total = wash + arb + reserve
        if total <= 0:
            raise ValueError("资金占比配置非法，总和 <= 0")
        if abs(total - 1.0) > 1e-6:
            logger.warning("资金占比总和 %.4f 非 1.0，将自动归一化", total)
            wash, arb, reserve = wash / total, arb / total, reserve / total
        return wash, arb, reserve

    def _ensure_profile(self, exchange: str) -> ExchangePoolProfile:
        if exchange not in self.exchange_profiles:
            pools = {
                "wash": PoolState(name="wash", budget_pct=self.wash_budget_pct, pool=self.wu_size * self.wash_budget_pct),
                "arb": PoolState(name="arb", budget_pct=self.arb_budget_pct, pool=self.wu_size * self.arb_budget_pct),
                "reserve": PoolState(
                    name="reserve", budget_pct=self.reserve_pct, pool=self.wu_size * self.reserve_pct
                ),
            }
            self.exchange_profiles[exchange] = ExchangePoolProfile(
                exchange=exchange,
                equity=self.wu_size,
                pools=pools,
            )
            logger.info("初始化交易所资金池(三层模型): %s 目标资金 %.2f", exchange, self.wu_size)
        return self.exchange_profiles[exchange]

    def update_equity(self, exchange: str, equity: float) -> None:
        profile = self._ensure_profile(exchange)
        profile.equity = equity
        profile.pools["wash"].pool = equity * self.wash_budget_pct
        profile.pools["arb"].pool = equity * self.arb_budget_pct
        profile.pools["reserve"].pool = equity * self.reserve_pct
        logger.debug("更新 %s 资金池: equity=%.2f", exchange, equity)

    def update_drawdown(self, exchange: str, drawdown_pct: float) -> None:
        profile = self._ensure_profile(exchange)
        profile.drawdown_pct = drawdown_pct
        profile.safe_mode = drawdown_pct >= self.drawdown_limit_pct
        if profile.safe_mode:
            logger.warning("%s 回撤 %.2f%% 触发安全模式，仅开放 %s", exchange, drawdown_pct * 100, ",".join(self.safe_layers))

    def _allocate_pool(self, profile: ExchangePoolProfile, pool: str, amount: float) -> bool:
        state = profile.pools.get(pool)
        if not state:
            return False
        return state.allocate(amount)

    def reserve_for_strategy(
        self, exchanges: List[str], amount: float, strategy: str = "arbitrage"
    ) -> CapitalReservation:
        pool = self._strategy_to_pool(strategy)
        allocations: Dict[str, Tuple[str, float]] = {}
        for ex in exchanges:
            if self.reserve_for_pool(ex, pool, amount):
                allocations[ex] = (pool, amount)
            else:
                return CapitalReservation(False, reason=f"{ex} {pool} 资金不足", allocations={})
        return CapitalReservation(True, allocations=allocations)

    def reserve_for_wash(self, exchange: str, amount: float) -> bool:
        return self.reserve_for_pool(exchange, "wash", amount)

    def reserve_for_arb(self, exchange: str, amount: float) -> bool:
        return self.reserve_for_pool(exchange, "arb", amount)

    def reserve_for_pool(self, exchange: str, pool: str, amount: float) -> bool:
        profile = self._ensure_profile(exchange)
        # 安全模式下仅允许 safe_layers
        if profile.safe_mode and pool not in self.safe_layers:
            return False
        return self._allocate_pool(profile, pool, amount)

    def release(self, reservation: Union[CapitalReservation, Tuple[str, float, str]]) -> None:
        if isinstance(reservation, CapitalReservation):
            allocations = reservation.allocations
        else:
            ex, amount, pool = reservation
            allocations = {ex: (pool, amount)}

        for ex, (pool, amount) in allocations.items():
            profile = self.exchange_profiles.get(ex)
            if not profile:
                continue
            state = profile.pools.get(pool)
            if state:
                state.release(amount)
        logger.debug("释放资金占用: %s", allocations)

    def _strategy_to_pool(self, strategy: str) -> str:
        mapping = {
            "wash_trade": "wash",
            "hft": "arb",
            "flash": "arb",
            "stat": "arb",
            "mid_freq": "arb",
            "funding": "reserve",
            "arbitrage": "arb",
        }
        return mapping.get(strategy, "arb")

    def record_volume_result(self, exchange: str, volume: float, fee: float, pnl: float) -> None:
        profile = self._ensure_profile(exchange)
        profile.total_volume += volume
        profile.total_fee += fee
        profile.realized_pnl += pnl
        logger.info(
            "%s 刷量统计: volume=%.2f, fee=%.2f, pnl=%.4f, 累计pnl=%.4f",
            exchange,
            volume,
            fee,
            pnl,
            profile.realized_pnl,
        )

    def current_snapshot(self) -> Dict[str, Dict[str, Dict[str, float]]]:
        snapshot: Dict[str, Dict[str, Dict[str, float]]] = {}
        for ex, profile in self.exchange_profiles.items():
            snapshot[ex] = {}
            for name, pool in profile.pools.items():
                snapshot[ex][name] = {
                    "pool": pool.pool,
                    "allocated": pool.allocated,
                    "available": pool.available,
                }
        return snapshot

