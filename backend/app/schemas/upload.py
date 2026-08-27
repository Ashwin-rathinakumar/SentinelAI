from pydantic import BaseModel, Field

from app.schemas.ocr import OcrResult


class ResolutionQuality(BaseModel):
    width: int
    height: int
    label: str


class BrightnessQuality(BaseModel):
    value: float
    label: str


class BlurQuality(BaseModel):
    score: float
    label: str


class DocumentQuality(BaseModel):
    resolution: ResolutionQuality
    brightness: BrightnessQuality
    blur: BlurQuality
    ocr_readiness: int = Field(ge=0, le=100)


class UploadResponse(BaseModel):
    success: bool = True
    file_id: str
    filename: str
    document_type: str
    file_size: int
    quality: DocumentQuality


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    detail: str | None = None
