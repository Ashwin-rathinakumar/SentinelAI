"""Local OCR engine wrapper (PaddleOCR models via RapidOCR ONNX)."""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_engine_lock = threading.Lock()
_engine: Any = None
_engine_name = "rapidocr-onnxruntime"
_fallback_name = "tesseract"
_engine_error: str | None = None


def get_engine_name() -> str:
    return _fallback_name if isinstance(_engine, tuple) and _engine[0] == 'tesseract' else _engine_name


def _load_engine() -> Any:
    global _engine, _engine_error
    with _engine_lock:
        if _engine is not None:
            return _engine
        try:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
            _engine_error = None
            logger.info("OCR engine initialized: %s", _engine_name)
            return _engine
        except Exception as exc:
            logger.warning("RapidOCR unavailable; using Tesseract fallback: %s", exc)
            try:
                import pytesseract
                from PIL import Image
                if not pytesseract.get_tesseract_version():
                    raise RuntimeError('tesseract binary not found')
                _engine = ('tesseract', pytesseract, Image)
                _engine_error = None
                return _engine
            except Exception as fallback_exc:
                _engine_error = "OCR engine is unavailable."
                logger.exception("Failed to initialize OCR fallback")
                raise RuntimeError(_engine_error) from fallback_exc


def _box_to_list(box: Any) -> list[list[float]]:
    array = np.array(box, dtype=float).reshape(-1, 2)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in array]


def run_ocr(image_bgr: np.ndarray) -> tuple[list[dict[str, Any]], list[float] | float | None]:
    """Run OCR on a BGR numpy image. Confidence values come from the engine only."""
    engine = _load_engine()
    if isinstance(engine, tuple) and engine[0] == 'tesseract':
        import time
        started = time.perf_counter()
        pytesseract, Image = engine[1], engine[2]
        rgb = image_bgr[:, :, ::-1]
        data = pytesseract.image_to_data(Image.fromarray(rgb), config='--psm 6', output_type=pytesseract.Output.DICT)
        regions = []
        for i, text in enumerate(data.get('text', [])):
            text = str(text).strip()
            try: confidence = float(data['conf'][i]) / 100
            except (TypeError, ValueError): confidence = 0
            if text and confidence >= 0:
                x, y, w, h = [int(data[key][i]) for key in ('left','top','width','height')]
                regions.append({'text': text, 'confidence': round(max(0, confidence), 4), 'box': [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]})
        return regions, time.perf_counter() - started
    result, elapse = engine(image_bgr)
    regions: list[dict[str, Any]] = []
    if not result:
        return regions, elapse

    for item in result:
        if not item or len(item) < 3:
            continue
        box, text, score = item[0], item[1], item[2]
        if text is None:
            continue
        text_value = str(text).strip()
        if not text_value:
            continue
        try:
            confidence = float(score)
        except (TypeError, ValueError):
            continue
        regions.append(
            {
                "text": text_value,
                "confidence": round(confidence, 4),
                "box": _box_to_list(box),
            }
        )
    return regions, elapse


def regions_score(regions: list[dict[str, Any]]) -> float:
    if not regions:
        return 0.0
    total = sum(float(item["confidence"]) for item in regions)
    return total / len(regions)
