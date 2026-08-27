"""Document image quality analysis for OCR readiness screening."""

from __future__ import annotations

import io
from typing import Literal

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

ResolutionLabel = Literal["Excellent", "Good", "Poor"]
BrightnessLabel = Literal["Excellent", "Good", "Poor"]
BlurLabel = Literal["Low", "Medium", "High"]


def _load_image_from_bytes(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Unable to read image data. The file may be corrupted.") from exc

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    return image


def _load_pdf_first_page(data: bytes) -> Image.Image:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ValueError("PDF processing is unavailable on this server.") from exc

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ValueError("Invalid or corrupted PDF file.") from exc

    if document.page_count < 1:
        document.close()
        raise ValueError("PDF file contains no pages.")

    try:
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()

    return image


def load_image_for_analysis(data: bytes, extension: str) -> Image.Image:
    if extension == ".pdf":
        return _load_pdf_first_page(data)
    return _load_image_from_bytes(data)


def classify_resolution(width: int, height: int) -> ResolutionLabel:
    pixels = width * height
    short_edge = min(width, height)

    if short_edge >= 1080 or pixels >= 1_500_000:
        return "Excellent"
    if short_edge >= 720 or pixels >= 500_000:
        return "Good"
    return "Poor"


def classify_brightness(value: float) -> BrightnessLabel:
    if 100 <= value <= 180:
        return "Excellent"
    if 70 <= value < 100 or 180 < value <= 210:
        return "Good"
    return "Poor"


def classify_blur(variance: float) -> BlurLabel:
    if variance >= 500:
        return "Low"
    if variance >= 100:
        return "Medium"
    return "High"


def calculate_brightness(image: Image.Image) -> float:
    gray = np.array(image.convert("L"), dtype=np.uint8)
    return round(float(np.mean(gray)), 1)


def calculate_blur_score(image: Image.Image) -> float:
    gray = np.array(image.convert("L"), dtype=np.uint8)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return round(float(laplacian.var()), 1)


def score_resolution(label: ResolutionLabel) -> int:
    return {"Excellent": 35, "Good": 22, "Poor": 10}[label]


def score_brightness(label: BrightnessLabel) -> int:
    return {"Excellent": 30, "Good": 20, "Poor": 8}[label]


def score_blur(label: BlurLabel) -> int:
    return {"Low": 35, "Medium": 20, "High": 8}[label]


def calculate_ocr_readiness(
    resolution_label: ResolutionLabel,
    brightness_label: BrightnessLabel,
    blur_label: BlurLabel,
) -> int:
    total = (
        score_resolution(resolution_label)
        + score_brightness(brightness_label)
        + score_blur(blur_label)
    )
    return min(total, 100)


def analyze_document_quality(data: bytes, extension: str) -> dict:
    image = load_image_for_analysis(data, extension)
    width, height = image.size

    resolution_label = classify_resolution(width, height)
    brightness_value = calculate_brightness(image)
    brightness_label = classify_brightness(brightness_value)
    blur_score = calculate_blur_score(image)
    blur_label = classify_blur(blur_score)
    ocr_readiness = calculate_ocr_readiness(
        resolution_label, brightness_label, blur_label
    )

    return {
        "resolution": {
            "width": width,
            "height": height,
            "label": resolution_label,
        },
        "brightness": {
            "value": brightness_value,
            "label": brightness_label,
        },
        "blur": {
            "score": blur_score,
            "label": blur_label,
        },
        "ocr_readiness": ocr_readiness,
    }
