"""Reusable OCR preprocessing. Original uploads are never overwritten."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.config import PROCESSED_DIR


def ensure_processed_directory() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def _pil_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"), dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype(np.float32)
    sums = pts.sum(axis=1)
    diffs = np.diff(pts, axis=1).reshape(4)
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = pts[np.argmin(sums)]
    ordered[2] = pts[np.argmax(sums)]
    ordered[1] = pts[np.argmin(diffs)]
    ordered[3] = pts[np.argmax(diffs)]
    return ordered


def _maybe_deskew_document(bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    height, width = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return bgr, False

    page = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(page)
    if area < 0.35 * width * height:
        return bgr, False

    peri = cv2.arcLength(page, True)
    approx = cv2.approxPolyDP(page, 0.02 * peri, True)
    if len(approx) != 4:
        return bgr, False

    corners = _order_corners(approx)
    width_a = np.linalg.norm(corners[1] - corners[0])
    width_b = np.linalg.norm(corners[2] - corners[3])
    height_a = np.linalg.norm(corners[3] - corners[0])
    height_b = np.linalg.norm(corners[2] - corners[1])
    max_w = int(max(width_a, width_b))
    max_h = int(max(height_a, height_b))
    if max_w < 80 or max_h < 80:
        return bgr, False

    destination = np.array(
        [[0, 0], [max_w - 1, 0], [max_w - 1, max_h - 1], [0, max_h - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(corners, destination)
    warped = cv2.warpPerspective(bgr, matrix, (max_w, max_h))
    return warped, True


def _resize_for_ocr(bgr: np.ndarray) -> tuple[np.ndarray, str | None]:
    height, width = bgr.shape[:2]
    short_edge = min(height, width)
    long_edge = max(height, width)
    note = None
    scale = 1.0
    if short_edge < 720:
        scale = 720 / max(short_edge, 1)
        note = "upscaled"
    elif long_edge > 2200:
        scale = 2200 / long_edge
        note = "downscaled"
    if scale != 1.0:
        bgr = cv2.resize(
            bgr,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
        )
    return bgr, note


def _illumination_correct(gray: np.ndarray) -> np.ndarray:
    blur = cv2.GaussianBlur(gray, (0, 0), 25)
    blur = np.clip(blur, 1, 255)
    return cv2.divide(gray, blur, scale=255)


def enhance_for_ocr(bgr: np.ndarray) -> np.ndarray:
    """Grayscale, contrast, denoise, sharpen, illumination correction."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    mean = float(np.mean(gray))
    if mean < 70:
        gray = cv2.convertScaleAbs(gray, alpha=1.35, beta=25)
    elif mean > 210:
        gray = cv2.convertScaleAbs(gray, alpha=0.85, beta=-15)

    gray = _illumination_correct(gray)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    gray = cv2.fastNlMeansDenoising(gray, None, 12, 7, 21)
    blur = cv2.GaussianBlur(gray, (0, 0), 1.0)
    sharp = cv2.addWeighted(gray, 1.4, blur, -0.4, 0)
    return cv2.cvtColor(sharp, cv2.COLOR_GRAY2BGR)


def threshold_variant(bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def rotate_bgr(bgr: np.ndarray, angle: int) -> np.ndarray:
    if angle % 360 == 0:
        return bgr
    if angle == 90:
        return cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(bgr, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return bgr


def preprocess_image(
    image: Image.Image, file_id: str
) -> tuple[np.ndarray, Path, list[str]]:
    """Return an enhanced BGR image and persist it separately from the original."""
    ensure_processed_directory()
    notes: list[str] = []

    oriented = ImageOps.exif_transpose(image) or image
    if oriented.size != image.size:
        notes.append("exif_orientation")

    bgr = _pil_to_bgr(oriented)
    bgr, resized_note = _resize_for_ocr(bgr)
    if resized_note:
        notes.append(resized_note)

    deskewed, warped = _maybe_deskew_document(bgr)
    if warped:
        bgr = deskewed
        notes.append("perspective_corrected")

    enhanced = enhance_for_ocr(bgr)
    notes.append("contrast_denoise_sharpen")

    processed_path = PROCESSED_DIR / f"{file_id}_ocr.png"
    cv2.imwrite(str(processed_path), enhanced)
    return enhanced, processed_path, notes
