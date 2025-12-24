from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import requests


class TelegramControl:
    def __init__(
        self,
        *,
        token: str,
        chat_id: str,
        handler: Callable[[str, str], None],
    ) -> None:
        self._token = token
        self._chat_id = str(chat_id)
        self._handler = handler
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._offset: Optional[int] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _loop(self) -> None:
        self._offset = self._get_latest_offset()
        while not self._stop.is_set():
            try:
                updates = self._get_updates(timeout=20)
                if updates:
                    for update in updates:
                        update_id = update.get("update_id")
                        if update_id is not None:
                            self._offset = update_id + 1
                        message = update.get("message") or {}
                        chat = message.get("chat") or {}
                        chat_id = str(chat.get("id", ""))
                        if chat_id != self._chat_id:
                            continue
                        text = (message.get("text") or "").strip()
                        if not text:
                            continue
                        if text.lower().startswith("/div"):
                            parts = text.split()
                            if len(parts) >= 3:
                                inst_id = parts[1].upper()
                                tf = parts[2].lower()
                                self._handler(inst_id, tf)
            except Exception:
                time.sleep(2)

    def _get_latest_offset(self) -> Optional[int]:
        updates = self._get_updates(timeout=0)
        if not updates:
            return None
        last_id = updates[-1].get("update_id")
        return last_id + 1 if last_id is not None else None

    def _get_updates(self, *, timeout: int) -> list[dict]:
        url = f"https://api.telegram.org/bot{self._token}/getUpdates"
        params: dict[str, object] = {"timeout": timeout}
        if self._offset is not None:
            params["offset"] = self._offset
        try:
            resp = requests.get(url, params=params, timeout=timeout + 5)
            data = resp.json()
            return data.get("result") or []
        except Exception:
            return []
