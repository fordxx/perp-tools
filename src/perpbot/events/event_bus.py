from __future__ import annotations

import queue
import threading
from typing import Callable, Dict, List, Type, Union

from .event_types import Event, EventKind

EventHandler = Callable[[Event], None]
SubscriberKey = Union[EventKind, Type[Event]]


class EventBus:
    """Thread-safe async event bus with non-blocking publish."""

    def __init__(self, max_queue_size: int = 10000, worker_count: int = 1):
        self._queue: "queue.Queue[Event]" = queue.Queue(maxsize=max_queue_size)
        self._subscribers: Dict[EventKind, List[EventHandler]] = {}
        self._subscribers_by_type: Dict[Type[Event], List[EventHandler]] = {}
        self._lock = threading.Lock()
        self._workers: List[threading.Thread] = []
        self._running = False
        self._worker_count = max(1, worker_count)

    def subscribe(self, kind: SubscriberKey, handler: EventHandler) -> None:
        with self._lock:
            if isinstance(kind, EventKind):
                self._subscribers.setdefault(kind, []).append(handler)
            else:
                self._subscribers_by_type.setdefault(kind, []).append(handler)

    def publish(self, event: Event) -> None:
        if not self._running:
            self._dispatch_event(event)
            return

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            # Queue is full; drop the event to keep the system responsive.
            pass

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for idx in range(self._worker_count):
            thread = threading.Thread(
                target=self._worker_loop,
                name=f"event-bus-worker-{idx}",
                daemon=True,
            )
            thread.start()
            self._workers.append(thread)

    def stop(self) -> None:
        self._running = False

    def _worker_loop(self) -> None:
        while self._running:
            try:
                event = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._dispatch_event(event)

    def unsubscribe(self, kind: SubscriberKey, handler: EventHandler) -> None:
        with self._lock:
            if isinstance(kind, EventKind):
                handlers = self._subscribers.get(kind)
            else:
                handlers = self._subscribers_by_type.get(kind)
            if handlers and handler in handlers:
                handlers.remove(handler)

    def _dispatch_event(self, event: Event) -> None:
        with self._lock:
            handlers = list(self._subscribers.get(event.kind, []))
            handlers.extend(self._subscribers_by_type.get(type(event), []))

        for handler in handlers:
            try:
                handler(event)
            except Exception:
                # TODO: integrate structured logging here
                pass
