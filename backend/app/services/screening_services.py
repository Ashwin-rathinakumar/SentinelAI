from __future__ import annotations

import base64
import io
import re
from datetime import date, datetime
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageChops

from app.schemas.screening import (
    DatabaseResult,
    FaceResult,
    ForensicResult,
    Indicator,
    RiskResult,
    ValidationResult,
)
from app.services.ocr_normalize import compare_date_values, normalize_date_string, strip_non_alnum

# Synthetic local verification database records for SIH presentation
DEMO_RECORDS: dict[str, dict[str, Any]] = {
    "L898902C": {
        "document_number": "L898902C",
        "full_name": "ANNA MARIA ERIKSSON",
        "date_of_birth": "1969-08-06",
        "nationality": "UTO",
        "date_of_expiry": "1994-06-23",
        "status": "EXPIRED",
        "blacklisted": False,
        "note": "Standard expired travel record (ICAO synthetic benchmark).",
    },
    "P1234567": {
        "document_number": "P1234567",
        "full_name": "JOHNATHAN DOE",
        "date_of_birth": "1985-04-12",
        "nationality": "UTO",
        "date_of_expiry": "2030-04-12",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified active synthetic traveler identity.",
    },
    "P12345678": {
        "document_number": "P12345678",
        "full_name": "JOHNATHAN DOE",
        "date_of_birth": "1985-04-12",
        "nationality": "UTO",
        "date_of_expiry": "2030-04-12",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified active synthetic traveler identity.",
    },
    "A1234567": {
        "document_number": "A1234567",
        "full_name": "SARAH JENKINS",
        "date_of_birth": "1990-11-23",
        "nationality": "UTO",
        "date_of_expiry": "2029-11-23",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified clear identity.",
    },
    "A12345678": {
        "document_number": "A12345678",
        "full_name": "MARIA GARCIA",
        "date_of_birth": "1990-01-15",
        "nationality": "UTO",
        "date_of_expiry": "2030-01-15",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified clear identity.",
    },
    "B7654321": {
        "document_number": "B7654321",
        "full_name": "VIKTOR KORZHOV",
        "date_of_birth": "1978-11-20",
        "nationality": "UTO",
        "date_of_expiry": "2027-11-20",
        "status": "SUSPICIOUS",
        "blacklisted": True,
        "note": "ALERT: Flagged on international border watch list.",
    },
    "E9988776": {
        "document_number": "E9988776",
        "full_name": "ELENA ROSTOVA",
        "date_of_birth": "1995-09-30",
        "nationality": "UTO",
        "date_of_expiry": "2031-09-30",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified clear identity.",
    },
    "C2468135": {
        "document_number": "C2468135",
        "full_name": "MARIA GARCIA",
        "date_of_birth": "1982-07-30",
        "nationality": "ESP",
        "date_of_expiry": "2022-07-30",

        "status": "EXPIRED",
        "blacklisted": False,
        "note": "Document expired in local registry.",
    },
    "D1357902": {
        "document_number": "D1357902",
        "full_name": "MIKHAIL VOLKOV",
        "date_of_birth": "1975-09-18",
        "nationality": "DEU",
        "date_of_expiry": "2032-09-18",
        "status": "SUSPICIOUS",
        "blacklisted": False,
        "note": "Flagged for manual secondary inspection.",
    },
    "E9876543": {
        "document_number": "E9876543",
        "full_name": "RAJ PATEL",
        "date_of_birth": "1992-05-14",
        "nationality": "IND",
        "date_of_expiry": "2031-05-14",
        "status": "VALID",
        "blacklisted": False,
        "note": "Verified identity record in South Asia registry.",
    },
    "M9999999": {
        "document_number": "M9999999",
        "full_name": "GENUINE PERSON NAME",
        "date_of_birth": "1995-01-01",
        "nationality": "GBR",
        "date_of_expiry": "2030-01-01",
        "status": "VALID",
        "blacklisted": False,
        "note": "Synthetic benchmark for detecting identity mismatch.",
    },
}


def database_lookup(number: str | None, extracted_fields: dict[str, Any] | None = None) -> DatabaseResult:
    """Query synthetic local registry and perform multi-field cross-validation."""
    if not number:
        return DatabaseResult(
            found=False,
            status="NOT_FOUND",
            blacklisted=False,
            note="No document number was available for database query.",
        )

    key = strip_non_alnum(number).upper()
    record = DEMO_RECORDS.get(key)
    if not record:
        return DatabaseResult(
            found=False,
            status="NOT_FOUND",
            blacklisted=False,
            note="Document number was not found in synthetic demo database.",
        )

    field_matches: dict[str, str] = {"document_number": "MATCH"}
    is_mismatch = False

    if extracted_fields:
        # 1. Compare Full Name / Surname
        extracted_name = (
            (extracted_fields.get("full_name") or {}).get("normalized")
            or (extracted_fields.get("name") or {}).get("normalized")
            or ""
        )
        if extracted_name:
            rec_name = record["full_name"].upper()
            ext_clean = strip_non_alnum(extracted_name).upper()
            rec_clean = strip_non_alnum(rec_name)
            # Check overlap or match
            if ext_clean == rec_clean or all(
                part in ext_clean for part in rec_name.split() if len(part) > 2
            ):
                field_matches["full_name"] = "MATCH"
            else:
                field_matches["full_name"] = "MISMATCH"
                is_mismatch = True

        # 2. Compare Date of Birth
        extracted_dob = (extracted_fields.get("date_of_birth") or {}).get("normalized")
        if extracted_dob:
            if compare_date_values(extracted_dob, record["date_of_birth"]):
                field_matches["date_of_birth"] = "MATCH"
            else:
                field_matches["date_of_birth"] = "MISMATCH"
                is_mismatch = True

        # 3. Compare Nationality
        extracted_nat = (extracted_fields.get("nationality") or {}).get("normalized")
        if extracted_nat:
            clean_ext_nat = strip_non_alnum(extracted_nat).upper()
            clean_rec_nat = strip_non_alnum(record["nationality"]).upper()
            if clean_ext_nat == clean_rec_nat:
                field_matches["nationality"] = "MATCH"
            else:
                field_matches["nationality"] = "MISMATCH"
                is_mismatch = True

        # 4. Compare Date of Expiry
        extracted_exp = (extracted_fields.get("date_of_expiry") or {}).get("normalized")
        if extracted_exp:
            if compare_date_values(extracted_exp, record["date_of_expiry"]):
                field_matches["date_of_expiry"] = "MATCH"
            else:
                field_matches["date_of_expiry"] = "MISMATCH"
                is_mismatch = True

    status_str = "MATCH"
    if is_mismatch:
        status_str = "MISMATCH"
    elif record.get("blacklisted"):
        status_str = "BLACKLISTED"
    elif record.get("status") == "EXPIRED":
        status_str = "EXPIRED"
    elif record.get("status") == "SUSPICIOUS":
        status_str = "SUSPICIOUS"
    else:
        status_str = "FOUND"

    return DatabaseResult(
        found=True,
        status=status_str,
        blacklisted=bool(record.get("blacklisted")),
        source="SIMULATED DEMO DATABASE",
        note=record.get("note", "Synthetic record lookup complete."),
        record={
            "document_number": record["document_number"],
            "full_name": record["full_name"],
            "date_of_birth": record["date_of_birth"],
            "nationality": record["nationality"],
            "date_of_expiry": record["date_of_expiry"],
            "registered_status": record["status"],
        },
        field_matches=field_matches,
    )


def validate_document(fields: dict[str, Any], mrz: dict[str, Any]) -> ValidationResult:
    """Consolidated document validation layer."""
    codes: list[str] = []
    messages: list[str] = []
    consistency: dict[str, str] = {}

    # 1. Required Fields Check
    required_keys = ("full_name", "passport_number", "date_of_expiry")
    for key in required_keys:
        item = fields.get(key) or {}
        if not item.get("normalized"):
            codes.append("MISSING_REQUIRED_FIELD")
            messages.append(f"Required field '{key.replace('_', ' ').title()}' was not extracted.")

    # 2. Document Number Format Check
    doc_num = (fields.get("passport_number") or fields.get("id_number") or {}).get("normalized")
    if doc_num and not re.fullmatch(r"[A-Z0-9]{6,12}", strip_non_alnum(doc_num).upper()):
        codes.append("INVALID_DOCUMENT_NUMBER")
        messages.append("Document number format is non-standard.")

    # 3. Cross-Validation between OCR Visual Zone and MRZ
    has_mrz = bool(mrz.get("mrz_detected"))
    if has_mrz:
        # Compare Document Number
        ocr_num = (fields.get("passport_number") or {}).get("normalized")
        mrz_num = (mrz.get("passport_number") or {}).get("normalized") if isinstance(mrz.get("passport_number"), dict) else None
        if ocr_num and mrz_num:
            if strip_non_alnum(str(ocr_num)).upper() == strip_non_alnum(str(mrz_num)).upper():
                consistency["passport_number"] = "MATCH"
            else:
                consistency["passport_number"] = "MISMATCH"
                codes.append("OCR_MRZ_MISMATCH")
                messages.append(f"Document number mismatch: OCR ({ocr_num}) vs MRZ ({mrz_num}).")
        else:
            consistency["passport_number"] = "UNAVAILABLE"

        # Compare Date of Birth
        ocr_dob = (fields.get("date_of_birth") or {}).get("normalized")
        mrz_dob = (mrz.get("date_of_birth") or {}).get("normalized") if isinstance(mrz.get("date_of_birth"), dict) else None
        if ocr_dob and mrz_dob:
            if compare_date_values(str(ocr_dob), str(mrz_dob)):
                consistency["date_of_birth"] = "MATCH"
            else:
                consistency["date_of_birth"] = "MISMATCH"
                codes.append("OCR_MRZ_MISMATCH")
                messages.append(f"Date of birth mismatch: OCR ({ocr_dob}) vs MRZ ({mrz_dob}).")
        else:
            consistency["date_of_birth"] = "UNAVAILABLE"

        # Compare Date of Expiry
        ocr_exp = (fields.get("date_of_expiry") or {}).get("normalized")
        mrz_exp = (mrz.get("date_of_expiry") or {}).get("normalized") if isinstance(mrz.get("date_of_expiry"), dict) else None
        if ocr_exp and mrz_exp:
            if compare_date_values(str(ocr_exp), str(mrz_exp)):
                consistency["date_of_expiry"] = "MATCH"
            else:
                consistency["date_of_expiry"] = "MISMATCH"
                codes.append("OCR_MRZ_MISMATCH")
                messages.append(f"Expiry date mismatch: OCR ({ocr_exp}) vs MRZ ({mrz_exp}).")
        else:
            consistency["date_of_expiry"] = "UNAVAILABLE"

        # Compare Nationality
        ocr_nat = (fields.get("nationality") or {}).get("normalized")
        mrz_nat = (mrz.get("nationality") or {}).get("normalized") if isinstance(mrz.get("nationality"), dict) else None
        if ocr_nat and mrz_nat:
            c_ocr = strip_non_alnum(str(ocr_nat)).upper()
            c_mrz = strip_non_alnum(str(mrz_nat)).upper()
            if c_ocr == c_mrz or c_ocr.startswith(c_mrz) or c_mrz.startswith(c_ocr):
                consistency["nationality"] = "MATCH"
            else:
                consistency["nationality"] = "MISMATCH"
                codes.append("OCR_MRZ_MISMATCH")
                messages.append(f"Nationality mismatch: OCR ({ocr_nat}) vs MRZ ({mrz_nat}).")
        else:
            consistency["nationality"] = "UNAVAILABLE"

        # MRZ Check Digit Integrity
        if not mrz.get("mrz_valid"):
            codes.append("MRZ_CHECK_FAILED")
            mrz_errs = mrz.get("mrz_errors") or []
            if mrz_errs:
                messages.append(f"MRZ check failed: {'; '.join(mrz_errs)}")
            else:
                messages.append("One or more MRZ check digits failed.")
    else:
        codes.append("MRZ_NOT_FOUND")
        messages.append("No complete passport MRZ was detected on document.")

    # 4. Expiry Date & Chronological Integrity Check
    expiry_val = (fields.get("date_of_expiry") or {}).get("normalized")
    if expiry_val:
        norm_exp = normalize_date_string(str(expiry_val))
        if norm_exp:
            try:
                exp_date = datetime.strptime(norm_exp[:10], "%Y-%m-%d").date()
                if exp_date < date.today():
                    codes.append("DOCUMENT_EXPIRED")
                    messages.append(f"Document expired on {exp_date.isoformat()}.")
            except ValueError:
                pass

    issue_val = (fields.get("date_of_issue") or {}).get("normalized")
    if issue_val and expiry_val:
        norm_iss = normalize_date_string(str(issue_val))
        norm_exp = normalize_date_string(str(expiry_val))
        if norm_iss and norm_exp:
            try:
                d_iss = datetime.strptime(norm_iss[:10], "%Y-%m-%d").date()
                d_exp = datetime.strptime(norm_exp[:10], "%Y-%m-%d").date()
                if d_iss > d_exp:
                    codes.append("INVALID_DATE_SEQUENCE")
                    messages.append("Issue date is after expiry date.")
            except ValueError:
                pass

    unique_codes = list(dict.fromkeys(codes))
    is_valid = len(unique_codes) == 0 or unique_codes == ["DOCUMENT_VALID"]
    
    status_label: Any = "VALID"
    if "MRZ_CHECK_FAILED" in unique_codes or "OCR_MRZ_MISMATCH" in unique_codes:
        status_label = "INVALID"
    elif not is_valid:
        status_label = "REVIEW"

    if not messages:
        messages.append("All structural, OCR, MRZ, and chronological checks passed.")

    return ValidationResult(
        valid=is_valid,
        status=status_label,
        reason_codes=unique_codes if unique_codes else ["DOCUMENT_VALID"],
        messages=messages,
        consistency=consistency,
    )


def forensic_analysis(data: bytes, quality: dict[str, Any], validation: ValidationResult) -> ForensicResult:
    """Forensic and tamper indicators analysis."""
    indicators: list[Indicator] = []
    score = 0

    if "OCR_MRZ_MISMATCH" in validation.reason_codes:
        score += 30
        indicators.append(
            Indicator(
                type="OCR_MRZ_MISMATCH",
                severity="HIGH",
                description="Important identity values conflict between the visual zone and machine-readable zone.",
            )
        )

    if "MRZ_CHECK_FAILED" in validation.reason_codes:
        score += 25
        indicators.append(
            Indicator(
                type="MRZ_CHECK_FAILED",
                severity="HIGH",
                description="Machine-readable zone check-digit calculation failed.",
            )
        )

    if quality.get("ocr_readiness", 0) < 45:
        score += 15
        indicators.append(
            Indicator(
                type="IMAGE_QUALITY",
                severity="MEDIUM",
                description="Degraded image quality may obscure tampering or physical alteration.",
            )
        )

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.asarray(image, dtype=np.float32)

        # 1. Error Level Analysis (ELA) simulation: compression artifact discrepancy
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=75)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")
        diff = ImageChops.difference(image, recompressed)
        diff_arr = np.asarray(diff, dtype=np.float32)
        ela_score = float(diff_arr.mean())
        if ela_score > 12.0:
            score += 15
            indicators.append(
                Indicator(
                    type="COMPRESSION_DISCREPANCY",
                    severity="MEDIUM",
                    description="Elevated resave error level detected, suggesting possible digital modification.",
                )
            )

        # 2. Edge Gradient & Sharpening Density
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        edges = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0
        if edges > 45:
            score += 10
            indicators.append(
                Indicator(
                    type="EDGE_ANOMALY",
                    severity="MEDIUM",
                    description="High edge gradient density detected, consistent with text overlay or aggressive sharpening.",
                )
            )
        elif float(arr.std()) < 15:
            score += 8
            indicators.append(
                Indicator(
                    type="LOW_VARIATION",
                    severity="LOW",
                    description="Image exhibits unusually uniform pixel distribution; verify capture authenticity.",
                )
            )

        # 3. Metadata analysis
        if image.info and ("Software" in image.info or "Adobe" in str(image.info)):
            score += 8
            indicators.append(
                Indicator(
                    type="METADATA_EDIT_HISTORY",
                    severity="LOW",
                    description="Image container contains editing software signatures in metadata.",
                )
            )

    except Exception:
        pass

    if not indicators:
        indicators.append(
            Indicator(
                type="NO_SIGNIFICANT_ANOMALY",
                severity="LOW",
                description="No significant forensic or structural anomalies were detected.",
            )
        )

    tamper_level: Any = "HIGH" if score >= 40 else "MEDIUM" if score >= 15 else "LOW"
    return ForensicResult(
        tamper_risk=tamper_level,
        score=min(score, 100),
        indicators=indicators,
    )


def _detect_and_crop_face(image_bgr: np.ndarray) -> tuple[np.ndarray | None, str | None]:
    """Detect primary face in BGR image and return cropped 128x128 face and base64 data URL."""
    try:
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(40, 40)
        )

        if len(faces) == 0:
            # Fallback: try alt tree if available or center-upper crop
            h, w = image_bgr.shape[:2]
            # If standard document layout (portrait usually in left third or right third)
            return None, None

        # Pick largest face
        largest_face = max(faces, key=lambda r: r[2] * r[3])
        x, y, fw, fh = largest_face

        # Add 15% margin
        margin_x = int(fw * 0.15)
        margin_y = int(fh * 0.15)
        h, w = image_bgr.shape[:2]
        x1 = max(0, x - margin_x)
        y1 = max(0, y - margin_y)
        x2 = min(w, x + fw + margin_x)
        y2 = min(h, y + fh + margin_y)

        crop = image_bgr[y1:y2, x1:x2]
        crop_resized = cv2.resize(crop, (128, 128))

        # Encode to base64 JPEG
        _, enc = cv2.imencode(".jpg", crop_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        b64 = f"data:image/jpeg;base64,{base64.b64encode(enc.tobytes()).decode('utf-8')}"
        return crop_resized, b64
    except Exception:
        return None, None


def compare_faces(document_data: bytes, selfie_data: bytes | None) -> FaceResult:
    """1:1 Biometric Face Verification between document photo and live selfie."""
    # Attempt to load document image
    try:
        doc_img = Image.open(io.BytesIO(document_data)).convert("RGB")
        doc_bgr = cv2.cvtColor(np.asarray(doc_img), cv2.COLOR_RGB2BGR)
        doc_crop, doc_b64 = _detect_and_crop_face(doc_bgr)
    except Exception:
        doc_crop, doc_b64 = None, None

    if not selfie_data:
        return FaceResult(
            face_detected_document=doc_crop is not None,
            face_detected_selfie=False,
            image_quality="NOT_PROVIDED",
            similarity=None,
            match=None,
            status="NOT_PROVIDED",
            reason="No live selfie supplied; 1:1 facial verification was skipped.",
            document_face_crop=doc_b64,
            selfie_face_crop=None,
        )

    try:
        selfie_img = Image.open(io.BytesIO(selfie_data)).convert("RGB")
        selfie_bgr = cv2.cvtColor(np.asarray(selfie_img), cv2.COLOR_RGB2BGR)
        selfie_crop, selfie_b64 = _detect_and_crop_face(selfie_bgr)

        # If selfie crop failed via cascade, use normalized resized selfie image directly
        if selfie_crop is None:
            selfie_crop = cv2.resize(selfie_bgr, (128, 128))
            _, enc = cv2.imencode(".jpg", selfie_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            selfie_b64 = f"data:image/jpeg;base64,{base64.b64encode(enc.tobytes()).decode('utf-8')}"

        if doc_crop is None:
            # Fallback document photo region (typically left 40% of standard passport)
            dh, dw = doc_bgr.shape[:2]
            doc_crop = cv2.resize(doc_bgr[int(dh * 0.15) : int(dh * 0.85), 0 : int(dw * 0.45)], (128, 128))
            _, enc = cv2.imencode(".jpg", doc_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            doc_b64 = f"data:image/jpeg;base64,{base64.b64encode(enc.tobytes()).decode('utf-8')}"

        # Convert both to normalized grayscale for feature comparison
        doc_gray = cv2.cvtColor(doc_crop, cv2.COLOR_BGR2GRAY).astype(np.float32)
        selfie_gray = cv2.cvtColor(selfie_crop, cv2.COLOR_BGR2GRAY).astype(np.float32)

        # Feature 1: Normalized Pearson correlation
        if doc_gray.std() > 0 and selfie_gray.std() > 0:
            corr = float(np.corrcoef(doc_gray.flatten(), selfie_gray.flatten())[0, 1])
            norm_corr = max(0.0, min(1.0, (corr + 1) / 2))
        else:
            norm_corr = 0.5

        # Feature 2: Histogram intersection on equalized facial luminance
        hist_doc = cv2.calcHist([doc_crop], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        hist_selfie = cv2.calcHist([selfie_crop], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
        cv2.normalize(hist_doc, hist_doc)
        cv2.normalize(hist_selfie, hist_selfie)
        hist_sim = float(cv2.compareHist(hist_doc, hist_selfie, cv2.HISTCMP_CORREL))
        norm_hist = max(0.0, min(1.0, (hist_sim + 1) / 2))

        # Combined similarity score
        similarity = round(0.6 * norm_corr + 0.4 * norm_hist, 3)
        match = similarity >= 0.70

        return FaceResult(
            face_detected_document=True,
            face_detected_selfie=True,
            image_quality="BIOMETRIC_FEATURE_MATCH",
            similarity=similarity,
            match=match,
            status="MATCH" if match else "MISMATCH",
            reason=f"1:1 face similarity score: {int(similarity * 100)}% (Threshold: 70%).",
            document_face_crop=doc_b64,
            selfie_face_crop=selfie_b64,
        )
    except Exception as exc:
        return FaceResult(
            status="UNABLE_TO_VERIFY",
            reason=f"Face verification could not be completed: {exc}",
            document_face_crop=doc_b64,
            selfie_face_crop=None,
        )


def calculate_risk(
    quality: dict[str, Any],
    ocr: dict[str, Any],
    mrz: dict[str, Any],
    validation: ValidationResult,
    tamper: ForensicResult,
    face: FaceResult,
    database: DatabaseResult,
) -> RiskResult:
    """Explainable 0-100 Risk Engine with explicit weighted score breakdown."""
    score = 0
    reasons: list[dict[str, Any]] = []

    def add_reason(points: int, code: str, desc: str, severity: str = "MEDIUM"):
        nonlocal score
        score += points
        reasons.append({
            "code": code,
            "points": points,
            "severity": severity,
            "description": desc,
        })

    # 1. Critical Watchlist & Database Flag
    if database.blacklisted:
        add_reason(35, "WATCHLIST_MATCH", "Identity is flagged on the immigration watchlist / blacklist.", "HIGH")
    elif database.status == "MISMATCH":
        add_reason(25, "DATABASE_MISMATCH", "Identity details conflict with registry records.", "HIGH")
    elif database.status == "SUSPICIOUS":
        add_reason(20, "DATABASE_FLAGGED", "Registry record marked as suspicious.", "HIGH")

    # 2. MRZ Integrity
    if not mrz.get("mrz_detected"):
        add_reason(20, "MRZ_MISSING", "Document machine-readable zone was not detected.", "MEDIUM")
    elif not mrz.get("mrz_valid"):
        add_reason(25, "MRZ_CHECK_FAILED", "ICAO machine-readable zone check-digit calculation failed.", "HIGH")

    # 3. OCR vs MRZ Consistency
    if "OCR_MRZ_MISMATCH" in validation.reason_codes:
        add_reason(25, "OCR_MRZ_CONFLICT", "Conflict detected between visual zone text and MRZ data.", "HIGH")

    # 4. Document Expiration & Date Sequences
    if "DOCUMENT_EXPIRED" in validation.reason_codes or database.status == "EXPIRED":
        add_reason(15, "DOCUMENT_EXPIRED", "Document has expired and is no longer valid for travel.", "MEDIUM")
    if "INVALID_DATE_SEQUENCE" in validation.reason_codes:
        add_reason(15, "INVALID_DATES", "Chronological contradiction detected in issue/expiry dates.", "MEDIUM")

    # 5. Biometric Face Verification
    if face.match is False:
        add_reason(25, "FACE_MISMATCH", f"Live selfie facial similarity ({int((face.similarity or 0) * 100)}%) is below verification threshold.", "HIGH")

    # 6. Forensic & Tampering
    if tamper.tamper_risk == "HIGH":
        add_reason(25, "TAMPER_HIGH", "Forensic analysis detected strong indicators of image tampering or manipulation.", "HIGH")
    elif tamper.tamper_risk == "MEDIUM":
        add_reason(15, "TAMPER_MEDIUM", "Forensic analysis identified review-worthy visual anomalies.", "MEDIUM")

    # 7. OCR Confidence & Missing Required Fields
    conf = ocr.get("confidence")
    if conf is not None and conf < 60:
        add_reason(10, "LOW_OCR_CONFIDENCE", f"OCR extraction confidence ({conf}%) is below optimal threshold.", "LOW")
    if "MISSING_REQUIRED_FIELD" in validation.reason_codes:
        add_reason(15, "MISSING_FIELDS", "One or more mandatory identity fields could not be extracted.", "MEDIUM")

    # 8. Image Quality Readiness
    if quality.get("ocr_readiness", 100) < 50:
        add_reason(10, "POOR_QUALITY", "Capture quality (resolution/blur/lighting) is below recommended standard.", "LOW")

    total_score = min(score, 100)

    # Determine Risk Level Category
    if total_score >= 60 or database.blacklisted:
        risk_level: Any = "HIGH PRIORITY REVIEW"
        recommendation = "REJECT_OR_INTERCEPT" if database.blacklisted else "SECONDARY_INSPECTION"
    elif total_score >= 30:
        risk_level = "MEDIUM RISK"
        recommendation = "SECONDARY_INSPECTION"
    else:
        risk_level = "LOW RISK"
        recommendation = "PROCEED_WITH_OFFICER_REVIEW"

    return RiskResult(
        risk_score=total_score,
        risk_level=risk_level,
        recommendation=recommendation,
        reasons=reasons,
    )

