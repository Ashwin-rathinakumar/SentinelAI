"""Face detection, embedding, verification, quality checks, and duplicate search.

Uses InsightFace (ArcFace) for 512-d face embeddings via ONNX Runtime.
Reports unavailable when InsightFace cannot run; never substitutes pixel comparison.
"""

from __future__ import annotations

import base64
import io
import logging
import pickle
import threading
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image

from app.schemas.screening import FaceResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FACE_MATCH_THRESHOLD = 0.45  # ArcFace cosine similarity threshold for 1:1
FACE_MIN_AREA_RATIO = 0.02   # Face bbox must be ≥ 2% of image area
FACE_BLUR_THRESHOLD = 50.0   # Laplacian variance threshold on face crop
FACE_DARK_THRESHOLD = 40     # Mean brightness threshold for face crop

# ---------------------------------------------------------------------------
# InsightFace singleton
# ---------------------------------------------------------------------------
_lock = threading.Lock()
_face_app: Any = None
_face_app_loaded = False
_using_insightface = False


def _load_face_app() -> Any:
    """Lazy-load InsightFace FaceAnalysis model (thread-safe singleton)."""
    global _face_app, _face_app_loaded, _using_insightface
    with _lock:
        if _face_app_loaded:
            return _face_app
        try:
            from insightface.app import FaceAnalysis
            app = FaceAnalysis(
                name="buffalo_l",
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=-1, det_size=(640, 640))
            _face_app = app
            _using_insightface = True
            logger.info("InsightFace ArcFace model loaded successfully (CPU).")
        except Exception as exc:
            logger.warning("InsightFace unavailable: %s", exc)
            _face_app = None
            _using_insightface = False
        _face_app_loaded = True
        return _face_app


def get_face_model_name() -> str:
    """Return the name of the active face model."""
    _load_face_app()
    return "ArcFace" if _using_insightface else "ArcFace_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Face quality data
# ---------------------------------------------------------------------------
@dataclass
class FaceQuality:
    quality_pass: bool = True
    no_face: bool = False
    multiple_faces: bool = False
    face_too_small: bool = False
    too_blurry: bool = False
    too_dark: bool = False
    face_count: int = 0
    reason: str | None = None


@dataclass
class FaceDetection:
    bbox: list[int] = field(default_factory=list)  # [x1, y1, x2, y2]
    embedding: np.ndarray | None = None
    crop_bgr: np.ndarray | None = None
    crop_b64: str | None = None
    score: float = 0.0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------
def _crop_and_encode(image_bgr: np.ndarray, bbox: list[int]) -> tuple[np.ndarray, str]:
    """Crop face region with margin and encode to base64 JPEG."""
    h, w = image_bgr.shape[:2]
    x1, y1, x2, y2 = bbox
    fw, fh = x2 - x1, y2 - y1
    margin_x = int(fw * 0.15)
    margin_y = int(fh * 0.15)
    cx1 = max(0, x1 - margin_x)
    cy1 = max(0, y1 - margin_y)
    cx2 = min(w, x2 + margin_x)
    cy2 = min(h, y2 + margin_y)
    crop = image_bgr[cy1:cy2, cx1:cx2]
    crop_resized = cv2.resize(crop, (128, 128))
    _, enc = cv2.imencode(".jpg", crop_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    b64 = f"data:image/jpeg;base64,{base64.b64encode(enc.tobytes()).decode('utf-8')}"
    return crop_resized, b64


def detect_faces_insightface(image_bgr: np.ndarray) -> list[FaceDetection]:
    """Detect faces using InsightFace and extract ArcFace embeddings."""
    app = _load_face_app()
    if app is None:
        return []
    faces = app.get(image_bgr)
    results = []
    for face in faces:
        bbox = [int(c) for c in face.bbox]
        crop, b64 = _crop_and_encode(image_bgr, bbox)
        results.append(FaceDetection(
            bbox=bbox,
            embedding=face.embedding,
            crop_bgr=crop,
            crop_b64=b64,
            score=float(face.det_score) if hasattr(face, 'det_score') else 0.0,
        ))
    return results


def detect_faces(image_bgr: np.ndarray) -> list[FaceDetection]:
    """Only real InsightFace detections can enter biometric comparison."""
    if _load_face_app() is None:
        return []
    return detect_faces_insightface(image_bgr)


def cosine_similarity(emb1: np.ndarray, emb2: np.ndarray) -> float:
    """Compute cosine similarity between two embeddings."""
    n1 = np.linalg.norm(emb1)
    n2 = np.linalg.norm(emb2)
    if n1 == 0 or n2 == 0:
        return 0.0
    return float(np.dot(emb1, emb2) / (n1 * n2))


# ---------------------------------------------------------------------------
# Face quality pre-check
# ---------------------------------------------------------------------------
def check_face_quality(image_bgr: np.ndarray, faces: list[FaceDetection]) -> FaceQuality:
    """Evaluate face quality before attempting comparison."""
    h, w = image_bgr.shape[:2]
    image_area = h * w

    if len(faces) == 0:
        return FaceQuality(quality_pass=False, no_face=True, face_count=0,
                           reason="NO_FACE_DETECTED")

    if len(faces) > 1:
        return FaceQuality(quality_pass=False, multiple_faces=True, face_count=len(faces),
                           reason="MULTIPLE_FACES_DETECTED")

    face = faces[0]
    x1, y1, x2, y2 = face.bbox
    face_area = (x2 - x1) * (y2 - y1)

    if face_area < image_area * FACE_MIN_AREA_RATIO:
        return FaceQuality(quality_pass=False, face_too_small=True, face_count=1,
                           reason="FACE_TOO_SMALL")

    # Check blur on face crop
    if face.crop_bgr is not None:
        gray_crop = cv2.cvtColor(face.crop_bgr, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
        if blur_score < FACE_BLUR_THRESHOLD:
            return FaceQuality(quality_pass=False, too_blurry=True, face_count=1,
                               reason="FACE_TOO_BLURRY")

        mean_brightness = float(gray_crop.mean())
        if mean_brightness < FACE_DARK_THRESHOLD:
            return FaceQuality(quality_pass=False, too_dark=True, face_count=1,
                               reason="FACE_TOO_DARK")

    return FaceQuality(quality_pass=True, face_count=1)


# ---------------------------------------------------------------------------
# 1:1 Face Verification (main entry point)
# ---------------------------------------------------------------------------
def verify_faces(document_data: bytes, selfie_data: bytes | None) -> FaceResult:
    """Full 1:1 biometric face verification pipeline."""
    model_name = get_face_model_name()
    threshold = FACE_MATCH_THRESHOLD
    if not _using_insightface:
        return FaceResult(status="UNABLE_TO_VERIFY", model=model_name, threshold=threshold,
                          reason="ArcFace model unavailable; biometric verification was not performed.")

    # Load document image and detect face
    try:
        doc_img = Image.open(io.BytesIO(document_data)).convert("RGB")
        doc_bgr = cv2.cvtColor(np.asarray(doc_img), cv2.COLOR_RGB2BGR)
        doc_faces = detect_faces(doc_bgr)
    except Exception as exc:
        return FaceResult(
            status="FAILED",
            reason=f"Failed to process document image: {exc}",
            model=model_name,
            threshold=threshold,
        )

    doc_b64 = doc_faces[0].crop_b64 if doc_faces else None
    doc_detected = len(doc_faces) > 0

    if not selfie_data:
        return FaceResult(
            face_detected_document=doc_detected,
            face_detected_selfie=False,
            image_quality="NOT_PROVIDED",
            status="NOT_PROVIDED",
            reason="No live selfie supplied; 1:1 facial verification was skipped.",
            document_face_crop=doc_b64,
            model=model_name,
            threshold=threshold,
        )

    # Load selfie and detect face
    try:
        selfie_img = Image.open(io.BytesIO(selfie_data)).convert("RGB")
        selfie_bgr = cv2.cvtColor(np.asarray(selfie_img), cv2.COLOR_RGB2BGR)
        selfie_faces = detect_faces(selfie_bgr)
    except Exception as exc:
        return FaceResult(
            face_detected_document=doc_detected,
            face_detected_selfie=False,
            status="FAILED",
            reason=f"Failed to process selfie image: {exc}",
            document_face_crop=doc_b64,
            model=model_name,
            threshold=threshold,
        )

    # Quality checks on selfie
    selfie_quality = check_face_quality(selfie_bgr, selfie_faces)
    if not selfie_quality.quality_pass:
        return FaceResult(
            face_detected_document=doc_detected,
            face_detected_selfie=False,
            status="FAILED",
            reason=f"{selfie_quality.reason}_IN_SELFIE",
            document_face_crop=doc_b64,
            model=model_name,
            threshold=threshold,
        )

    # Apply the same quality gates to the document portrait.
    doc_quality = check_face_quality(doc_bgr, doc_faces)
    if not doc_quality.quality_pass:
        doc_quality = check_face_quality(doc_bgr, doc_faces)
        return FaceResult(
            face_detected_document=False,
            face_detected_selfie=True,
            status="FAILED",
            reason=f"{doc_quality.reason}_IN_DOCUMENT",
            selfie_face_crop=selfie_faces[0].crop_b64 if selfie_faces else None,
            model=model_name,
            threshold=threshold,
        )

    # Both faces detected — compute similarity
    doc_face = doc_faces[0]
    selfie_face = selfie_faces[0]

    if doc_face.embedding is not None and selfie_face.embedding is not None:
        similarity = cosine_similarity(doc_face.embedding, selfie_face.embedding)
    else:
        return FaceResult(status="UNABLE_TO_VERIFY", model=model_name, threshold=threshold,
                          reason="Face embeddings unavailable; biometric comparison was not performed.")

    similarity = round(similarity, 4)
    match = similarity >= threshold

    return FaceResult(
        face_detected_document=True,
        face_detected_selfie=True,
        image_quality="BIOMETRIC_EMBEDDING_MATCH",
        similarity=similarity,
        match=match,
        status="MATCH" if match else "MISMATCH",
        reason=f"1:1 face similarity: {similarity:.2%} (threshold: {threshold:.0%}, model: {model_name}).",
        document_face_crop=doc_face.crop_b64,
        selfie_face_crop=selfie_face.crop_b64,
        model=model_name,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Embedding storage & duplicate identity search
# ---------------------------------------------------------------------------
def get_embedding_from_image(image_data: bytes) -> np.ndarray | None:
    """Extract face embedding from raw image bytes. Returns None if no face."""
    try:
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        faces = detect_faces(bgr)
        if check_face_quality(bgr, faces).quality_pass and faces[0].embedding is not None:
            return faces[0].embedding
    except Exception:
        pass
    return None


def store_embedding(person_id: int, embedding: np.ndarray, model_name: str = "ArcFace") -> None:
    """Store a face embedding in the database."""
    from app.database import SessionLocal
    from app.models import FaceEmbedding
    db = SessionLocal()
    try:
        blob = pickle.dumps(embedding)
        fe = FaceEmbedding(person_id=person_id, embedding=blob, model_name=model_name)
        db.add(fe)
        db.commit()
    finally:
        db.close()


def search_duplicates(
    embedding: np.ndarray,
    threshold: float = FACE_MATCH_THRESHOLD,
    exclude_person_id: int | None = None,
) -> list[dict[str, Any]]:
    """Linear cosine search across all stored embeddings for duplicates.

    Returns list of matches: [{person_id, similarity, full_name}]
    """
    from app.database import SessionLocal
    from app.models import FaceEmbedding, Person

    db = SessionLocal()
    matches: list[dict[str, Any]] = []
    try:
        query = db.query(FaceEmbedding)
        if exclude_person_id is not None:
            query = query.filter(FaceEmbedding.person_id != exclude_person_id)

        for fe in query.all():
            try:
                stored_emb = pickle.loads(fe.embedding)
                sim = cosine_similarity(embedding, stored_emb)
                if sim >= threshold:
                    person = db.query(Person).filter(Person.id == fe.person_id).first()
                    matches.append({
                        "person_id": fe.person_id,
                        "similarity": round(sim, 4),
                        "full_name": person.full_name if person else "UNKNOWN",
                    })
            except Exception:
                continue

        matches.sort(key=lambda m: m["similarity"], reverse=True)
    finally:
        db.close()
    return matches
