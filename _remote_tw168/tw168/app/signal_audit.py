from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOCK = threading.Lock()


def _enabled() -> bool:
    return os.getenv("SIGNAL_AUDIT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "y", "on"}


def _audit_dir() -> Path:
    return Path(os.getenv("SIGNAL_AUDIT_DIR", "/app/logs")).expanduser()


def _path_for_now_utc() -> Path:
    d = _audit_dir()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return d / f"tv_signals_{day}.jsonl"


def append_event(event: dict[str, Any]) -> None:
    if not _enabled():
        return
    try:
        audit_path = _path_for_now_utc()
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _LOCK:
            audit_path.open("a", encoding="utf-8").write(line)
    except Exception:
        # Never break trading flow due to audit logging.
        return


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sanitize_payload(payload: Any) -> dict[str, Any]:
    """Return a JSON-serializable payload dict excluding secrets."""
    if payload is None:
        return {}
    try:
        data = payload.model_dump()  # pydantic v2
    except Exception:
        try:
            data = dict(payload)
        except Exception:
            return {}
    data.pop("secret", None)
    return data

