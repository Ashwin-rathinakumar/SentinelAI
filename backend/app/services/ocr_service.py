"""OCR orchestration: preprocess, read the uploaded image, extract fields."""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from app.config import OCR_LOW_CONFIDENCE_THRESHOLD, OCR_MIN_TEXT_CHARS
from app.services.field_extractor import extract_fields
from app.services.document_type_service import detect_document_type, not_applicable_mrz
from app.services.aadhaar_service import extract_aadhaar, detect_qr
from app.services.mrz_service import extract_mrz
from app.services.ocr_engine import get_engine_name, regions_score, run_ocr
from app.services.preprocess_service import preprocess_image, rotate_bgr, threshold_variant
from app.services.quality_service import load_image_for_analysis

logger = logging.getLogger(__name__)

FAILED_MESSAGE = "Unable to reliably read the document."


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def _processing_time(elapse: list[float] | float | None, wall_ms: float) -> dict[str, Any]:
    engine_ms = None
    if isinstance(elapse, (list, tuple)):
        engine_ms = round(sum(float(part) for part in elapse) * 1000, 1)
    elif isinstance(elapse, (int, float)):
        engine_ms = round(float(elapse) * 1000, 1)
    return {
        "total_ms": wall_ms,
        "engine_ms": engine_ms,
    }


def _confidence_percent(regions: list[dict[str, Any]]) -> int | None:
    if not regions:
        return None
    mean = regions_score(regions)
    return int(round(mean * 100))


def _cluster_count(regions: list[dict[str, Any]]) -> int:
    if len(regions) < 2:
        return len(regions)
    ys = [
        min((point[1] for point in item.get("box") or [[0.0, 0.0]]), default=0.0)
        for item in regions
    ]
    ys.sort()
    gaps = [b - a for a, b in zip(ys, ys[1:])]
    if not gaps:
        return 1
    median = sorted(gaps)[len(gaps) // 2]
    return 1 + sum(1 for gap in gaps if gap > max(80.0, median * 4))


def _failed_result(start: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "status": "FAILED",
        "message": FAILED_MESSAGE,
        "raw_text": "",
        "confidence": None,
        "regions": [],
        "engine": get_engine_name(),
        "processing_time": _processing_time(None, _elapsed_ms(start)),
        "preprocess_notes": [],
        "processed_image": None,
        "fields": {},
        "mrz": None,
        "multiple_text_regions": False,
        "possible_multiple_documents": False,
    }
    if extra:
        payload.update(extra)
    return payload


def _best_ocr(image_bgr: np.ndarray) -> tuple[list[dict[str, Any]], list[float] | float | None, int, str]:
    attempts: list[tuple[float, list[dict[str, Any]], list[float] | float | None, int, str]] = []

    def consider(image: np.ndarray, angle: int, variant: str) -> None:
        regions, elapse = run_ocr(image)
        score = regions_score(regions) * max(len(regions), 1)
        attempts.append((score, regions, elapse, angle, variant))

    consider(image_bgr, 0, "enhanced")

    best_score = attempts[0][0]
    if best_score < 1.5 or len(attempts[0][1]) < 3:
        consider(threshold_variant(image_bgr), 0, "threshold")
        for angle in (90, 180, 270):
            consider(rotate_bgr(image_bgr, angle), angle, "rotated")

    attempts.sort(key=lambda item: item[0], reverse=True)
    _score, regions, elapse, angle, variant = attempts[0]
    return regions, elapse, angle, variant


def extract_document(file_id: str, data: bytes, extension: str, document_type: str) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        image = load_image_for_analysis(data, extension)
        processed, processed_path, notes = preprocess_image(image, file_id)
        regions, elapse, angle, variant = _best_ocr(processed)
        if angle:
            notes.append(f"orientation_{angle}")
        if variant != "enhanced":
            notes.append(variant)

        raw_text = "\n".join(item["text"] for item in regions)
        confidence = _confidence_percent(regions)
        wall_ms = _elapsed_ms(start)

        if not raw_text.strip() or (confidence is not None and confidence == 0):
            result = _failed_result(start)
            result["preprocess_notes"] = notes
            result["processed_image"] = processed_path.name
            result["processing_time"] = _processing_time(elapse, wall_ms)
            result["confidence"] = confidence
            result["regions"] = regions
            result["raw_text"] = raw_text
            return result

        document = detect_document_type(raw_text)
        document_type = document["type"].lower()
        mrz = extract_mrz(raw_text, regions) if document_type == "passport" else not_applicable_mrz()
        if document_type == "passport":
            mrz["applicable"] = True

        # If MRZ not found or invalid, attempt dedicated bottom-region MRZ pass
        if document_type == "passport" and (not mrz or not mrz.get("mrz_valid")):
            from app.services.preprocess_service import crop_and_enhance_mrz_region
            mrz_crop = crop_and_enhance_mrz_region(processed)
            mrz_regions, _ = run_ocr(mrz_crop)
            if mrz_regions:
                mrz_crop_text = "\n".join(item["text"] for item in mrz_regions)
                crop_mrz_res = extract_mrz(mrz_crop_text, mrz_regions)
                if crop_mrz_res.get("mrz_detected") and (crop_mrz_res.get("mrz_valid") or not (mrz and mrz.get("mrz_detected"))):
                    mrz = crop_mrz_res
                    notes.append("mrz_region_enhanced_pass")

        if document_type == "aadhaar":
            fields = extract_aadhaar(raw_text, regions)
        elif document_type == "unknown":
            fields = {}
        else:
            fields = extract_fields(document_type, raw_text, regions, mrz)
        mrz["applicable"] = document_type == "passport"
        expiry = {"applicable": document_type in {"passport", "visa"},
                  "status": "NOT_APPLICABLE" if document_type not in {"passport", "visa"} else "NOT_DETECTED"}
        expiry_value = (fields.get("date_of_expiry") or fields.get("expiry_date") or {}).get("normalized")
        if expiry["applicable"] and expiry_value:
            from datetime import date
            expiry.update(status="EXPIRED" if expiry_value < date.today().isoformat() else "VALID", value=expiry_value)

        status = "SUCCESS"
        message = None
        if confidence is not None and confidence < OCR_LOW_CONFIDENCE_THRESHOLD:
            status = "LOW_CONFIDENCE"
            message = "OCR completed with low confidence."
        elif len(raw_text.strip()) < OCR_MIN_TEXT_CHARS:
            status = "LOW_CONFIDENCE"
            message = "Only partial text could be read."

        clusters = _cluster_count(regions)
        return {
            "document": document,
            "expiry": expiry,
            "qr": detect_qr(processed) if document_type == "aadhaar" else {"status": "NOT_APPLICABLE"},
            "status": status,
            "message": message,
            "raw_text": raw_text,
            "confidence": confidence,
            "regions": regions,
            "engine": get_engine_name(),
            "processing_time": _processing_time(elapse, wall_ms),
            "preprocess_notes": notes,
            "processed_image": processed_path.name,
            "fields": fields,
            "mrz": mrz,
            "multiple_text_regions": len(regions) > 1,
            "possible_multiple_documents": clusters > 1,
        }
    except Exception:
        logger.exception("OCR processing failed for file_id=%s", file_id)
        return _failed_result(start)
