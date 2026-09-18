"""Service for persisting live /api/screen results into the case-management data layer."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Document,
    FaceResult as FaceResultModel,
    OCRResult as OCRResultModel,
    ScreeningCase,
    TamperResult as TamperResultModel,
    Traveller,
    WatchlistCheck as WatchlistCheckModel,
    WatchlistEntry,
)

logger = logging.getLogger(__name__)


def persist_screening_case(
    db: Session,
    *,
    case_id: str,
    file_id: str,
    document_type: str,
    doc_number: str | None,
    extracted_fields: dict[str, Any] | None,
    mrz: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    ocr: dict[str, Any] | None,
    tamper: Any,
    face: Any,
    database: Any,
    risk: Any,
    officer_id: str | None = None,
) -> ScreeningCase:
    """Idempotently persist or update all case-management models for a screening result.

    Ensures that Traveller, Document, ScreeningCase, OCRResult, FaceResult,
    TamperResult, and WatchlistCheck are created or updated within an atomic transaction.
    """
    extracted_fields = extracted_fields or {}
    mrz = mrz or {}
    quality = quality or {}
    ocr = ocr or {}

    # 1. Resolve or Create Traveller
    full_name = (
        (extracted_fields.get("full_name") or {}).get("normalized")
        or (extracted_fields.get("name") or {}).get("normalized")
        or (mrz.get("full_name") or {}).get("normalized")
        or (getattr(database, "record", {}) or {}).get("full_name")
        or "UNKNOWN TRAVELLER"
    )
    dob = (
        (extracted_fields.get("date_of_birth") or {}).get("normalized")
        or (mrz.get("date_of_birth") or {}).get("normalized")
        or (getattr(database, "record", {}) or {}).get("date_of_birth")
    )
    nationality = (
        (extracted_fields.get("nationality") or {}).get("normalized")
        or (mrz.get("nationality") or {}).get("normalized")
        or (getattr(database, "record", {}) or {}).get("nationality")
    )

    # 2. Resolve or Create Document
    doc_num_clean = (
        doc_number
        or (extracted_fields.get("passport_number") or {}).get("normalized")
        or (extracted_fields.get("id_number") or {}).get("normalized")
        or (extracted_fields.get("visa_number") or {}).get("normalized")
        or (mrz.get("passport_number") or {}).get("normalized")
        or f"UNKNOWN-{file_id[:8].upper()}"
    )
    issue_date = (extracted_fields.get("date_of_issue") or {}).get("normalized")
    expiry_date = (
        (extracted_fields.get("date_of_expiry") or {}).get("normalized")
        or (mrz.get("date_of_expiry") or {}).get("normalized")
        or (getattr(database, "record", {}) or {}).get("date_of_expiry")
    )
    doc_status = (getattr(database, "record", {}) or {}).get("registered_status") or "VALID"

    # Check if Document already exists
    existing_doc = db.scalar(
        select(Document).where(Document.document_number == doc_num_clean)
    )

    if existing_doc:
        document = existing_doc
        traveller = existing_doc.traveller
        if traveller and full_name != "UNKNOWN TRAVELLER" and traveller.full_name == "UNKNOWN TRAVELLER":
            traveller.full_name = full_name
            if dob:
                traveller.date_of_birth = dob
            if nationality:
                traveller.nationality = nationality
    else:
        traveller = Traveller(
            full_name=full_name,
            date_of_birth=dob,
            nationality=nationality,
        )
        db.add(traveller)
        db.flush()

        document = Document(
            person_id=traveller.id,
            document_number=doc_num_clean,
            document_type=document_type,
            issue_date=issue_date,
            expiry_date=expiry_date,
            status=doc_status,
        )
        db.add(document)
        db.flush()

    # 3. Create or Update ScreeningCase
    is_blacklisted = bool(getattr(database, "blacklisted", False))
    is_duplicate = bool(getattr(database, "duplicate_identity", False))
    tamper_score = float(getattr(tamper, "score", 0.0) or 0.0) if tamper else 0.0
    risk_score = int(getattr(risk, "risk_score", 0) or 0) if risk else 0
    face_similarity = getattr(face, "similarity", None) if face else None
    mrz_valid = mrz.get("mrz_valid")

    existing_case = db.scalar(
        select(ScreeningCase).where(ScreeningCase.case_id == case_id)
    )

    if existing_case:
        case = existing_case
        case.document_id = document.id
        case.extracted_document_number = doc_num_clean
        case.face_similarity = face_similarity
        case.mrz_valid = mrz_valid
        case.watchlist_match = is_blacklisted
        case.duplicate_identity = is_duplicate
        case.tamper_score = tamper_score
        case.risk_score = risk_score
        if officer_id:
            case.officer_id = officer_id[:64]
    else:
        case = ScreeningCase(
            case_id=case_id,
            document_id=document.id,
            extracted_document_number=doc_num_clean,
            face_similarity=face_similarity,
            mrz_valid=mrz_valid,
            watchlist_match=is_blacklisted,
            duplicate_identity=is_duplicate,
            tamper_score=tamper_score,
            risk_score=risk_score,
            officer_id=officer_id[:64] if officer_id else None,
        )
        db.add(case)
        db.flush()

    # 4. Create or Update OCRResult
    if ocr:
        raw_ocr_conf = ocr.get("confidence")
        ocr_conf = float(raw_ocr_conf) if raw_ocr_conf is not None else None
        ocr_status = ocr.get("status", "SUCCESS")
        ocr_raw_text = ocr.get("raw_text", "")
        ocr_details = {
            "processing_time": ocr.get("processing_time"),
            "preprocess_notes": ocr.get("preprocess_notes"),
            "engine": ocr.get("engine"),
            "mrz": mrz,
        }

        existing_ocr = db.scalar(
            select(OCRResultModel).where(OCRResultModel.case_id == case_id)
        )
        if existing_ocr:
            existing_ocr.status = ocr_status
            existing_ocr.confidence = ocr_conf
            existing_ocr.extracted_fields = extracted_fields
            existing_ocr.raw_text = ocr_raw_text
            existing_ocr.details = ocr_details
        else:
            db.add(
                OCRResultModel(
                    case_id=case_id,
                    status=ocr_status,
                    confidence=ocr_conf,
                    extracted_fields=extracted_fields,
                    raw_text=ocr_raw_text,
                    details=ocr_details,
                )
            )

    # 5. Create or Update FaceResult
    if face:
        face_status = getattr(face, "status", "NOT_PROVIDED") or "NOT_PROVIDED"
        face_sim = getattr(face, "similarity", None)
        face_match = getattr(face, "match", None)
        face_model = getattr(face, "model", None) or "ArcFace"
        face_threshold = getattr(face, "threshold", None) or 0.45
        face_details = {
            "reason": getattr(face, "reason", ""),
            "face_detected_document": getattr(face, "face_detected_document", False),
            "face_detected_selfie": getattr(face, "face_detected_selfie", False),
            "image_quality": getattr(face, "image_quality", ""),
        }

        existing_face = db.scalar(
            select(FaceResultModel).where(FaceResultModel.case_id == case_id)
        )
        if existing_face:
            existing_face.status = face_status
            existing_face.similarity = face_sim
            existing_face.match = face_match
            existing_face.model_name = face_model
            existing_face.threshold = face_threshold
            existing_face.details = face_details
        else:
            db.add(
                FaceResultModel(
                    case_id=case_id,
                    status=face_status,
                    similarity=face_sim,
                    match=face_match,
                    model_name=face_model,
                    threshold=face_threshold,
                    details=face_details,
                )
            )

    # 6. Create or Update TamperResult
    if tamper:
        tamper_risk = getattr(tamper, "tamper_risk", "LOW") or "LOW"
        tamper_detected = bool(getattr(tamper, "content_tamper_detected", False))
        indicators_raw = getattr(tamper, "indicators", []) or []
        serialized_indicators = [
            ind.model_dump() if hasattr(ind, "model_dump") else (ind if isinstance(ind, dict) else str(ind))
            for ind in indicators_raw
        ]
        tamper_details = {
            "tamper_risk": tamper_risk,
            "indicators": serialized_indicators,
            "quality": quality,
        }

        existing_tamper = db.scalar(
            select(TamperResultModel).where(TamperResultModel.case_id == case_id)
        )
        if existing_tamper:
            existing_tamper.status = tamper_risk
            existing_tamper.detected = tamper_detected
            existing_tamper.score = tamper_score
            existing_tamper.details = tamper_details
        else:
            db.add(
                TamperResultModel(
                    case_id=case_id,
                    status=tamper_risk,
                    detected=tamper_detected,
                    score=tamper_score,
                    details=tamper_details,
                )
            )

    # 7. Create or Update WatchlistCheck
    wl_entry_id = None
    if is_blacklisted:
        matched_entry = db.scalar(
            select(WatchlistEntry).where(
                (WatchlistEntry.document_number == doc_num_clean) |
                (WatchlistEntry.person_id == traveller.id)
            )
        )
        if matched_entry:
            wl_entry_id = matched_entry.id

    wl_details = {
        "source": getattr(database, "source", "SENTINELAI VERIFICATION DATABASE"),
        "status": getattr(database, "status", "NOT_FOUND"),
        "note": getattr(database, "note", ""),
        "field_matches": getattr(database, "field_matches", {}),
    }

    existing_wl_checks = db.scalars(
        select(WatchlistCheckModel).where(WatchlistCheckModel.case_id == case_id)
    ).all()

    if existing_wl_checks:
        check = existing_wl_checks[0]
        check.watchlist_entry_id = wl_entry_id
        check.matched = is_blacklisted
        check.match_score = 1.0 if is_blacklisted else 0.0
        check.details = wl_details
    else:
        db.add(
            WatchlistCheckModel(
                case_id=case_id,
                watchlist_entry_id=wl_entry_id,
                matched=is_blacklisted,
                match_score=1.0 if is_blacklisted else 0.0,
                details=wl_details,
            )
        )

    db.commit()
    db.expire_all()
    return case


def save_case_snapshot(db: Session, case_id: str, payload: dict) -> None:
    """Keep the complete response in the existing JSON details column."""
    row = db.scalar(select(OCRResultModel).where(OCRResultModel.case_id == case_id))
    if row:
        row.details = {**(row.details or {}), "screening_snapshot": payload}
        db.commit()


def load_case_snapshot(db: Session, case_id: str) -> dict | None:
    row = db.scalar(select(OCRResultModel).where(OCRResultModel.case_id == case_id))
    return (row.details or {}).get("screening_snapshot") if row else None
