"""In-memory screening sessions with JSON persistence. No PII is logged in plain logs."""

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
        "case_id": payload.get("case_id", session_id),
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


def record_officer_decision(
    case_id: str,
    decision: str,
    notes: str | None = None,
    officer_id: str = "OFFICER-DEMO",
) -> dict[str, Any] | None:
    """Record an immigration officer decision on a screened case."""
    session = get_session(case_id)
    if not session:
        return None

    decision_record = {
        "decision": decision,
        "notes": notes,
        "officer_id": officer_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    session["officer_decision"] = decision_record
    return create_or_update_session(case_id, session)


def list_sessions() -> list[dict[str, Any]]:
    """Return recent screening cases summaries for the dashboard."""
    ensure_sessions_directory()
    records: list[dict[str, Any]] = []
    for path in sorted(SESSIONS_DIR.glob("CASE-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            ocr_fields = (item.get("ocr") or {}).get("fields") or {}
            doc_num = (ocr_fields.get("passport_number") or ocr_fields.get("id_number") or {}).get("normalized") or ""
            name = (ocr_fields.get("full_name") or ocr_fields.get("name") or {}).get("normalized") or "Unknown"

            summary = {
                "case_id": item.get("case_id", path.stem),
                "timestamp": item.get("timestamp", item.get("created_at")),
                "document_type": item.get("document_type", "passport"),
                "document_number": (doc_num[:2] + "•••" + doc_num[-3:]) if len(doc_num) >= 5 else (doc_num or "NOT_EXTRACTED"),
                "holder_name": name,
                "risk": item.get("risk"),
                "validation": item.get("validation", {}).get("status", "REVIEW"),
                "officer_decision": item.get("officer_decision"),
            }
            records.append(summary)
        except (OSError, json.JSONDecodeError):
            continue
    return records[:100]


def get_session(session_id: str) -> dict[str, Any] | None:
    with _lock:
        cached = _sessions.get(session_id)
        if cached:
            return cached

    path = _session_path(session_id)
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        with _lock:
            _sessions[session_id] = data
        return data
    except (OSError, json.JSONDecodeError):
        return None

