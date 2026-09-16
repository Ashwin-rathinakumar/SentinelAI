from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db

from app.schemas.screening import (
    FaceResult,
    OfficerDecisionRequest,
    ScreeningResponse,
)
from app.services.file_service import (
    generate_safe_filename,
    read_and_validate_upload,
    save_upload,
    validate_document_type,
)
from app.services.ocr_service import extract_document
from app.services.quality_service import analyze_document_quality
from app.services.screening_services import (
    calculate_risk,
    compare_faces,
    database_lookup,
    forensic_analysis,
    validate_document,
)
from app.services.session_store import (
    create_or_update_session,
    get_session,
    list_sessions,
    record_officer_decision,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["screening"])


@router.post("/screen", response_model=ScreeningResponse)
async def screen_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form("passport"),
    selfie: UploadFile | None = File(None),
    officer_id: str = Form("OFFICER-DEMO"),
    db: Session = Depends(get_db),
) -> ScreeningResponse:
    """Run full automated screening pipeline on uploaded document and optional selfie."""
    document_type = validate_document_type(document_type)
    data, extension, _ = await read_and_validate_upload(file)
    file_id, safe_filename = generate_safe_filename(extension)
    save_upload(data, safe_filename)

    # 1. Image Quality Analysis
    quality = analyze_document_quality(data, extension)

    # 2. OCR and MRZ Extraction
    ocr = extract_document(file_id, data, extension, document_type)
    mrz = ocr.get("mrz") or {}
    fields = ocr.get("fields") or {}

    # 3. Document Integrity Validation
    document = ocr.get("document") or {"type": "UNKNOWN", "signals": [], "method": "deterministic_rules"}
    document_type = document["type"].lower()
    ocr["document"] = document
    if document_type == "unknown":
        from app.services.document_type_service import not_applicable_mrz
        mrz = not_applicable_mrz()
        ocr["mrz"] = mrz
    validation = validate_document(fields, mrz, document_type)

    # 4. Forensic & Tamper Analysis
    tamper = forensic_analysis(data, quality, validation)

    # 5. Biometric Face Verification
    selfie_data = await selfie.read() if selfie else None
    face = compare_faces(data, selfie_data)

    # 6. Database Verification
    number_item = fields.get("passport_number") or fields.get("id_number") or fields.get("visa_number") or {}
    doc_number = number_item.get("normalized")
    database = database_lookup(doc_number, extracted_fields=fields, document_type=document_type)

    # 6b. Duplicate Identity Search via Stored Face Embeddings
    from app.services.face_service import get_embedding_from_image, search_duplicates
    doc_embedding = get_embedding_from_image(data)
    if doc_embedding is not None:
        dup_matches = search_duplicates(doc_embedding, threshold=0.45)
        if dup_matches:
            top_dup = dup_matches[0]
            doc_holder_name = (fields.get("full_name") or {}).get("normalized") or ""
            if not doc_holder_name or top_dup["full_name"].upper() != doc_holder_name.upper():
                database.duplicate_identity = True
                database.matched_person_id = top_dup["person_id"]
                database.duplicate_reason = (
                    f"{top_dup['full_name']} (Person #{top_dup['person_id']}, "
                    f"similarity {top_dup['similarity']:.1%})"
                )

    # 7. Explainable Risk Scoring Engine
    risk = calculate_risk(quality, ocr, mrz, validation, tamper, face, database)

    from app.services.aadhaar_service import mask_numbers
    if document_type == "aadhaar":
        ocr = mask_numbers(ocr)
        database = type(database)(**mask_numbers(database.model_dump()))
        if doc_number:
            import hashlib
            doc_number = "SHA256" + hashlib.sha256(doc_number.encode()).hexdigest().upper()

    now = datetime.now(timezone.utc).isoformat()
    case_id = f"CASE-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{file_id[:8].upper()}"

    payload = {
        "case_id": case_id,
        "timestamp": now,
        "file_id": file_id,
        "document_type": document_type,
        "document": document,
        "expiry": ocr.get("expiry", {"applicable": False, "status": "NOT_APPLICABLE"}),
        "qr": ocr.get("qr", {"status": "NOT_APPLICABLE"}),
        "filename": safe_filename,
        "officer_id": officer_id[:64],
        "quality": quality,
        "ocr": ocr,
        "mrz": mrz,
        "validation": validation.model_dump(),
        "tamper": tamper.model_dump(),
        "face": face.model_dump(),
        "database": database.model_dump(),
        "risk": risk.model_dump(),
        "officer_decision": None,
    }

    # Persist in session cache and SQLite/PostgreSQL case-management database
    create_or_update_session(case_id, payload)
    try:
        from app.services.case_persistence_service import persist_screening_case
        persist_screening_case(
            db,
            case_id=case_id,
            file_id=file_id,
            document_type=document_type,
            doc_number=doc_number,
            extracted_fields=fields,
            mrz=mrz,
            quality=quality,
            ocr=ocr,
            tamper=tamper,
            face=face,
            database=database,
            risk=risk,
            officer_id=officer_id[:64] if officer_id else None,
        )
    except Exception as exc:
        logger.warning("Could not persist case to database: %s", exc)

    # Optional audit work starts only after existing persistence has completed.
    from app.services.blockchain_service import prepare_safely, anchor_safely
    audit_result = prepare_safely(case_id)
    payload["blockchain_audit"] = audit_result
    if "id" in audit_result:
        background_tasks.add_task(anchor_safely, audit_result["id"])
    return ScreeningResponse(**payload)


@router.get("/cases")
def get_cases(db: Session = Depends(get_db)) -> dict:
    """List recent screening sessions for the officer dashboard."""
    from app.routers.cases import list_database_cases
    sessions = list_sessions()
    session_ids = {item["case_id"] for item in sessions}
    database_cases = [item.model_dump(mode="json") for item in list_database_cases(db) if item.case_id not in session_ids]
    return {"success": True, "cases": sessions + database_cases}


@router.get("/cases/{case_id}")
def get_case_details(case_id: str, db: Session = Depends(get_db)) -> dict:
    """Retrieve complete audit trail and screening result for a case ID."""
    result = get_session(case_id)
    if result:
        return {"success": True, "case": result}
    from app.routers.cases import find_database_case
    stored = find_database_case(db, case_id)
    if not stored:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening case '{case_id}' was not found.",
        )
    return {"success": True, "case": stored.model_dump(mode="json")}


@router.post("/cases/{case_id}/decision")
def post_officer_decision(
    case_id: str,
    background_tasks: BackgroundTasks,
    req: OfficerDecisionRequest = Body(...),
) -> dict:
    """Record an official officer screening decision (APPROVE, REJECT, MANUAL_VERIFICATION)."""
    updated = record_officer_decision(
        case_id=case_id,
        decision=req.decision,
        notes=req.notes,
        officer_id=req.officer_id,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening case '{case_id}' was not found.",
        )

    # Also update SQLite verification_cases row if it exists
    try:
        from app.database import SessionLocal
        from app.models import VerificationCase
        db = SessionLocal()
        try:
            vc = db.query(VerificationCase).filter(VerificationCase.case_id == case_id).first()
            if vc:
                vc.decision = req.decision
                vc.officer_id = req.officer_id
                vc.officer_notes = req.notes
                db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning("Could not update decision in database: %s", exc)

    from app.services.blockchain_service import prepare_safely, anchor_safely
    audit_result = prepare_safely(case_id, "OFFICER_DECISION", new_decision=True)
    if "id" in audit_result:
        background_tasks.add_task(anchor_safely, audit_result["id"])
    return {
        "success": True,
        "message": f"Decision '{req.decision}' recorded successfully.",
        "case": updated,
        "blockchain_audit": audit_result,
    }


@router.get("/documents/{document_number}/status")
def document_status(document_number: str) -> dict:
    """Query synthetic local registry for a document number status."""
    return database_lookup(document_number).model_dump()
