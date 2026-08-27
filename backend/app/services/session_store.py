"""In-memory screening sessions with JSON persistence. No PII is logged."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from app.config import SESSIONS_DIR

_lock = threading.Lock()
_sessions: dict[str, dict[str, Any]] = {}


def ensure_sessions_directory() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_path(session_id: str) -> Any:
    return SESSIONS_DIR / f"{session_id}.json"


def create_or_update_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    ensure_sessions_directory()
    record = {
        **payload,
        "session_id": session_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if "created_at" not in record:
        record["created_at"] = record["updated_at"]

    with _lock:
        existing = _sessions.get(session_id)
        if existing and "created_at" in existing:
            record["created_at"] = existing["created_at"]
        _sessions[session_id] = record
        _session_path(session_id).write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return record


def get_session(session_id: str) -> dict[str, Any] | None:
    with _lock:
        cached = _sessions.get(session_id)
        if cached:
            return cached

    path = _session_path(session_id)
    if not path.exists():
        return None

    data = json.loads(path.read_text(encoding="utf-8"))
    with _lock:
        _sessions[session_id] = data
    return data
