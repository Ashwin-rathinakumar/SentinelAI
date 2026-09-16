"""Database-backed case creation and read helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import Document, FaceResult, OCRResult, ScreeningCase, TamperResult, Traveller, WatchlistCheck
from app.schemas.case_management import CaseEnvelope, ScreeningCaseCreate, ScreeningCaseResponse

router = APIRouter(prefix="/api/cases", tags=["cases"])


def _new_case_id() -> str:
    return f"CASE-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}"


def _case_query(case_id: str | None = None):
    query = select(ScreeningCase).options(
        selectinload(ScreeningCase.document).selectinload(Document.traveller),
        selectinload(ScreeningCase.ocr_result),
        selectinload(ScreeningCase.face_result),
        selectinload(ScreeningCase.tamper_result),
        selectinload(ScreeningCase.watchlist_checks),
    )
    return query.where(ScreeningCase.case_id == case_id) if case_id else query


def serialize_case(case: ScreeningCase) -> ScreeningCaseResponse:
    document = case.document
    return ScreeningCaseResponse(
        case_id=case.case_id,
        document_id=case.document_id,
        extracted_document_number=case.extracted_document_number,
        created_at=case.created_at,
        traveller=document.traveller if document else None,
        document=document,
        ocr_result=case.ocr_result,
        face_result=case.face_result,
        tamper_result=case.tamper_result,
        watchlist_checks=case.watchlist_checks,
    )


def find_database_case(db: Session, case_id: str) -> ScreeningCaseResponse | None:
    case = db.scalar(_case_query(case_id))
    return serialize_case(case) if case else None


def list_database_cases(db: Session, limit: int = 100) -> list[ScreeningCaseResponse]:
    cases = db.scalars(_case_query().order_by(ScreeningCase.created_at.desc()).limit(limit)).all()
    return [serialize_case(case) for case in cases]


@router.post("", response_model=CaseEnvelope, status_code=status.HTTP_201_CREATED)
def create_case(payload: ScreeningCaseCreate, db: Session = Depends(get_db)) -> CaseEnvelope:
    if payload.document and not payload.traveller:
        raise HTTPException(422, "traveller is required when document is supplied")

    case_id = payload.case_id or _new_case_id()
    if db.scalar(select(ScreeningCase.id).where(ScreeningCase.case_id == case_id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "case_id already exists")

    document = None
    if payload.traveller:
        traveller = Traveller(**payload.traveller.model_dump())
        db.add(traveller)
        db.flush()
        if payload.document:
            document = Document(person_id=traveller.id, **payload.document.model_dump())
            db.add(document)
            db.flush()

    case = ScreeningCase(
        case_id=case_id,
        document_id=document.id if document else None,
        extracted_document_number=payload.extracted_document_number,
        watchlist_match=any(item.matched for item in payload.watchlist_checks),
        duplicate_identity=False,
    )
    db.add(case)
    db.flush()
    if payload.ocr_result:
        db.add(OCRResult(case_id=case_id, **payload.ocr_result.model_dump()))
    if payload.face_result:
        db.add(FaceResult(case_id=case_id, **payload.face_result.model_dump()))
    if payload.tamper_result:
        db.add(TamperResult(case_id=case_id, **payload.tamper_result.model_dump()))
    for check in payload.watchlist_checks:
        db.add(WatchlistCheck(case_id=case_id, **check.model_dump()))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "case data conflicts with an existing record") from exc

    # Reload from the database so POST and later GET serialization use the same
    # driver-level timestamp representation (notably with SQLite test fallback).
    db.expire_all()
    created = db.scalar(_case_query(case_id))
    return CaseEnvelope(case=serialize_case(created))
