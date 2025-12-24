from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Literal

from app.config import Settings
from app.fill_tracker import FillTracker
from app.notify import notify_info
from app.okx import OKXClient


Side = Literal["buy", "sell"]
PosSide = Literal["long", "short"]


def _to_decimal(value: str) -> Decimal:
    return Decimal(value)


def _fmt_decimal(value: Decimal) -> str:
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


@dataclass
class TradePlan:
    inst_id: str
    tf: str
    side: Side  # entry side
    pos_side: PosSide
    td_mode: str
    entry_price: float
    stop_loss: float
    total_sz: Decimal
    r_value: float
    cl_ord_id: str
    filled: bool = False
    tp1_done: bool = False
    tp2_done: bool = False
    tp3_done: bool = False
    tp4_done: bool = False
    trail_active: bool = False
    closed_sz: Decimal = Decimal("0")

    @property
    def remaining_sz(self) -> Decimal:
        rem = self.total_sz - self.closed_sz
        return rem if rem > 0 else Decimal("0")


class TradeManager:
    def __init__(self, *, okx: OKXClient, settings: Settings, fill_tracker: FillTracker | None = None) -> None:
        self.okx = okx
        self.settings = settings
        self.fill_tracker = fill_tracker
        self._plans: dict[str, TradePlan] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run_forever())

    async def upsert_plan(self, key: str, plan: TradePlan) -> None:
        async with self._lock:
            self._plans[key] = plan

    async def get_plan(self, key: str) -> TradePlan | None:
        async with self._lock:
            return self._plans.get(key)

    async def clear_plan(self, key: str) -> None:
        async with self._lock:
            self._plans.pop(key, None)

    async def _run_forever(self) -> None:
        while True:
            try:
                await self._tick()
            except Exception:
                # Keep loop alive; errors will surface via logs in real deployments.
                pass
            await asyncio.sleep(self.settings.manager_poll_seconds)

    async def _tick(self) -> None:
        async with self._lock:
            items = list(self._plans.items())
        for key, plan in items:
            await self._process_plan(key, plan)

    async def _process_plan(self, key: str, plan: TradePlan) -> None:
        # If position is gone (stopped out or manually closed), clear plan.
        pos = self.okx.get_position(inst_id=plan.inst_id, pos_side=plan.pos_side)
        if pos is None or float(pos.get("pos", "0") or "0") == 0.0:
            await self.clear_plan(key)
            return

        if not plan.filled:
            ord_state = self.okx.get_order(inst_id=plan.inst_id, cl_ord_id=plan.cl_ord_id)
            if ord_state is None:
                # Might be too old; still manage based on position.
                plan.filled = True
            else:
                state = (ord_state.get("state") or "").lower()
                if state in {"filled", "partially_filled"}:
                    avg_px = ord_state.get("avgPx")
                    if avg_px:
                        plan.entry_price = float(avg_px)
                        plan.r_value = abs(plan.entry_price - plan.stop_loss)
                    plan.filled = True

        last = self.okx.get_last_price(inst_id=plan.inst_id)
        if last is None or plan.r_value <= 0:
            return

        profit_r = (
            (last - plan.entry_price) / plan.r_value
            if plan.side == "buy"
            else (plan.entry_price - last) / plan.r_value
        )

        if (not plan.trail_active) and profit_r >= self.settings.trail_start_r:
            plan.trail_active = True

        # Retrace exit for remaining size (after trail active)
        if plan.trail_active and profit_r <= self.settings.trail_back_r and plan.remaining_sz > 0:
            await self._close_reduce_only(plan, sz=plan.remaining_sz, reason="trail_back")
            plan.closed_sz = plan.total_sz
            await self.clear_plan(key)
            return

        if not self.settings.tp_enabled:
            return

        # Close partials at R targets.
        tp1_sz, tp2_sz, tp3_sz, tp4_sz = self._split_sizes(plan.total_sz)

        if (not plan.tp1_done) and profit_r >= self.settings.tp1_r and tp1_sz > 0:
            sz = tp1_sz if tp1_sz <= plan.remaining_sz else plan.remaining_sz
            await self._close_reduce_only(plan, sz=sz, reason="tp1")
            plan.tp1_done = True
            plan.closed_sz += sz

        if (not plan.tp2_done) and profit_r >= self.settings.tp2_r and tp2_sz > 0:
            sz = tp2_sz if tp2_sz <= plan.remaining_sz else plan.remaining_sz
            await self._close_reduce_only(plan, sz=sz, reason="tp2")
            plan.tp2_done = True
            plan.closed_sz += sz

        if (not plan.tp3_done) and profit_r >= self.settings.tp3_r and tp3_sz > 0:
            sz = tp3_sz if tp3_sz <= plan.remaining_sz else plan.remaining_sz
            await self._close_reduce_only(plan, sz=sz, reason="tp3")
            plan.tp3_done = True
            plan.closed_sz += sz

        if (not plan.tp4_done) and profit_r >= self.settings.tp4_r and plan.remaining_sz > 0:
            # Close whatever remains at TP4 (runner).
            await self._close_reduce_only(plan, sz=plan.remaining_sz, reason="tp4")
            plan.tp4_done = True
            plan.closed_sz = plan.total_sz
            await self.clear_plan(key)

    def _split_sizes(self, total: Decimal) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        # Try to keep sensible rounding for contract counts: default step 1.
        step = Decimal("1") if total == total.to_integral_value() else Decimal("0.0001")
        tp1 = _floor_to_step(total * Decimal(str(self.settings.tp1_pct)), step)
        tp2 = _floor_to_step(total * Decimal(str(self.settings.tp2_pct)), step)
        tp3 = _floor_to_step(total * Decimal(str(self.settings.tp3_pct)), step)
        remaining = total - tp1 - tp2 - tp3
        # Ensure remaining is not negative due to rounding.
        if remaining < 0:
            remaining = Decimal("0")
        return tp1, tp2, tp3, remaining

    async def _close_reduce_only(self, plan: TradePlan, *, sz: Decimal, reason: str) -> None:
        if sz <= 0:
            return
        # Closing side is opposite of entry side in hedge mode for same posSide.
        close_side: Side = "sell" if plan.pos_side == "long" else "buy"
        cl_ord_id = f"{plan.cl_ord_id}_{reason}"
        # Fire-and-forget market reduce-only order.
        self.okx.place_order(
            inst_id=plan.inst_id,
            td_mode=plan.td_mode,
            side=close_side,
            pos_side=plan.pos_side,
            ord_type="market",
            sz=_fmt_decimal(sz),
            px=None,
            cl_ord_id=cl_ord_id[:32],
            sl_trigger_px=None,
            tp_trigger_px=None,
            reduce_only=True,
        )
        if self.fill_tracker is not None:
            self.fill_tracker.register_order_label(
                key=cl_ord_id[:32],
                label=reason,
            )
        notify_info(
            f"okx tp triggered instId={plan.inst_id} reason={reason} sz={_fmt_decimal(sz)}"
        )
