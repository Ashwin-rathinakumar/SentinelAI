from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field

class OCRResult(BaseModel):
    raw_text: str = ""
    confidence: float | None = 0.0
    fields: dict[str, Any] = Field(default_factory=dict)
    mrz_text: list[str] = Field(default_factory=list)
    mrz: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)

class MRZResult(BaseModel):
    mrz_detected: bool = False
    valid: bool = False
    status: str = "MRZ_NOT_DETECTED"
    document_type: str | None = None
    issuing_country: str | None = None
    surname: str | None = None
    given_names: str | None = None
    document_number: str | None = None
    nationality: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    expiry_date: str | None = None
    personal_number: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)
    mrz_errors: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

class ValidationResult(BaseModel):
    valid: bool
    status: Literal['VALID', 'REVIEW', 'INVALID'] = 'REVIEW'
    reason_codes: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    consistency: dict[str, Literal['MATCH', 'MISMATCH', 'UNAVAILABLE']] = Field(default_factory=dict)

class Indicator(BaseModel):
    type: str
    severity: Literal['LOW', 'MEDIUM', 'HIGH']
    description: str

class ForensicResult(BaseModel):
    tamper_risk: Literal['LOW', 'MEDIUM', 'HIGH']
    score: int = Field(ge=0, le=100)
    indicators: list[Indicator] = Field(default_factory=list)

class FaceResult(BaseModel):
    face_detected_document: bool = False
    face_detected_selfie: bool = False
    image_quality: str = 'NOT_PROVIDED'
    similarity: float | None = None
    match: bool | None = None
    status: str = 'NOT_PROVIDED'
    reason: str = 'No selfie supplied; face verification was not run.'
    document_face_crop: str | None = None
    selfie_face_crop: str | None = None

class DatabaseResult(BaseModel):
    found: bool = False
    status: str = 'NOT_FOUND'
    blacklisted: bool = False
    source: str = 'SIMULATED DEMO DATABASE'
    note: str = 'Synthetic records only; not a government database.'
    record: dict[str, Any] | None = None
    field_matches: dict[str, str] = Field(default_factory=dict)

class RiskResult(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    risk_level: Literal['LOW RISK', 'MEDIUM RISK', 'HIGH PRIORITY REVIEW']
    recommendation: str
    reasons: list[dict[str, Any]] = Field(default_factory=list)

class OfficerDecisionRequest(BaseModel):
    decision: Literal['APPROVE', 'REJECT', 'MANUAL_VERIFICATION']
    notes: str | None = None
    officer_id: str | None = 'OFFICER-DEMO'

class OfficerDecision(BaseModel):
    decision: str
    notes: str | None = None
    officer_id: str
    timestamp: str

class ScreeningResponse(BaseModel):
    success: bool = True
    case_id: str
    timestamp: str
    file_id: str
    document_type: str
    filename: str
    quality: dict[str, Any]
    ocr: OCRResult
    mrz: dict[str, Any]
    validation: ValidationResult
    tamper: ForensicResult
    face: FaceResult
    database: DatabaseResult
    risk: RiskResult
    officer_decision: OfficerDecision | None = None

