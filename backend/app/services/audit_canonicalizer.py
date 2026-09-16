"""sentinel-audit-v1: an explicitly selected, deterministic off-chain payload."""
import hashlib
import hmac
import json
import math
from decimal import Decimal

FORMAT = "sentinel-audit-v1"
RECORD_TYPES = {"SCREENING_RESULT": 0, "OFFICER_DECISION": 1}


def canonical_json(value) -> str:
    """UTF-8 JSON, sorted Unicode keys, no spaces; finite numbers in plain decimal.

    1 == 1.0, and -0 == 0. Strings retain exact Unicode content (no lossy cleanup).
    Arrays retain order. Unsupported types and nonfinite floats fail closed.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite audit number")
        number = format(Decimal(str(value)), "f")
        if "." in number:
            number = number.rstrip("0").rstrip(".")
        return "0" if number in {"-0", ""} else number
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(item) for item in value) + "]"
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return "{" + ",".join(canonical_json(key) + ":" + canonical_json(value[key]) for key in sorted(value)) + "}"
    raise ValueError("Unsupported audit value")


def case_key(case_id: str) -> str:
    return "0x" + hashlib.sha256(case_id.encode("utf-8")).hexdigest()


def audit_digest(payload: dict, secret: str) -> str:
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("Audit HMAC key must be at least 32 bytes")
    return "0x" + hmac.new(secret.encode("utf-8"), canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


def select(data: dict, keys: tuple) -> dict:
    return {key: data.get(key) for key in keys}


def snapshot(case: dict, persisted: dict, record_type: str, version: int) -> dict:
    if record_type not in RECORD_TYPES or version < 1:
        raise ValueError("Invalid audit record type/version")
    result = {"format": FORMAT, "case_id": case["case_id"], "record_type": record_type, "version": version}
    if record_type == "OFFICER_DECISION":
        if not case.get("officer_decision"):
            raise ValueError("No saved officer decision")
        result.update(decision=select(case["officer_decision"], ("decision", "notes", "officer_id", "timestamp")),
                      persisted=select(persisted, ("decision", "officer_id", "officer_notes")))
        return result
    result.update(select(case, ("timestamp", "document_type", "document", "quality", "mrz", "expiry", "qr", "validation", "tamper", "database", "risk")))
    ocr = case.get("ocr") or {}
    result["identity"] = ocr.get("fields", {})
    result["ocr"] = select(ocr, ("status", "confidence"))
    # Deliberately exclude image crops, file paths, raw OCR, timings and embeddings.
    result["face"] = select(case.get("face") or {}, ("face_detected_document", "face_detected_selfie", "image_quality", "similarity", "match", "status", "reason", "model", "threshold"))
    result["persisted"] = select(persisted, ("extracted_document_number", "face_similarity", "mrz_valid", "watchlist_match", "duplicate_identity", "tamper_score", "risk_score"))
    return result
