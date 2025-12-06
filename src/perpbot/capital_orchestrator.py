from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CapitalLayerState:
    """资金分层状态，记录当前层的目标权重与占用情况。"""

    name: str
    target_pct: float
    max_usage_pct: float
    pool: float = 0.0
    allocated: float = 0.0

    @property
    def available(self) -> float:
        return max(self.pool * self.max_usage_pct - self.allocated, 0.0)

    def allocate(self, amount: float) -> bool:
        if amount <= self.available + 1e-9:
            self.allocated += amount
            return True
        return False

    def release(self, amount: float) -> None:
        self.allocated = max(self.allocated - amount, 0.0)


@dataclass
class ExchangeCapitalProfile:
    exchange: str
    equity: float
    layers: Dict[str, CapitalLayerState]
    drawdown_pct: float = 0.0
    safe_mode: bool = False
    total_volume: float = 0.0
    total_fee: float = 0.0
    realized_pnl: float = 0.0

    def allowed_layers(self, safe_layers: List[str]) -> List[str]:
        if self.safe_mode:
            return [l for l in self.layers if l in safe_layers]
        return list(self.layers.keys())


@dataclass
class CapitalReservation:
    """记录单次下单前的资金占用，便于执行后释放。"""

    approved: bool
    reason: Optional[str] = None
    allocations: Dict[str, Tuple[str, float]] = field(default_factory=dict)  # ex -> (layer, amount)


class CapitalOrchestrator:
    """资金调度与风险分层总控，负责在下单前分配/冻结资金。"""

    def __init__(
        self,
        wu_size: float = 10_000.0,
        layer_targets: Optional[Dict[str, float]] = None,
        layer_max_usage: Optional[Dict[str, float]] = None,
        safe_layers: Optional[List[str]] = None,
        allow_borrow_from_l5: bool = True,
        drawdown_limit_pct: float = 0.05,
    ) -> None:
        self.wu_size = wu_size
        self.layer_targets = layer_targets or {
            "L1": 0.2,
            "L2": 0.3,
            "L3": 0.25,
            "L4": 0.1,
            "L5": 0.15,
        }
        self.layer_max_usage = layer_max_usage or {
            "L1": 1.0,
            "L2": 1.0,
            "L3": 1.0,
            "L4": 1.0,
            "L5": 1.0,
        }
        self.safe_layers = safe_layers or ["L1", "L4"]
        self.allow_borrow_from_l5 = allow_borrow_from_l5
        self.drawdown_limit_pct = drawdown_limit_pct
        self.exchange_profiles: Dict[str, ExchangeCapitalProfile] = {}

    def _ensure_profile(self, exchange: str) -> ExchangeCapitalProfile:
        if exchange not in self.exchange_profiles:
            layers = {
                name: CapitalLayerState(
                    name=name,
                    target_pct=pct,
                    max_usage_pct=self.layer_max_usage.get(name, 1.0),
                    pool=self.wu_size * pct,
                )
                for name, pct in self.layer_targets.items()
            }
            self.exchange_profiles[exchange] = ExchangeCapitalProfile(
                exchange=exchange,
                equity=self.wu_size,
                layers=layers,
            )
            logger.info("初始化交易所资金分层: %s 目标资金 %.2f", exchange, self.wu_size)
        return self.exchange_profiles[exchange]

    def update_equity(self, exchange: str, equity: float) -> None:
        profile = self._ensure_profile(exchange)
        profile.equity = equity
        for layer in profile.layers.values():
            layer.pool = equity * self.layer_targets.get(layer.name, 0.0)
        logger.debug("更新 %s 资金池: equity=%.2f", exchange, equity)

    def update_drawdown(self, exchange: str, drawdown_pct: float) -> None:
        profile = self._ensure_profile(exchange)
        profile.drawdown_pct = drawdown_pct
        if drawdown_pct >= self.drawdown_limit_pct:
            profile.safe_mode = True
            logger.warning("%s 触发单所回撤限制，进入安全模式，仅开放 %s", exchange, ",".join(self.safe_layers))
        else:
            profile.safe_mode = False

    def _borrow_from_l5(self, profile: ExchangeCapitalProfile, amount: float) -> bool:
        l5 = profile.layers.get("L5")
        if not l5:
            return False
        return l5.allocate(amount)

    def _allocate_single(self, profile: ExchangeCapitalProfile, layer: str, amount: float) -> Optional[str]:
        state = profile.layers.get(layer)
        if not state:
            return None
        if state.allocate(amount):
            return layer
        if layer != "L5" and self.allow_borrow_from_l5:
            borrowed = self._borrow_from_l5(profile, amount)
            if borrowed:
                logger.info("%s %s 资金不足，已直接从 L5 调度 %.2f", profile.exchange, layer, amount)
                return "L5"
        return None

    def reserve_for_strategy(
        self,
        exchanges: List[str],
        amount: float,
        strategy: str = "arbitrage",
    ) -> CapitalReservation:
        allocations: Dict[str, Tuple[str, float]] = {}
        target_layer = self._strategy_to_layer(strategy)
        for ex in exchanges:
            profile = self._ensure_profile(ex)
            if profile.safe_mode and target_layer not in self.safe_layers:
                target_layer = self.safe_layers[0]
            if target_layer not in profile.allowed_layers(self.safe_layers):
                return CapitalReservation(False, reason=f"{ex} 当前仅允许 {','.join(self.safe_layers)}", allocations={})
            used_layer = self._allocate_single(profile, target_layer, amount)
            if not used_layer:
                return CapitalReservation(False, reason=f"{ex} {target_layer} 资金不足", allocations={})
            allocations[ex] = (used_layer, amount)
        return CapitalReservation(True, allocations=allocations)

    def release(self, reservation: CapitalReservation) -> None:
        for ex, (layer, amount) in reservation.allocations.items():
            profile = self.exchange_profiles.get(ex)
            if not profile:
                continue
            state = profile.layers.get(layer)
            if state:
                state.release(amount)
        logger.debug("释放资金占用: %s", reservation.allocations)

    def _strategy_to_layer(self, strategy: str) -> str:
        mapping = {
            "wash_trade": "L1",
            "hft": "L2",
            "flash": "L2",
            "stat": "L2",
            "mid_freq": "L3",
            "funding": "L4",
            "arbitrage": "L2",
        }
        return mapping.get(strategy, "L2")

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
            for name, layer in profile.layers.items():
                snapshot[ex][name] = {
                    "pool": layer.pool,
                    "allocated": layer.allocated,
                    "available": layer.available,
                }
        return snapshot

