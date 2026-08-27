from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile, status

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
    file: UploadFile = File(...),
    document_type: str = Form("passport"),
    selfie: UploadFile | None = File(None),
    officer_id: str = Form("OFFICER-DEMO"),
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
    validation = validate_document(fields, mrz)

    # 4. Forensic & Tamper Analysis
    tamper = forensic_analysis(data, quality, validation)

    # 5. Biometric Face Verification
    selfie_data = await selfie.read() if selfie else None
    face = compare_faces(data, selfie_data)

    # 6. Database Verification
    number_item = fields.get("passport_number") or fields.get("id_number") or {}
    doc_number = number_item.get("normalized")
    database = database_lookup(doc_number, extracted_fields=fields)

    # 7. Explainable Risk Scoring Engine
    risk = calculate_risk(quality, ocr, mrz, validation, tamper, face, database)

    now = datetime.now(timezone.utc).isoformat()
    case_id = f"CASE-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{file_id[:8].upper()}"

    payload = {
        "case_id": case_id,
        "timestamp": now,
        "file_id": file_id,
        "document_type": document_type,
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

    create_or_update_session(case_id, payload)
    return ScreeningResponse(**payload)


@router.get("/cases")
def get_cases() -> dict:
    """List recent screening sessions for the officer dashboard."""
    return {"success": True, "cases": list_sessions()}


@router.get("/cases/{case_id}")
def get_case_details(case_id: str) -> dict:
    """Retrieve complete audit trail and screening result for a case ID."""
    result = get_session(case_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening case '{case_id}' was not found.",
        )
    return {"success": True, "case": result}


@router.post("/cases/{case_id}/decision")
def post_officer_decision(
    case_id: str,
    req: OfficerDecisionRequest = Body(...),
) -> dict:
    """Record an official officer screening decision (APPROVE, REJECT, MANUAL_VERIFICATION)."""
    updated = record_officer_decision(
        case_id=case_id,
        decision=req.decision,
        notes=req.notes,
        officer_id=req.officer_id or "OFFICER-DEMO",
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screening case '{case_id}' was not found.",
        )
    return {
        "success": True,
        "message": f"Decision '{req.decision}' recorded successfully.",
        "case": updated,
    }


@router.get("/documents/{document_number}/status")
def document_status(document_number: str) -> dict:
    """Query synthetic local registry for a document number status."""
    return database_lookup(document_number).model_dump()

