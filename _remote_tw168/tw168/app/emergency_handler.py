"""Emergency handler for critical trading failures."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.notify import notify_error


logger = logging.getLogger("uvicorn.error")


@dataclass
class EmergencyPosition:
    """Represents a position that needs emergency handling."""
    inst_id: str
    pos_side: str
    size: str
    entry_price: float
    stop_loss: float | None
    cl_ord_id: str
    failure_reason: str
    timestamp: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3


class EmergencyHandler:
    """Handle critical failures in stop-loss orders with multiple fallback strategies."""

    def __init__(self) -> None:
        self._emergency_positions: dict[str, EmergencyPosition] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        """Start the emergency handler background task."""
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._monitor_loop())
            logger.info("Emergency handler started")

    async def stop(self) -> None:
        """Stop the emergency handler."""
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Emergency handler stopped")

    async def register_emergency(
        self,
        *,
        inst_id: str,
        pos_side: str,
        size: str,
        entry_price: float,
        stop_loss: float | None,
        cl_ord_id: str,
        failure_reason: str,
    ) -> None:
        """Register a position that failed to set stop-loss."""
        key = f"{inst_id}:{pos_side}"
        async with self._lock:
            if key in self._emergency_positions:
                # Update existing entry
                self._emergency_positions[key].retry_count += 1
                self._emergency_positions[key].failure_reason = failure_reason
                self._emergency_positions[key].timestamp = time.time()
            else:
                # Create new entry
                self._emergency_positions[key] = EmergencyPosition(
                    inst_id=inst_id,
                    pos_side=pos_side,
                    size=size,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    cl_ord_id=cl_ord_id,
                    failure_reason=failure_reason,
                )

        logger.warning(
            "Emergency position registered: %s posSide=%s size=%s reason=%s",
            inst_id, pos_side, size, failure_reason
        )

        # Send critical alert
        notify_error(
            f"⚠️ CRITICAL: Emergency position registered\n"
            f"Symbol: {inst_id}\n"
            f"Side: {pos_side}\n"
            f"Size: {size}\n"
            f"Entry: {entry_price}\n"
            f"Reason: {failure_reason}\n"
            f"⚠️ MANUAL INTERVENTION MAY BE REQUIRED"
        )

    async def clear_emergency(self, inst_id: str, pos_side: str) -> None:
        """Clear an emergency position (e.g., after successful closure)."""
        key = f"{inst_id}:{pos_side}"
        async with self._lock:
            if key in self._emergency_positions:
                del self._emergency_positions[key]
                logger.info("Emergency position cleared: %s posSide=%s", inst_id, pos_side)

    async def get_emergency_positions(self) -> list[EmergencyPosition]:
        """Get all current emergency positions."""
        async with self._lock:
            return list(self._emergency_positions.values())

    async def _monitor_loop(self) -> None:
        """Background task to monitor and attempt recovery of emergency positions."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                await self._check_emergency_positions()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Emergency handler monitor loop error: %s", e)

    async def _check_emergency_positions(self) -> None:
        """Check all emergency positions and attempt recovery."""
        positions = await self.get_emergency_positions()

        if not positions:
            return

        logger.warning("Emergency handler checking %d positions", len(positions))

        for pos in positions:
            # Check if max retries reached
            if pos.retry_count >= pos.max_retries:
                # Max retries reached, send critical alert
                notify_error(
                    f"🚨 CRITICAL ALERT - MAX RETRIES REACHED 🚨\n"
                    f"Symbol: {pos.inst_id}\n"
                    f"Side: {pos.pos_side}\n"
                    f"Size: {pos.size}\n"
                    f"Entry: {pos.entry_price}\n"
                    f"SL: {pos.stop_loss}\n"
                    f"Retries: {pos.retry_count}/{pos.max_retries}\n"
                    f"Age: {int(time.time() - pos.timestamp)}s\n"
                    f"⚠️ IMMEDIATE MANUAL INTERVENTION REQUIRED"
                )
                continue

            # Attempt active recovery: retry setting stop-loss
            age_seconds = int(time.time() - pos.timestamp)
            retry_interval = 30  # Retry every 30 seconds

            if age_seconds % retry_interval == 0:
                try:
                    from app.main import exchange, _adjust_size_for_min_quote, _normalize_qty, _format_decimal
                    from decimal import Decimal, ROUND_UP

                    logger.info(
                        "emergency_handler attempting_sl_recovery instId=%s retry=%d/%d",
                        pos.inst_id,
                        pos.retry_count + 1,
                        pos.max_retries,
                    )

                    # Get instrument info
                    inst_info = await exchange.get_instrument_info(inst_id=pos.inst_id)
                    if not inst_info:
                        logger.warning("emergency_handler inst_info_unavailable instId=%s", pos.inst_id)
                        continue

                    lot_step = Decimal(str(inst_info.get("lotStep", "1")))
                    min_order = Decimal(str(inst_info.get("lotSz", "1")))

                    # Adjust stop-loss order size to meet min_quote
                    sl_sz = Decimal(str(pos.size))
                    adjusted_sz, was_adjusted = _adjust_size_for_min_quote(
                        sl_sz,
                        float(pos.stop_loss),
                        inst_info,
                        lot_step,
                    )

                    if was_adjusted:
                        logger.info(
                            "emergency_handler sl_size_adjusted from=%s to=%s min_quote_requirement",
                            sl_sz,
                            adjusted_sz,
                        )

                    sl_sz_str = _format_decimal(adjusted_sz)
                    sl_side = "buy" if pos.pos_side == "short" else "sell"

                    # Attempt to place stop-loss order
                    sl_resp = await exchange.place_algo_order(
                        inst_id=pos.inst_id,
                        td_mode="cross",
                        side=sl_side,
                        pos_side=pos.pos_side,
                        ord_type="conditional",
                        sz=sl_sz_str,
                        sl_trigger_px=str(pos.stop_loss),
                        sl_ord_px="-1",
                    )

                    if str(sl_resp.get("code", "")) in {"0", "success"}:
                        logger.info("emergency_handler recovery_success instId=%s", pos.inst_id)
                        await self.clear_emergency(pos.inst_id, pos.pos_side)
                        from app.notify import notify_info
                        notify_info(
                            f"✅ Emergency Recovery Success\n"
                            f"Symbol: {pos.inst_id}\n"
                            f"SL set at: {pos.stop_loss}\n"
                            f"Size: {sl_sz_str}"
                        )
                    else:
                        logger.warning(
                            "emergency_handler recovery_failed instId=%s resp=%s",
                            pos.inst_id,
                            sl_resp,
                        )
                        # Increment retry count
                        pos.retry_count += 1

                except Exception as e:
                    logger.error("emergency_handler recovery_exception instId=%s err=%s", pos.inst_id, e)
                    pos.retry_count += 1

            # Send periodic reminder
            if age_seconds > 30 and age_seconds % 60 == 0:
                notify_error(
                    f"⚠️ Emergency position still open ({age_seconds}s)\n"
                    f"Symbol: {pos.inst_id} {pos.pos_side}\n"
                    f"Size: {pos.size}\n"
                    f"Retries: {pos.retry_count}/{pos.max_retries}"
                )

    async def attempt_recovery(
        self,
        inst_id: str,
        pos_side: str,
        recovery_func: Callable[[], Any],
    ) -> bool:
        """
        Attempt to recover an emergency position using a recovery function.

        Args:
            inst_id: Instrument ID
            pos_side: Position side (long/short)
            recovery_func: Async function to call for recovery

        Returns:
            True if recovery successful, False otherwise
        """
        key = f"{inst_id}:{pos_side}"

        async with self._lock:
            if key not in self._emergency_positions:
                return False

            pos = self._emergency_positions[key]
            if pos.retry_count >= pos.max_retries:
                logger.error(
                    "Emergency position %s has reached max retries, cannot attempt recovery",
                    key
                )
                return False

        try:
            logger.info("Attempting emergency recovery for %s", key)
            result = await recovery_func()

            if result:
                await self.clear_emergency(inst_id, pos_side)
                logger.info("Emergency recovery successful for %s", key)
                notify_error(f"✅ Emergency recovery successful: {inst_id} {pos_side}")
                return True
            else:
                async with self._lock:
                    if key in self._emergency_positions:
                        self._emergency_positions[key].retry_count += 1
                logger.warning("Emergency recovery failed for %s", key)
                return False

        except Exception as e:
            async with self._lock:
                if key in self._emergency_positions:
                    self._emergency_positions[key].retry_count += 1
            logger.exception("Emergency recovery exception for %s: %s", key, e)
            return False


# Global emergency handler instance
_emergency_handler: EmergencyHandler | None = None


def get_emergency_handler() -> EmergencyHandler:
    """Get or create the global emergency handler instance."""
    global _emergency_handler
    if _emergency_handler is None:
        _emergency_handler = EmergencyHandler()
        _emergency_handler.start()
    return _emergency_handler
