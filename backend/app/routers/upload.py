import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.schemas.upload import DocumentQuality, UploadResponse
from app.services.file_service import (
    generate_safe_filename,
    read_and_validate_upload,
    save_upload,
    validate_document_type,
)
from app.services.quality_service import analyze_document_quality

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        400: {"description": "Missing or empty file"},
        413: {"description": "File too large"},
        415: {"description": "Unsupported media type"},
        422: {"description": "Invalid document type or unreadable image"},
        500: {"description": "Server processing error"},
    },
)
async def upload_document(
    file: UploadFile = File(..., description="Document image or PDF"),
    document_type: str = Form(..., description="Type of identity document"),
) -> UploadResponse:
    validated_type = validate_document_type(document_type)

    try:
        data, extension, _ = await read_and_validate_upload(file)
        file_id, safe_filename = generate_safe_filename(extension)
        save_upload(data, safe_filename)

        quality_data = analyze_document_quality(data, extension)
        quality = DocumentQuality(**quality_data)

        return UploadResponse(
            file_id=file_id,
            filename=safe_filename,
            document_type=validated_type,
            file_size=len(data),
            quality=quality,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "Unable to process document.", "detail": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception("Upload processing failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Server processing error.",
                "detail": "An unexpected error occurred while analyzing the document.",
            },
        ) from exc
