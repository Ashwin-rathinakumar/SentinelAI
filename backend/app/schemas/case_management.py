"""Request and response contracts for persisted screening cases."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TravellerCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=256)
    date_of_birth: str | None = Field(default=None, max_length=10)
    nationality: str | None = Field(default=None, max_length=10)


class TravellerResponse(TravellerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class DocumentCreate(BaseModel):
    document_number: str = Field(min_length=1, max_length=70)
    document_type: str = Field(default="passport", min_length=1, max_length=20)
    issue_date: str | None = Field(default=None, max_length=10)
    expiry_date: str | None = Field(default=None, max_length=10)
    status: str = Field(default="VALID", min_length=1, max_length=20)
    note: str | None = None


class DocumentResponse(DocumentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    person_id: int
    created_at: datetime


class WatchlistEntryCreate(BaseModel):
    person_id: int | None = None
    document_number: str | None = Field(default=None, max_length=70)
    reason: str = Field(min_length=1)
    severity: str = Field(default="MEDIUM", max_length=20)
    active: bool = True


class WatchlistEntryResponse(WatchlistEntryCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class OCRResultCreate(BaseModel):
    status: str = Field(default="PENDING", max_length=32)
    confidence: float | None = None
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class FaceResultCreate(BaseModel):
    status: str = Field(default="NOT_PROVIDED", max_length=32)
    similarity: float | None = None
    match: bool | None = None
    model_name: str | None = Field(default=None, max_length=64)
    threshold: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TamperResultCreate(BaseModel):
    status: str = Field(default="PENDING", max_length=32)
    detected: bool | None = None
    score: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class WatchlistCheckCreate(BaseModel):
    watchlist_entry_id: int | None = None
    matched: bool = False
    match_score: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: str
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OCRResultResponse(ResultResponse):
    status: str
    confidence: float | None
    extracted_fields: dict[str, Any]
    raw_text: str | None


class FaceResultResponse(ResultResponse):
    status: str
    similarity: float | None
    match: bool | None
    model_name: str | None
    threshold: float | None


class TamperResultResponse(ResultResponse):
    status: str
    detected: bool | None
    score: float | None


class WatchlistCheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: str
    watchlist_entry_id: int | None
    matched: bool
    match_score: float | None
    details: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ScreeningCaseCreate(BaseModel):
    case_id: str | None = Field(default=None, pattern=r"^CASE-[A-Za-z0-9-]{1,58}$")
    traveller: TravellerCreate | None = None
    document: DocumentCreate | None = None
    extracted_document_number: str | None = Field(default=None, max_length=70)
    ocr_result: OCRResultCreate | None = None
    face_result: FaceResultCreate | None = None
    tamper_result: TamperResultCreate | None = None
    watchlist_checks: list[WatchlistCheckCreate] = Field(default_factory=list)


class ScreeningCaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    case_id: str
    document_id: int | None
    extracted_document_number: str | None
    created_at: datetime
    traveller: TravellerResponse | None
    document: DocumentResponse | None
    ocr_result: OCRResultResponse | None
    face_result: FaceResultResponse | None
    tamper_result: TamperResultResponse | None
    watchlist_checks: list[WatchlistCheckResponse]


class CaseEnvelope(BaseModel):
    success: bool = True
    case: ScreeningCaseResponse
