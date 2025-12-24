from __future__ import annotations

import os
from typing import Optional

import requests


def _env(name: str) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value or None


def _send(message: str) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"[tv168] {message}",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        return


def notify_error(message: str) -> None:
    """Send a best-effort Telegram alert when configured."""
    _send(f"ERROR {message}")


def notify_info(message: str) -> None:
    """Send a best-effort Telegram info alert when configured."""
    _send(f"INFO {message}")


def notify_photo(image_path: str, caption: str | None = None) -> None:
    token = _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    try:
        with open(image_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            requests.post(url, data=data, files=files, timeout=10)
    except Exception:
        return
