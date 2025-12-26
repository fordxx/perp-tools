from __future__ import annotations

import asyncio
import base64
import hmac
import json
import time
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Optional

import websockets

from app.fill_tracker import FillTracker
from app.notify import notify_info


def _now() -> float:
    return time.time()


class _Dedupe:
    def __init__(self, ttl_seconds: float = 3600) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        now = _now()
        expired = [k for k, ts in self._seen.items() if now - ts > self._ttl_seconds]
        for k in expired:
            self._seen.pop(k, None)
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


def _okx_sign(timestamp: str, secret: str) -> str:
    msg = f"{timestamp}GET/users/self/verify"
    digest = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), sha256).digest()
    return base64.b64encode(digest).decode()


def _okx_extract_tp_tag(cl_ord_id: str) -> Optional[str]:
    for tag in ("tp1", "tp2", "tp3", "tp4", "trail_back"):
        if cl_ord_id.endswith(f"_{tag}"):
            return tag
    return None


async def _okx_ws_loop(
    *,
    api_key: str,
    api_secret: str,
    passphrase: str,
    inst_type: str = "SWAP",
    stop_event: asyncio.Event,
) -> None:
    import logging
    logger = logging.getLogger("uvicorn.error")

    dedupe = _Dedupe()
    url = "wss://ws.okx.com:8443/ws/v5/private"
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

                ts = str(_now())
                login = {
                    "op": "login",
                    "args": [
                        {
                            "apiKey": api_key,
                            "passphrase": passphrase,
                            "timestamp": ts,
                            "sign": _okx_sign(ts, api_secret),
                        }
                    ],
                }
                await ws.send(json.dumps(login))
                await ws.send(json.dumps({"op": "subscribe", "args": [{"channel": "orders", "instType": inst_type}]}))
                await ws.send(
                    json.dumps({"op": "subscribe", "args": [{"channel": "orders-algo", "instType": inst_type}]})
                )
                logger.info("OKX fill ws connected and subscribed")

                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("event"):
                        event_type = msg.get("event")
                        if event_type == "error":
                            logger.error("OKX fill ws event error: %s", msg)
                        continue
                    arg = msg.get("arg") or {}
                    channel = arg.get("channel", "")
                    data = msg.get("data") or []
                    if channel == "orders":
                        for item in data:
                            state = (item.get("state") or "").lower()
                            if state != "filled":
                                continue
                            cl_ord_id = item.get("clOrdId") or ""
                            ord_id = item.get("ordId") or ""
                            label = None
                            if cl_ord_id:
                                label = fill_tracker.get_order_label(key=cl_ord_id)
                            if label is None and ord_id:
                                label = fill_tracker.get_order_label(key=ord_id)
                            if label is None:
                                label = _okx_extract_tp_tag(cl_ord_id)
                            ord_id = item.get("ordId") or cl_ord_id or "unknown"
                            key = f"okx:orders:{ord_id}:{state}"
                            if dedupe.seen(key):
                                continue
                            inst_id = item.get("instId") or ""
                            px = item.get("avgPx") or item.get("fillPx") or ""
                            sz = item.get("fillSz") or item.get("accFillSz") or ""
                            if label:
                                notify_info(f"okx {label} filled instId={inst_id} px={px} sz={sz}")
                            else:
                                notify_info(f"okx order filled instId={inst_id} px={px} sz={sz}")
                    elif channel == "orders-algo":
                        for item in data:
                            state = (item.get("state") or "").lower()
                            ord_type = (item.get("ordType") or "").lower()
                            if ord_type not in {"conditional", "trigger"}:
                                continue
                            if state not in {"triggered", "effective", "filled"}:
                                continue
                            algo_id = item.get("algoId") or item.get("ordId") or "unknown"
                            label = fill_tracker.get_algo_label(algo_id=algo_id) or "sl"
                            key = f"okx:algo:{algo_id}:{state}"
                            if dedupe.seen(key):
                                continue
                            inst_id = item.get("instId") or ""
                            trigger_px = item.get("triggerPx") or item.get("slTriggerPx") or ""
                            sz = item.get("sz") or ""
                            notify_info(
                                f"okx {label} triggered instId={inst_id} state={state} trigger_px={trigger_px} sz={sz}"
                            )
        except asyncio.CancelledError:
            logger.info("OKX fill ws task cancelled")
            raise
        except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as e:
            consecutive_errors += 1
            logger.warning(
                "OKX fill ws connection error (consecutive: %d/%d): %s",
                consecutive_errors, max_consecutive_errors, str(e)
            )
            if consecutive_errors >= max_consecutive_errors:
                logger.error("OKX fill ws max consecutive errors reached, stopping reconnection attempts")
                break
        except (ConnectionError, TimeoutError) as e:
            consecutive_errors += 1
            logger.warning(
                "OKX fill ws network error (consecutive: %d/%d): %s",
                consecutive_errors, max_consecutive_errors, str(e)
            )
        except json.JSONDecodeError as e:
            logger.error("OKX fill ws received invalid JSON: %s", str(e))
            # Don't increment consecutive_errors for JSON errors
        except Exception as e:
            consecutive_errors += 1
            logger.exception("OKX fill ws unexpected error (consecutive: %d/%d)", consecutive_errors, max_consecutive_errors)
            if consecutive_errors >= max_consecutive_errors:
                logger.error("OKX fill ws max consecutive errors reached, stopping")
                break

        if not stop_event.is_set():
            logger.info("OKX fill ws reconnecting in %.1fs", retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff


async def _extended_ws_loop(
    *,
    stream_url: str,
    api_key: str,
    fill_tracker: FillTracker,
    stop_event: asyncio.Event,
) -> None:
    import logging
    logger = logging.getLogger("uvicorn.error")

    from x10.perpetual.stream_client import PerpetualStreamClient
    from x10.utils.http import StreamDataType

    dedupe = _Dedupe()
    client = PerpetualStreamClient(api_url=stream_url)
    retry_delay = 1.0
    max_retry_delay = 60.0
    consecutive_errors = 0
    max_consecutive_errors = 10

    while not stop_event.is_set():
        try:
            async with client.subscribe_to_account_updates(api_key=api_key) as stream:
                # Connection successful, reset retry parameters
                retry_delay = 1.0
                consecutive_errors = 0
                logger.info("Extended fill ws connected and subscribed")

                async for msg in stream:
                    if msg.type != StreamDataType.TRADE or not msg.data or not msg.data.trades:
                        continue
                    for trade in msg.data.trades:
                        trade_id = str(trade.id)
                        key = f"ext:trade:{trade_id}"
                        if dedupe.seen(key):
                            continue
                        side_val = getattr(trade.side, "value", str(trade.side))
                        side = str(side_val).lower()
                        market = trade.market
                        inst_id = market.replace("-USD", "-USDT-SWAP")
                        price = float(trade.price)
                        qty = trade.qty
                        label = fill_tracker.get_order_label(key=str(trade.order_id))
                        if label is None:
                            label = fill_tracker.classify_exit(inst_id=inst_id, trade_side=side, price=price)
                        if label:
                            notify_info(
                                f"extended {label} filled instId={inst_id} side={side} px={price} sz={qty}"
                            )
                        else:
                            notify_info(
                                f"extended trade filled instId={inst_id} side={side} px={price} sz={qty}"
                            )
        except asyncio.CancelledError:
            logger.info("Extended fill ws task cancelled")
            raise
        except (ConnectionError, TimeoutError) as e:
            consecutive_errors += 1
            logger.warning(
                "Extended fill ws network error (consecutive: %d/%d): %s",
                consecutive_errors, max_consecutive_errors, str(e)
            )
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Extended fill ws max consecutive errors reached, stopping reconnection attempts")
                break
        except Exception as e:
            consecutive_errors += 1
            logger.exception("Extended fill ws unexpected error (consecutive: %d/%d)", consecutive_errors, max_consecutive_errors)
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Extended fill ws max consecutive errors reached, stopping")
                break

        if not stop_event.is_set():
            logger.info("Extended fill ws reconnecting in %.1fs", retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_retry_delay)  # Exponential backoff


@dataclass
class WsFillManager:
    fill_tracker: FillTracker
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""
    extended_stream_url: str = ""
    extended_api_key: str = ""
    _stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    _tasks: list[asyncio.Task] = field(default_factory=list)

    def start(self, *, enable_okx: bool, enable_extended: bool) -> None:
        self._stop_event = asyncio.Event()
        self._tasks = []
        if enable_okx and self.okx_api_key and self.okx_api_secret and self.okx_passphrase:
            self._tasks.append(
                asyncio.create_task(
                    _okx_ws_loop(
                        api_key=self.okx_api_key,
                        api_secret=self.okx_api_secret,
                        passphrase=self.okx_passphrase,
                        stop_event=self._stop_event,
                    )
                )
            )
        if enable_extended and self.extended_stream_url and self.extended_api_key:
            self._tasks.append(
                asyncio.create_task(
                    _extended_ws_loop(
                        stream_url=self.extended_stream_url,
                        api_key=self.extended_api_key,
                        fill_tracker=self.fill_tracker,
                        stop_event=self._stop_event,
                    )
                )
            )

    async def stop(self) -> None:
        if self._tasks:
            self._stop_event.set()
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks = []
