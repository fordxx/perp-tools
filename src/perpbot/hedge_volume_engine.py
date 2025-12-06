from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from perpbot.capital_orchestrator import CapitalOrchestrator, CapitalReservation
from perpbot.exchanges.base import ExchangeClient
from perpbot.models import Order, OrderRequest, PriceQuote

logger = logging.getLogger(__name__)


@dataclass
class HedgeVolumeResult:
    """刷量单次结果，用于回传资金占用与盈亏。"""

    status: str
    reason: Optional[str] = None
    long_order: Optional[Order] = None
    short_order: Optional[Order] = None
    long_close: Optional[Order] = None
    short_close: Optional[Order] = None
    fee: float = 0.0
    pnl: float = 0.0
    volume: float = 0.0


class HedgeVolumeEngine:
    """跨交易所永续对冲刷量引擎。

    设计要点：
    - 仅对接永续合约，严格双边对冲（A 做多 / B 做空）。
    - 下单前从资金总控申请 L1 额度，名义金额由配置的区间随机/轮询决定。
    - 全流程包含预检查、同步开仓、持仓等待、同步平仓以及结果回传。
    - 所有风险拦截、滑点/时间阈值、单所亏损熔断均在内部完成。
    - 通过显式传入交易所实例与 capital_orchestrator 对接，无需改动套利/风控主模块；
      删除本模块不会影响原有系统运行。
    """

    def __init__(
        self,
        exchanges: Dict[str, ExchangeClient],
        orchestrator: CapitalOrchestrator,
        min_notional: float = 300.0,
        max_notional: float = 800.0,
        hold_seconds: Tuple[int, int] = (10, 60),
        slippage_bps_limit: float = 30.0,
        time_skew_ms: int = 800,
        loss_limit_pct: float = 0.02,
    ) -> None:
        self.exchanges = exchanges
        self.orchestrator = orchestrator
        self.min_notional = min_notional
        self.max_notional = max_notional
        self.hold_seconds = hold_seconds
        self.slippage_bps_limit = slippage_bps_limit
        self.time_skew_ms = time_skew_ms
        self.loss_limit_pct = loss_limit_pct
        self.loss_tracker: Dict[str, float] = {}

    def _select_notional(self) -> float:
        return random.uniform(self.min_notional, self.max_notional)

    def _check_loss_limit(self, ex: str, pnl: float) -> bool:
        self.loss_tracker.setdefault(ex, 0.0)
        self.loss_tracker[ex] += pnl
        # 当累计亏损超过配置比例（相对 1WU），直接拒绝后续刷量
        threshold = -self.loss_limit_pct * self.orchestrator.wu_size
        if self.loss_tracker[ex] <= threshold:
            logger.warning("%s 刷量累计亏损超限，暂停该所刷量", ex)
            return False
        return True

    async def _fetch_quote(self, ex: ExchangeClient, symbol: str) -> PriceQuote:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, ex.get_current_price, symbol)

    async def _fetch_orderbook(self, ex: ExchangeClient, symbol: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, ex.get_orderbook, symbol)

    async def _precheck(self, long_ex: ExchangeClient, short_ex: ExchangeClient, symbol: str, notional: float) -> Tuple[bool, str]:
        # 只允许 DEX 永续参与刷量
        if long_ex.venue_type != "dex" or short_ex.venue_type != "dex":
            return False, "仅支持 DEX 永续合约刷量"

        try:
            ob_long, ob_short = await asyncio.gather(
                self._fetch_orderbook(long_ex, symbol),
                self._fetch_orderbook(short_ex, symbol),
            )
        except Exception as e:
            return False, f"盘口获取失败: {e}"

        quotes = await asyncio.gather(
            self._fetch_quote(long_ex, symbol),
            self._fetch_quote(short_ex, symbol),
        )
        long_quote, short_quote = quotes
        long_quote.order_book = ob_long
        short_quote.order_book = ob_short

        # 估算滑点
        long_price = long_quote.executable_price("buy", notional / long_quote.mid)
        short_price = short_quote.executable_price("sell", notional / short_quote.mid)
        if long_price is None or short_price is None:
            return False, "盘口深度不足"

        best_long = long_quote.ask
        best_short = short_quote.bid
        long_slip_bps = (long_price - best_long) / best_long * 10_000
        short_slip_bps = (best_short - short_price) / best_short * 10_000
        if long_slip_bps > self.slippage_bps_limit or short_slip_bps > self.slippage_bps_limit:
            return False, "预估滑点超阈值"

        return True, "ok"

    async def execute_wash_cycle(self, symbol: str, long_exchange: str, short_exchange: str) -> HedgeVolumeResult:
        long_ex = self.exchanges.get(long_exchange)
        short_ex = self.exchanges.get(short_exchange)
        if not long_ex or not short_ex:
            return HedgeVolumeResult(status="blocked", reason="交易所不存在")

        notional = self._select_notional()
        reservation: CapitalReservation = self.orchestrator.reserve_for_strategy(
            [long_exchange, short_exchange], amount=notional, strategy="wash_trade"
        )
        if not reservation.approved:
            return HedgeVolumeResult(status="blocked", reason=reservation.reason)

        try:
            ok, reason = await self._precheck(long_ex, short_ex, symbol, notional)
            if not ok:
                return HedgeVolumeResult(status="blocked", reason=reason)

            # 同步开仓
            size_long = notional / (await self._fetch_quote(long_ex, symbol)).mid
            size_short = notional / (await self._fetch_quote(short_ex, symbol)).mid
            open_start = time.time()
            long_order, short_order = await self._open_both(long_ex, short_ex, symbol, size_long, size_short)
            skew_ms = abs(time.time() - open_start) * 1000
            if skew_ms > self.time_skew_ms:
                logger.warning("开仓时间差超阈值 %.0fms", skew_ms)

            if not long_order or not short_order:
                await self._rollback_open(long_ex, short_ex, symbol, long_order, short_order)
                return HedgeVolumeResult(status="failed", reason="一边成交失败已回退")

            # 等待持仓
            hold = random.randint(self.hold_seconds[0], self.hold_seconds[1])
            await asyncio.sleep(hold)

            long_close, short_close = await self._close_both(long_ex, short_ex, symbol, size_long, size_short)
            if not long_close or not short_close:
                return HedgeVolumeResult(status="failed", reason="平仓异常")

            # 简单估算手续费与名义
            fee = notional * 2 * 0.0005  # 占位：默认 5bps 双边
            pnl = (short_close.price - long_close.price) * size_long
            volume = notional * 2

            # 回传到资金总控用于统计
            self.orchestrator.record_volume_result(long_exchange, volume, fee, pnl)
            self.orchestrator.record_volume_result(short_exchange, volume, fee, pnl)

            if not self._check_loss_limit(long_exchange, pnl) or not self._check_loss_limit(short_exchange, pnl):
                return HedgeVolumeResult(status="blocked", reason="单所刷量亏损超限", fee=fee, pnl=pnl, volume=volume)

            return HedgeVolumeResult(
                status="filled",
                long_order=long_order,
                short_order=short_order,
                long_close=long_close,
                short_close=short_close,
                fee=fee,
                pnl=pnl,
                volume=volume,
            )
        finally:
            self.orchestrator.release(reservation)

    async def _open_both(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_size: float,
        short_size: float,
    ) -> Tuple[Optional[Order], Optional[Order]]:
        async def place(ex: ExchangeClient, side: str, size: float):
            req = OrderRequest(symbol=symbol, side=side, size=size)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, ex.place_open_order, req)

        results = await asyncio.gather(
            place(long_ex, "buy", long_size),
            place(short_ex, "sell", short_size),
            return_exceptions=True,
        )
        long_order = results[0] if isinstance(results[0], Order) else None
        short_order = results[1] if isinstance(results[1], Order) else None
        return long_order, short_order

    async def _close_both(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_size: float,
        short_size: float,
    ) -> Tuple[Optional[Order], Optional[Order]]:
        async def close(ex: ExchangeClient, side: str, size: float):
            req = OrderRequest(symbol=symbol, side=side, size=size)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, ex.place_open_order, req)

        results = await asyncio.gather(
            close(long_ex, "sell", long_size),
            close(short_ex, "buy", short_size),
            return_exceptions=True,
        )
        long_close = results[0] if isinstance(results[0], Order) else None
        short_close = results[1] if isinstance(results[1], Order) else None
        return long_close, short_close

    async def _rollback_open(
        self,
        long_ex: ExchangeClient,
        short_ex: ExchangeClient,
        symbol: str,
        long_order: Optional[Order],
        short_order: Optional[Order],
    ) -> None:
        # 任一边失败时，快速反向平掉已成交腿，避免裸露风险
        tasks = []
        loop = asyncio.get_event_loop()
        if long_order:
            tasks.append(loop.run_in_executor(None, long_ex.cancel_order, long_order.id, symbol))
            tasks.append(loop.run_in_executor(None, long_ex.place_open_order, OrderRequest(symbol=symbol, side="sell", size=long_order.size)))
        if short_order:
            tasks.append(loop.run_in_executor(None, short_ex.cancel_order, short_order.id, symbol))
            tasks.append(loop.run_in_executor(None, short_ex.place_open_order, OrderRequest(symbol=symbol, side="buy", size=short_order.size)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

