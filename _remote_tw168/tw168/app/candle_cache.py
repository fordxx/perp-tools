from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Iterable

import websockets

from app.risk import Candle

logger = logging.getLogger("uvicorn.error")


@dataclass
class CandleSnapshot:
    candles: list[Candle]
    updated_ts: float


class CandleCache:
    # Dynamic TTL based on timeframe
    DYNAMIC_TTL = {
        "1m": 10,    # 1分钟K线缓存10秒
        "5m": 30,    # 5分钟K线缓存30秒
        "15m": 60,   # 15分钟K线缓存1分钟
        "30m": 120,  # 30分钟K线缓存2分钟
        "1h": 180,   # 1小时K线缓存3分钟
        "2h": 300,   # 2小时K线缓存5分钟
        "4h": 600,   # 4小时K线缓存10分钟
        "1d": 1800,  # 1天K线缓存30分钟
    }

    def __init__(self, *, max_bars: int, ttl_seconds: float) -> None:
        self._max_bars = max_bars
        self._ttl_seconds = ttl_seconds  # 默认TTL,作为后备
        self._data: dict[str, CandleSnapshot] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(source: str, inst_id: str, tf: str) -> str:
        return f"{source}:{inst_id}:{tf}"

    def _trim(self, candles: list[Candle]) -> list[Candle]:
        if self._max_bars <= 0:
            return candles
        return candles[-self._max_bars :]

    async def set_candles(self, *, source: str, inst_id: str, tf: str, candles: Iterable[Candle]) -> None:
        candles_list = list(candles)
        if not candles_list:
            return
        candles_list.sort(key=lambda c: c.ts_ms)
        async with self._lock:
            self._data[self._key(source, inst_id, tf)] = CandleSnapshot(
                candles=self._trim(candles_list),
                updated_ts=time.time(),
            )

    async def upsert_candle(self, *, source: str, inst_id: str, tf: str, candle: Candle) -> None:
        key = self._key(source, inst_id, tf)
        async with self._lock:
            snap = self._data.get(key)
            if snap is None:
                self._data[key] = CandleSnapshot(candles=[candle], updated_ts=time.time())
                return
            candles = snap.candles
            if not candles:
                candles.append(candle)
            else:
                last_ts = candles[-1].ts_ms
                if candle.ts_ms > last_ts:
                    candles.append(candle)
                elif candle.ts_ms == last_ts:
                    candles[-1] = candle
            snap.candles = self._trim(candles)
            snap.updated_ts = time.time()

    async def get_candles(
        self, *, source: str, inst_id: str, tf: str, min_bars: int
    ) -> list[Candle] | None:
        key = self._key(source, inst_id, tf)
        async with self._lock:
            snap = self._data.get(key)
            if snap is None:
                return None

            # Use dynamic TTL based on timeframe, fallback to default
            ttl = self.DYNAMIC_TTL.get(tf.lower(), self._ttl_seconds)
            age = time.time() - snap.updated_ts

            if ttl > 0 and age > ttl:
                logger.debug(
                    "Cache expired for %s:%s:%s (age: %.1fs > ttl: %ds)",
                    source, inst_id, tf, age, ttl
                )
                return None

            if min_bars > 0 and len(snap.candles) < min_bars:
                return None
            return list(snap.candles)


_OKX_CHANNEL_MAP = {
    "1m": "candle1m",
    "5m": "candle5m",
    "15m": "candle15m",
    "30m": "candle30m",
    "1h": "candle1H",
    "2h": "candle2H",
    "4h": "candle4H",
    "1d": "candle1D",
}
_OKX_CHANNEL_TO_TF = {v: k for k, v in _OKX_CHANNEL_MAP.items()}

_EXTENDED_INTERVAL_MAP = {
    "1m": "PT1M",
    "5m": "PT5M",
    "15m": "PT15M",
    "30m": "PT30M",
    "1h": "PT1H",
    "2h": "PT2H",
    "4h": "PT4H",
    "1d": "P1D",
}


async def _okx_candles_loop(
    *,
    cache: CandleCache,
    inst_ids: list[str],
    tfs: list[str],
    stop_event: asyncio.Event,
) -> None:
    if not inst_ids or not tfs:
        return
    url = "wss://ws.okx.com:8443/ws/v5/public"
    args: list[dict[str, str]] = []
    for inst_id in inst_ids:
        for tf in tfs:
            channel = _OKX_CHANNEL_MAP.get(tf)
            if channel is None:
                continue
            args.append({"channel": channel, "instId": inst_id})
    if not args:
        return

    # OKX may limit subscriptions per connection; keep this conservative.
    chunk_size = 80
    chunks = [args[i : i + chunk_size] for i in range(0, len(args), chunk_size)]

    async def _run_chunk(sub_args: list[dict[str, str]]) -> None:
        retry_delay = 1.0
        max_retry_delay = 60.0
        consecutive_errors = 0
        max_consecutive_errors = 10

        while not stop_event.is_set():
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as ws:
                    # Connection successful, reset retry parameters
                    retry_delay = 1.0
                    consecutive_errors = 0

                    await ws.send(json.dumps({"op": "subscribe", "args": sub_args}))
                    logger.info("OKX candle ws subscribed to %d channels (symbols x timeframes)", len(sub_args))

                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("event"):
                            continue
                        arg = msg.get("arg") or {}
                        channel = arg.get("channel")
                        inst_id = arg.get("instId")
                        if not channel or not inst_id:
                            continue
                        tf = _OKX_CHANNEL_TO_TF.get(channel)
                        if tf is None:
                            continue
                        rows = msg.get("data") or []
                        if not rows:
                            continue
                        rows = sorted(rows, key=lambda r: int(r[0]))
                        for row in rows:
                            candle = Candle(
                                ts_ms=int(row[0]),
                                o=float(row[1]),
                                h=float(row[2]),
                                l=float(row[3]),
                                c=float(row[4]),
                            )
                            await cache.upsert_candle(source="okx", inst_id=inst_id, tf=tf, candle=candle)
            except asyncio.CancelledError:
                logger.info("OKX candle ws task cancelled")
                raise
            except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as e:
                consecutive_errors += 1
                logger.warning(
                    "OKX candle ws connection error (consecutive: %d/%d): %s",
                    consecutive_errors, max_consecutive_errors, str(e)
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("OKX candle ws max consecutive errors reached, stopping reconnection attempts")
                    break
            except (ConnectionError, TimeoutError) as e:
                consecutive_errors += 1
                logger.warning(
                    "OKX candle ws network error (consecutive: %d/%d): %s",
                    consecutive_errors, max_consecutive_errors, str(e)
                )
            except json.JSONDecodeError as e:
                logger.error("OKX candle ws received invalid JSON: %s", str(e))
                # Don't increment consecutive_errors for JSON errors
            except Exception as e:
                consecutive_errors += 1
                logger.exception("OKX candle ws unexpected error (consecutive: %d/%d)", consecutive_errors, max_consecutive_errors)
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("OKX candle ws max consecutive errors reached, stopping")
                    break

            if not stop_event.is_set():
                logger.info("OKX candle ws reconnecting in %.1fs", retry_delay)
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff

    await asyncio.gather(*[asyncio.create_task(_run_chunk(chunk)) for chunk in chunks])


async def _okx_candles_loop_dynamic(
    *,
    cache: CandleCache,
    stop_event: asyncio.Event,
    sub_queue: asyncio.Queue,
    subscribed: set[tuple[str, str]],
) -> None:
    url = "wss://ws.okx.com:8443/ws/v5/public"

    async def _send_subscribe(ws: websockets.WebSocketClientProtocol, items: list[tuple[str, str]]) -> None:
        args: list[dict[str, str]] = []
        for inst_id, tf in items:
            channel = _OKX_CHANNEL_MAP.get(tf)
            if channel is None:
                continue
            args.append({"channel": channel, "instId": inst_id})
        if not args:
            return
        await ws.send(json.dumps({"op": "subscribe", "args": args}))

    while not stop_event.is_set():
        sender_task: asyncio.Task | None = None
        try:
            async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
                # Re-subscribe all known pairs on reconnect.
                if subscribed:
                    items = list(subscribed)
                    chunk_size = 80
                    logger.info(f"OKX candle ws re-subscribing to {len(items)} channels on reconnect")
                    for i in range(0, len(items), chunk_size):
                        await _send_subscribe(ws, items[i : i + chunk_size])
                    logger.info(f"OKX candle ws re-subscription sent ({len(items)} channels)")

                async def _sender() -> None:
                    while not stop_event.is_set():
                        inst_id, tf = await sub_queue.get()
                        await _send_subscribe(ws, [(inst_id, tf)])
                        logger.info(f"OKX candle ws dynamic subscription sent: {inst_id} {tf}")

                sender_task = asyncio.create_task(_sender())

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event"):
                        continue
                    arg = msg.get("arg") or {}
                    channel = arg.get("channel")
                    inst_id = arg.get("instId")
                    if not channel or not inst_id:
                        continue
                    tf = _OKX_CHANNEL_TO_TF.get(channel)
                    if tf is None:
                        continue
                    rows = msg.get("data") or []
                    if not rows:
                        continue
                    rows = sorted(rows, key=lambda r: int(r[0]))
                    for row in rows:
                        candle = Candle(
                            ts_ms=int(row[0]),
                            o=float(row[1]),
                            h=float(row[2]),
                            l=float(row[3]),
                            c=float(row[4]),
                        )
                        await cache.upsert_candle(source="okx", inst_id=inst_id, tf=tf, candle=candle)
        except Exception:
            logger.exception("okx candle ws dynamic error")
            await asyncio.sleep(3)
        finally:
            if sender_task is not None:
                sender_task.cancel()


async def _extended_candles_loop(
    *,
    cache: CandleCache,
    stream_url: str,
    inst_id: str,
    tf: str,
    stop_event: asyncio.Event,
) -> None:
    from x10.perpetual.stream_client import PerpetualStreamClient

    interval = _EXTENDED_INTERVAL_MAP.get(tf)
    if interval is None:
        return
    symbol = inst_id.replace("-USDT-SWAP", "-USD")
    client = PerpetualStreamClient(api_url=stream_url)
    while not stop_event.is_set():
        try:
            async with client.subscribe_to_candles(
                market_name=symbol, candle_type="trades", interval=interval
            ) as stream:
                async for msg in stream:
                    data = msg.data or []
                    for row in data:
                        candle = Candle(
                            ts_ms=int(row.timestamp),
                            o=float(row.open),
                            h=float(row.high),
                            l=float(row.low),
                            c=float(row.close),
                        )
                        await cache.upsert_candle(
                            source="extended",
                            inst_id=inst_id,
                            tf=tf,
                            candle=candle,
                        )
        except Exception:
            logger.exception("extended candle ws error")
            await asyncio.sleep(3)


@dataclass
class CandleWsManager:
    cache: CandleCache
    okx_enabled: bool
    extended_enabled: bool
    okx_inst_ids: list[str]
    extended_inst_ids: list[str]
    tfs: list[str]
    extended_stream_url: str
    okx_max_subs: int
    extended_max_subs: int
    extended_idle_seconds: int
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    _tasks: list[asyncio.Task] = field(default_factory=list)
    _okx_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _okx_subscribed: set[tuple[str, str]] = field(default_factory=set)
    _extended_tasks: dict[tuple[str, str], asyncio.Task] = field(default_factory=dict)
    _extended_last_used: dict[tuple[str, str], float] = field(default_factory=dict)
    _subscription_stats: dict[str, int] = field(default_factory=lambda: {
        "okx_subscribed": 0,
        "okx_rejected": 0,
        "extended_subscribed": 0,
        "extended_rejected": 0,
    })
    _first_candle_received: set[tuple[str, str]] = field(default_factory=set)

    def start(self) -> None:
        self._stop_event = asyncio.Event()
        self._tasks = []
        if self.okx_enabled:
            self._tasks.append(
                asyncio.create_task(
                    _okx_candles_loop_dynamic(
                        cache=self.cache,
                        stop_event=self._stop_event,
                        sub_queue=self._okx_queue,
                        subscribed=self._okx_subscribed,
                    )
                )
            )
        if self.extended_enabled and self.extended_stream_url:
            self._tasks.append(asyncio.create_task(self._extended_gc_loop()))
            for inst_id in self.extended_inst_ids:
                for tf in self.tfs:
                    asyncio.create_task(self.ensure_subscription(inst_id=inst_id, tf=tf))
        if self.okx_enabled:
            for inst_id in self.okx_inst_ids:
                for tf in self.tfs:
                    asyncio.create_task(self.ensure_subscription(inst_id=inst_id, tf=tf))

    async def stop(self) -> None:
        if self._tasks:
            self._stop_event.set()
            for task in self._tasks:
                task.cancel()
            for task in self._extended_tasks.values():
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            await asyncio.gather(*self._extended_tasks.values(), return_exceptions=True)
            self._tasks = []
            self._extended_tasks = {}

    async def ensure_subscription(self, *, inst_id: str, tf: str) -> None:
        tf_norm = tf.strip().lower()
        if self.okx_enabled:
            await self._ensure_okx(inst_id=inst_id, tf=tf_norm)
        if self.extended_enabled:
            await self._ensure_extended(inst_id=inst_id, tf=tf_norm)

    async def _ensure_okx(self, *, inst_id: str, tf: str) -> None:
        import logging
        logger = logging.getLogger("uvicorn.error")
        if tf not in _OKX_CHANNEL_MAP:
            return
        key = (inst_id, tf)
        if key in self._okx_subscribed:
            return
        if self.okx_max_subs > 0 and len(self._okx_subscribed) >= self.okx_max_subs:
            self._subscription_stats["okx_rejected"] += 1
            logger.warning(
                "OKX WebSocket subscription limit reached: %d/%d, rejected: %s:%s (total_rejected: %d)",
                len(self._okx_subscribed), self.okx_max_subs, inst_id, tf,
                self._subscription_stats["okx_rejected"]
            )
            return
        self._okx_subscribed.add(key)
        self._subscription_stats["okx_subscribed"] += 1
        await self._okx_queue.put(key)
        logger.debug(f"OKX candle ws queued subscription: {inst_id} {tf} (total: {len(self._okx_subscribed)})")

    async def _ensure_extended(self, *, inst_id: str, tf: str) -> None:
        import logging
        logger = logging.getLogger("uvicorn.error")
        if not self.extended_stream_url:
            return
        if tf not in _EXTENDED_INTERVAL_MAP:
            return
        key = (inst_id, tf)
        self._extended_last_used[key] = time.time()
        if key in self._extended_tasks:
            return
        if self.extended_max_subs > 0 and len(self._extended_tasks) >= self.extended_max_subs:
            self._subscription_stats["extended_rejected"] += 1
            logger.warning(
                "Extended WebSocket subscription limit reached: %d/%d, rejected: %s:%s (total_rejected: %d)",
                len(self._extended_tasks), self.extended_max_subs, inst_id, tf,
                self._subscription_stats["extended_rejected"]
            )
            return
        task = asyncio.create_task(
            _extended_candles_loop(
                cache=self.cache,
                stream_url=self.extended_stream_url,
                inst_id=inst_id,
                tf=tf,
                stop_event=self._stop_event,
            )
        )
        self._extended_tasks[key] = task
        self._subscription_stats["extended_subscribed"] += 1

    async def _extended_gc_loop(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(30)
            if self.extended_idle_seconds <= 0:
                continue
            now = time.time()
            stale = [
                key
                for key, ts in self._extended_last_used.items()
                if now - ts > self.extended_idle_seconds
            ]
            for key in stale:
                task = self._extended_tasks.pop(key, None)
                if task is not None:
                    task.cancel()
                self._extended_last_used.pop(key, None)

    def get_stats(self) -> dict:
        """Get WebSocket subscription statistics."""
        return {
            "okx": {
                "subscribed": len(self._okx_subscribed),
                "max": self.okx_max_subs,
                "rejected": self._subscription_stats["okx_rejected"],
                "utilization": f"{(len(self._okx_subscribed) / self.okx_max_subs * 100):.1f}%" if self.okx_max_subs > 0 else "N/A",
            },
            "extended": {
                "subscribed": len(self._extended_tasks),
                "max": self.extended_max_subs,
                "rejected": self._subscription_stats["extended_rejected"],
                "utilization": f"{(len(self._extended_tasks) / self.extended_max_subs * 100):.1f}%" if self.extended_max_subs > 0 else "N/A",
            },
        }
