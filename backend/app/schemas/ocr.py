from typing import Any

from pydantic import BaseModel, Field


class FieldValue(BaseModel):
    raw: str | None = None
    normalized: str | None = None
    status: str


class OcrRegion(BaseModel):
    text: str
    confidence: float
    box: list[list[float]] = Field(default_factory=list)


class ProcessingTime(BaseModel):
    total_ms: float
    engine_ms: float | None = None


class OcrResult(BaseModel):
    status: str
    message: str | None = None
    raw_text: str = ""
    confidence: int | None = None
    regions: list[OcrRegion] = Field(default_factory=list)
    engine: str
    processing_time: ProcessingTime
    preprocess_notes: list[str] = Field(default_factory=list)
    processed_image: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    mrz: dict[str, Any] | None = None
    multiple_text_regions: bool = False
    possible_multiple_documents: bool = False


class SessionResponse(BaseModel):
    success: bool = True
    session_id: str
    file_id: str
    filename: str
    document_type: str
    file_size: int
    quality: dict[str, Any]
    ocr: OcrResult
    created_at: str | None = None
    updated_at: str | None = None
