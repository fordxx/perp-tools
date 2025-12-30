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
    sl_moved_to_breakeven: bool = False  # Track if SL moved to breakeven at TP1
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
        import logging
        logger = logging.getLogger("uvicorn.error")
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error("TradeManager tick failed: %s", str(e), exc_info=True)
            await asyncio.sleep(self.settings.manager_poll_seconds)

    async def _tick(self) -> None:
        async with self._lock:
            items = list(self._plans.items())
        for key, plan in items:
            await self._process_plan(key, plan)

    async def _process_plan(self, key: str, plan: TradePlan) -> None:
        # If position is gone (stopped out or manually closed), clear plan.
        pos = await asyncio.to_thread(
            self.okx.get_position,
            inst_id=plan.inst_id,
            pos_side=plan.pos_side,
        )
        if pos is None or float(pos.get("pos", "0") or "0") == 0.0:
            await self.clear_plan(key)
            return

        if not plan.filled:
            # For ladder orders, entry_price is already the weighted average from main.py
            # Just check if position exists to confirm filled status
            pos_sz = float(pos.get("pos", "0") or "0")
            if pos_sz > 0:
                # Position exists, mark as filled
                # entry_price and r_value are already set correctly in the plan
                plan.filled = True
            else:
                # Position not found yet, might still be filling
                # Keep checking on next tick
                pass

        last = await asyncio.to_thread(
            self.okx.get_last_price,
            inst_id=plan.inst_id,
        )
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

            # Move stop loss to breakeven after TP1
            if not plan.sl_moved_to_breakeven and plan.remaining_sz > 0:
                await self._move_sl_to_breakeven(plan)
                plan.sl_moved_to_breakeven = True

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
        # OKX clOrdId: alphanumeric + hyphen, max 32 chars (no underscore allowed)
        cl_ord_id = f"{plan.cl_ord_id}-{reason}"

        # Place market reduce-only order with error handling
        import logging
        logger = logging.getLogger("uvicorn.error")

        try:
            resp = await asyncio.to_thread(
                self.okx.place_order,
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

            # Check if order was successful
            if str(resp.get("code", "")) not in {"0", "success"}:
                logger.error(
                    "TradeManager tp_order_failed instId=%s reason=%s sz=%s resp=%s",
                    plan.inst_id, reason, _fmt_decimal(sz), resp
                )
                from app.notify import notify_error
                notify_error(
                    f"⚠️ 止盈订单失败\n"
                    f"交易对: {plan.inst_id}\n"
                    f"原因: {reason}\n"
                    f"数量: {_fmt_decimal(sz)}\n"
                    f"响应: {resp.get('msg', '未知错误')}"
                )
            else:
                if self.fill_tracker is not None:
                    self.fill_tracker.register_order_label(
                        key=cl_ord_id[:32],
                        label=reason,
                    )
                notify_info(
                    f"✅ 止盈触发\n"
                    f"交易对: {plan.inst_id}\n"
                    f"级别: {reason}\n"
                    f"平仓数量: {_fmt_decimal(sz)}"
                )
        except Exception as e:
            logger.error(
                "TradeManager tp_order_exception instId=%s reason=%s sz=%s err=%s",
                plan.inst_id, reason, _fmt_decimal(sz), str(e),
                exc_info=True
            )
            from app.notify import notify_error
            notify_error(
                f"⚠️ 止盈订单异常\n"
                f"交易对: {plan.inst_id}\n"
                f"原因: {reason}\n"
                f"数量: {_fmt_decimal(sz)}\n"
                f"错误: {str(e)}"
            )

    async def _move_sl_to_breakeven(self, plan: TradePlan) -> None:
        """Move stop loss to breakeven (entry price) after TP1"""
        import logging
        logger = logging.getLogger("uvicorn.error")

        try:
            # Get current algo orders to find and cancel existing SL
            algo_orders = await asyncio.to_thread(
                self.okx.get_algo_orders,
                inst_id=plan.inst_id,
                ord_type="conditional"
            )

            # Find and cancel existing SL order
            sl_cancelled = False
            if algo_orders:
                for order in algo_orders:
                    # Check if it's a SL for this position
                    if (order.get("posSide") == plan.pos_side and
                        order.get("state", "").lower() == "live"):
                        algo_id = order.get("algoId")
                        if algo_id:
                            cancel_resp = await asyncio.to_thread(
                                self.okx.cancel_algo_order,
                                inst_id=plan.inst_id,
                                algo_id=algo_id
                            )
                            if str(cancel_resp.get("code", "")) in {"0", "success"}:
                                logger.info("TradeManager cancelled_old_sl instId=%s algoId=%s", plan.inst_id, algo_id)
                                sl_cancelled = True
                                break

            # Place new SL at breakeven (entry price)
            sl_side: Side = "sell" if plan.pos_side == "long" else "buy"

            # Get instrument info for price precision
            inst_info = await asyncio.to_thread(
                self.okx.get_instrument_info,
                inst_id=plan.inst_id
            )
            tick_size = inst_info.get("tickSz") if inst_info else None

            # Round breakeven price to tick size
            from decimal import Decimal, ROUND_DOWN
            if tick_size:
                tick = Decimal(str(tick_size))
                breakeven = Decimal(str(plan.entry_price))
                breakeven_rounded = (breakeven / tick).to_integral_value(rounding=ROUND_DOWN) * tick
                breakeven_price = str(breakeven_rounded)
            else:
                breakeven_price = str(plan.entry_price)

            # Place new SL at breakeven
            sl_resp = await asyncio.to_thread(
                self.okx.place_algo_order,
                inst_id=plan.inst_id,
                td_mode=plan.td_mode,
                side=sl_side,
                pos_side=plan.pos_side,
                ord_type="conditional",
                sz=_fmt_decimal(plan.remaining_sz),
                sl_trigger_px=breakeven_price,
                sl_ord_px="-1"
            )

            if str(sl_resp.get("code", "")) in {"0", "success"}:
                logger.info("TradeManager moved_sl_to_breakeven instId=%s entry=%.6f remaining_sz=%s",
                           plan.inst_id, plan.entry_price, _fmt_decimal(plan.remaining_sz))
                from app.notify import notify_info
                notify_info(
                    f"✅ 止损已推至保本\n"
                    f"交易对: {plan.inst_id}\n"
                    f"保本价: {plan.entry_price}\n"
                    f"保护数量: {_fmt_decimal(plan.remaining_sz)}\n"
                    f"触发原因: TP1 (1.5R) 已达成"
                )
                # Update plan's stop loss to reflect new breakeven level
                plan.stop_loss = plan.entry_price
            else:
                logger.error("TradeManager move_sl_failed instId=%s resp=%s", plan.inst_id, sl_resp)
                from app.notify import notify_error
                notify_error(
                    f"⚠️ 推止损至保本失败\n"
                    f"交易对: {plan.inst_id}\n"
                    f"响应: {sl_resp.get('msg', '未知错误')}"
                )

        except Exception as e:
            logger.error(
                "TradeManager move_sl_exception instId=%s err=%s",
                plan.inst_id, str(e),
                exc_info=True
            )
            from app.notify import notify_error
            notify_error(
                f"⚠️ 推止损至保本异常\n"
                f"交易对: {plan.inst_id}\n"
                f"错误: {str(e)}"
            )
