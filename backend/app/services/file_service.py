"""Secure upload validation and storage."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

HTTP_413 = status.HTTP_413_CONTENT_TOO_LARGE

from app.config import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DOCUMENT_TYPES,
    MAX_UPLOAD_SIZE_BYTES,
    UPLOADS_DIR,
)


def ensure_uploads_directory() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def validate_document_type(document_type: str) -> str:
    normalized = document_type.strip().lower()
    if normalized not in DOCUMENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "Invalid document type.",
                "detail": f"Supported types: {', '.join(sorted(DOCUMENT_TYPES))}.",
            },
        )
    return normalized


def _sanitize_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^\w.\- ]", "", name).strip()
    return name or "upload"


def _resolve_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "Unsupported file extension.",
                "detail": "Supported formats: JPG, JPEG, PNG, PDF.",
            },
        )
    return extension


def _validate_mime_type(extension: str, content_type: str | None) -> None:
    if not content_type:
        return

    normalized = content_type.split(";")[0].strip().lower()
    allowed = ALLOWED_MIME_TYPES.get(extension, set())
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "Invalid MIME type for uploaded file.",
                "detail": f"Expected a valid {extension.lstrip('.').upper()} file.",
            },
        )


async def read_and_validate_upload(file: UploadFile) -> tuple[bytes, str, str]:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "No file provided.", "detail": "Please select a file to upload."},
        )

    sanitized = _sanitize_filename(file.filename)
    extension = _resolve_extension(sanitized)
    _validate_mime_type(extension, file.content_type)

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Empty file.", "detail": "The uploaded file contains no data."},
        )

    if len(data) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=HTTP_413,
            detail={
                "error": "File too large.",
                "detail": "Maximum allowed file size is 10 MB.",
            },
        )

    return data, extension, sanitized


def generate_safe_filename(extension: str) -> tuple[str, str]:
    file_id = uuid.uuid4().hex
    safe_name = f"{file_id}{extension}"
    return file_id, safe_name


def save_upload(data: bytes, safe_filename: str) -> None:
    ensure_uploads_directory()
    destination = UPLOADS_DIR / safe_filename
    destination.write_bytes(data)
