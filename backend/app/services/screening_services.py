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


def database_lookup(number: str | None, extracted_fields: dict[str, Any] | None = None, document_type: str | None = None) -> DatabaseResult:
    """Query SQLite registry and perform multi-field cross-validation."""
    if not number:
        return DatabaseResult(
            found=False,
            status="UNABLE_TO_CHECK",
            blacklisted=False,
            note="No document number was available for database query.",
        )

    from app.database import SessionLocal
    from app.models import Document, Person, Watchlist

    key = strip_non_alnum(number).upper()
    db = SessionLocal()
    try:
        from sqlalchemy import func
        keys = [key]
        if document_type == "aadhaar":
            import hashlib
            keys.append("SHA256" + hashlib.sha256(key.encode()).hexdigest().upper())
        query = db.query(Document).filter(func.replace(Document.document_number, " ", "").in_(keys))
        if document_type:
            query = query.filter(func.lower(Document.document_type) == document_type.lower())
        doc = query.first()
        if not doc:
            hit = db.query(Watchlist).filter(Watchlist.active == True,
                func.replace(Watchlist.document_number, " ", "").in_(keys)).first()
            if hit:
                return DatabaseResult(found=False, status="BLACKLISTED", blacklisted=True,
                                      note="Document identifier appears on the local watchlist.")
            return DatabaseResult(
                found=False,
                status="NOT_FOUND",
                blacklisted=False,
                note="Document number was not found in the verification database.",
            )

        person = db.query(Person).filter(Person.id == doc.person_id).first()
        if not person:
            return DatabaseResult(
                found=True,
                status="FOUND",
                blacklisted=False,
                note="Document found but person record is missing.",
            )

        # Check watchlist by document number OR person_id
        watchlist_entry = db.query(Watchlist).filter(
            Watchlist.active == True,  # noqa: E712
            (func.replace(Watchlist.document_number, " ", "").in_(keys)) | (Watchlist.person_id == person.id),
        ).first()

        is_blacklisted = watchlist_entry is not None

        # Build the record dict for response (same shape as before)
        record = {
            "document_number": doc.document_number,
            "full_name": person.full_name,
            "date_of_birth": person.date_of_birth or "",
            "nationality": person.nationality or "",
            "date_of_expiry": doc.expiry_date or "",
            "registered_status": doc.status,
        }

        if doc.document_type.lower() == "aadhaar":
            from app.services.aadhaar_service import mask_numbers
            record = mask_numbers(record)

        # Multi-field cross-validation
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
                rec_name = person.full_name.upper()
                ext_clean = strip_non_alnum(extracted_name).upper()
                rec_clean = strip_non_alnum(rec_name)
                if ext_clean == rec_clean or all(
                    part in ext_clean for part in rec_name.split() if len(part) > 2
                ):
                    field_matches["full_name"] = "MATCH"
                else:
                    field_matches["full_name"] = "MISMATCH"
                    is_mismatch = True

            # 2. Compare Date of Birth
            extracted_dob = (extracted_fields.get("date_of_birth") or {}).get("normalized")
            if extracted_dob and person.date_of_birth:
                if compare_date_values(extracted_dob, person.date_of_birth):
                    field_matches["date_of_birth"] = "MATCH"
                else:
                    field_matches["date_of_birth"] = "MISMATCH"
                    is_mismatch = True

            # 3. Compare Nationality
            extracted_nat = (extracted_fields.get("nationality") or {}).get("normalized")
            if extracted_nat and person.nationality:
                clean_ext_nat = strip_non_alnum(extracted_nat).upper()
                clean_rec_nat = strip_non_alnum(person.nationality).upper()
                if clean_ext_nat == clean_rec_nat:
                    field_matches["nationality"] = "MATCH"
                else:
                    field_matches["nationality"] = "MISMATCH"
                    is_mismatch = True

            # 4. Compare Date of Expiry
            extracted_exp = (extracted_fields.get("date_of_expiry") or {}).get("normalized")
            if extracted_exp and doc.expiry_date:
                if compare_date_values(extracted_exp, doc.expiry_date):
                    field_matches["date_of_expiry"] = "MATCH"
                else:
                    field_matches["date_of_expiry"] = "MISMATCH"
                    is_mismatch = True

        # Determine status string
        status_str = "MATCH"
        if is_mismatch:
            status_str = "MISMATCH"
        elif is_blacklisted:
            status_str = "BLACKLISTED"
        elif doc.status == "EXPIRED":
            status_str = "EXPIRED"
        elif doc.status == "SUSPICIOUS":
            status_str = "SUSPICIOUS"
        else:
            status_str = "FOUND"

        watchlist_info = None
        if watchlist_entry:
            watchlist_info = {
                "matched": True,
                "reason": watchlist_entry.reason,
                "severity": watchlist_entry.severity,
            }

        return DatabaseResult(
            found=True,
            status=status_str,
            blacklisted=is_blacklisted,
            source="SENTINELAI SIMULATED DEMO DATABASE",
            note=doc.note or "Database record lookup complete.",
            record=record,
            field_matches=field_matches,
        )
    finally:
        db.close()



def validate_document(fields: dict[str, Any], mrz: dict[str, Any], document_type: str = "passport") -> ValidationResult:
    """Consolidated document validation layer."""
    codes: list[str] = []
    messages: list[str] = []
    consistency: dict[str, str] = {}

    # 1. Required Fields Check
    document_type = document_type.lower()
    if document_type != "passport":
        required = {"aadhaar": ("full_name", "id_number"), "visa": ("name", "visa_number"),
                    "national_id": ("name", "id_number")}.get(document_type, ())
        for key in required:
            if not (fields.get(key) or {}).get("normalized"):
                codes.append("MISSING_REQUIRED_FIELD")
                messages.append(f"Required field {key} was not extracted.")
        if document_type == "aadhaar":
            identifier = (fields.get("id_number") or {}).get("normalized")
            if identifier and not re.fullmatch(r"\d{12}", identifier):
                codes.append("INVALID_DOCUMENT_NUMBER")
                messages.append("Aadhaar identifier must contain 12 digits.")
        if document_type == "visa":
            expiry = (fields.get("expiry_date") or {}).get("normalized")
            if expiry and expiry < date.today().isoformat():
                codes.append("DOCUMENT_EXPIRED")
                messages.append("Visa has expired.")
        codes.append("AUTHENTICITY_NOT_VERIFIED" if document_type != "unknown" else "UNKNOWN_DOCUMENT")
        messages.append("Secondary / manual verification required; issuer authenticity is not verified.")
        return ValidationResult(valid=False, status="REVIEW", reason_codes=list(dict.fromkeys(codes)), messages=messages)
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

        # Compare Full Name
        ocr_name = (fields.get("full_name") or {}).get("normalized") or (fields.get("surname") or {}).get("normalized")
        mrz_name = (mrz.get("full_name") or {}).get("normalized") or (mrz.get("surname") or {}).get("normalized") if isinstance(mrz.get("full_name"), dict) or isinstance(mrz.get("surname"), dict) else None
        if ocr_name and mrz_name:
            c_ocr_name = strip_non_alnum(str(ocr_name)).upper()
            c_mrz_name = strip_non_alnum(str(mrz_name)).upper()
            if c_ocr_name == c_mrz_name or c_ocr_name in c_mrz_name or c_mrz_name in c_ocr_name or sorted(re.findall(r"[A-Z]+", str(ocr_name).upper())) == sorted(re.findall(r"[A-Z]+", str(mrz_name).upper())):
                consistency["full_name"] = "MATCH"
            else:
                consistency["full_name"] = "MISMATCH"
                codes.append("OCR_MRZ_MISMATCH")
                messages.append(f"Name mismatch: OCR ({ocr_name}) vs MRZ ({mrz_name}).")
        else:
            consistency["full_name"] = "UNAVAILABLE"

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


    if "OCR_MRZ_MISMATCH" in validation.reason_codes:

        indicators.append(
            Indicator(
                type="OCR_MRZ_MISMATCH",
                severity="HIGH",
                description="Important identity values conflict between the visual zone and machine-readable zone.",
            )
        )

    if "MRZ_CHECK_FAILED" in validation.reason_codes:

        indicators.append(
            Indicator(
                type="MRZ_CHECK_FAILED",
                severity="HIGH",
                description="Machine-readable zone check-digit calculation failed.",
            )
        )

    if quality.get("ocr_readiness", 0) < 45:

        indicators.append(
            Indicator(
                type="IMAGE_QUALITY",
                severity="MEDIUM",
                description="Degraded image quality reduces readability; this does not establish tampering.",
            )
        )

    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        arr = np.asarray(image, dtype=np.float32)

        # 1. Resave error heuristic; neither authenticity verification nor ML confidence
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=75)
        buffer.seek(0)
        recompressed = Image.open(buffer).convert("RGB")
        diff = ImageChops.difference(image, recompressed)
        diff_arr = np.asarray(diff, dtype=np.float32)
        ela_score = float(diff_arr.mean())
        if ela_score > 12.0:

            indicators.append(
                Indicator(
                    type="COMPRESSION_DISCREPANCY",
                    severity="MEDIUM",
                    description="Elevated resave error; compression or image detail can cause this. Content tampering is not established.",
                )
            )

        # 2. Edge Gradient & Sharpening Density
        gray = np.asarray(image.convert("L"), dtype=np.float32)
        edges = np.abs(np.diff(gray, axis=1)).mean() if gray.shape[1] > 1 else 0
        if edges > 45:

            indicators.append(
                Indicator(
                    type="EDGE_ANOMALY",
                    severity="MEDIUM",
                    description="High edge gradient density detected, consistent with text overlay or aggressive sharpening.",
                )
            )
        elif float(arr.std()) < 15:

            indicators.append(
                Indicator(
                    type="LOW_VARIATION",
                    severity="LOW",
                    description="Image has low pixel variation; capture quality may limit analysis.",
                )
            )

        # 3. Metadata analysis
        if image.info and ("Software" in image.info or "Adobe" in str(image.info)):

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

    return ForensicResult(
        tamper_risk="LOW",
        recompression_detected=any(i.type == "COMPRESSION_DISCREPANCY" for i in indicators),
        metadata_anomaly=any(i.type == "METADATA_EDIT_HISTORY" for i in indicators),
        score=0,
        indicators=indicators,
    )


def compare_faces(document_data: bytes, selfie_data: bytes | None) -> FaceResult:
    """1:1 Biometric Face Verification — delegates to face_service (InsightFace/ArcFace)."""
    from app.services.face_service import verify_faces
    return verify_faces(document_data, selfie_data)


# ---------------------------------------------------------------------------
# Configurable risk weights (points added per signal)
# ---------------------------------------------------------------------------
RISK_WEIGHTS: dict[str, int] = {
    "WATCHLIST_MATCH": 35,
    "DATABASE_MISMATCH": 25,
    "DATABASE_FLAGGED": 20,
    "MRZ_MISSING": 20,
    "MRZ_CHECK_FAILED": 25,
    "OCR_MRZ_CONFLICT": 25,
    "DOCUMENT_EXPIRED": 15,
    "INVALID_DATES": 15,
    "FACE_MISMATCH": 25,
    "FACE_FAILED": 15,
    "TAMPER_HIGH": 25,
    "TAMPER_MEDIUM": 15,
    "LOW_OCR_CONFIDENCE": 10,
    "MISSING_FIELDS": 15,
    "POOR_QUALITY": 10,
    "DUPLICATE_IDENTITY": 35,
}


def calculate_risk(
    quality: dict[str, Any],
    ocr: dict[str, Any],
    mrz: dict[str, Any],
    validation: ValidationResult,
    tamper: ForensicResult,
    face: FaceResult,
    database: DatabaseResult,
) -> RiskResult:
    """Explainable 0-100 Risk Engine with explicit weighted score breakdown.

    Risk Levels:
        0–29   → LOW RISK
        30–59  → MEDIUM RISK
        60–79  → HIGH PRIORITY REVIEW
        80–100 → CRITICAL
    """
    score = 0
    reasons: list[dict[str, Any]] = []

    def add_reason(code: str, desc: str, severity: str = "MEDIUM"):
        nonlocal score
        points = RISK_WEIGHTS.get(code, 10)
        score += points
        reasons.append({
            "code": code,
            "applicable": True,
            "points": points,
            "severity": severity,
            "description": desc,
        })

    # 1. Critical Watchlist & Database Flag
    if database.blacklisted:
        add_reason("WATCHLIST_MATCH", "Identity is flagged on the immigration watchlist / blacklist.", "HIGH")
    elif database.status == "MISMATCH":
        add_reason("DATABASE_MISMATCH", "Identity details conflict with registry records.", "HIGH")
    elif database.status == "SUSPICIOUS":
        add_reason("DATABASE_FLAGGED", "Registry record marked as suspicious.", "HIGH")

    # 2. Duplicate Identity Detection
    if database.duplicate_identity:
        dup_name = database.duplicate_reason or "another registered individual"
        add_reason("DUPLICATE_IDENTITY",
                   f"Face matches {dup_name} — possible multiple identity fraud.", "HIGH")

    document_type = (ocr.get("document") or {}).get("type", "PASSPORT").lower()
    mrz_applicable = document_type == "passport" and mrz.get("applicable", True)
    expiry_applicable = document_type in {"passport", "visa"}

    # 3. MRZ Integrity
    if mrz_applicable and not mrz.get("mrz_detected"):
        add_reason("MRZ_MISSING", "Document machine-readable zone was not detected.", "MEDIUM")
    elif mrz_applicable and not mrz.get("mrz_valid"):
        add_reason("MRZ_CHECK_FAILED", "ICAO machine-readable zone check-digit calculation failed.", "HIGH")

    # 4. OCR vs MRZ Consistency
    if mrz_applicable and "OCR_MRZ_MISMATCH" in validation.reason_codes:
        add_reason("OCR_MRZ_CONFLICT", "Conflict detected between visual zone text and MRZ data.", "HIGH")

    # 5. Document Expiration & Date Sequences
    if expiry_applicable and ("DOCUMENT_EXPIRED" in validation.reason_codes or database.status == "EXPIRED"):
        add_reason("DOCUMENT_EXPIRED", "Document has expired and is no longer valid for travel.", "MEDIUM")
    if expiry_applicable and "INVALID_DATE_SEQUENCE" in validation.reason_codes:
        add_reason("INVALID_DATES", "Chronological contradiction detected in issue/expiry dates.", "MEDIUM")

    # 6. Biometric Face Verification
    if face.match is False:
        sim_pct = int((face.similarity or 0) * 100)
        add_reason("FACE_MISMATCH",
                   f"Live selfie facial similarity ({sim_pct}%) is below verification threshold.", "HIGH")
    elif face.status in {"FAILED", "UNAVAILABLE", "MODEL_UNAVAILABLE", "UNABLE_TO_VERIFY"}:
        add_reason("FACE_FAILED",
                   f"Face verification failed: {face.reason}", "MEDIUM")

    # 7. Forensic & Tampering
    if tamper.content_tamper_detected and tamper.tamper_risk == "HIGH":
        add_reason("TAMPER_HIGH", "Forensic analysis detected strong indicators of image tampering.", "HIGH")
    elif tamper.content_tamper_detected and tamper.tamper_risk == "MEDIUM":
        add_reason("TAMPER_MEDIUM", "Forensic analysis identified review-worthy visual anomalies.", "MEDIUM")

    # 8. OCR Confidence & Missing Required Fields
    conf = ocr.get("confidence")
    if conf is not None and conf < 60:
        add_reason("LOW_OCR_CONFIDENCE",
                   f"OCR extraction confidence ({conf}%) is below optimal threshold.", "LOW")
    if "MISSING_REQUIRED_FIELD" in validation.reason_codes:
        add_reason("MISSING_FIELDS", "One or more mandatory identity fields could not be extracted.", "MEDIUM")

    # 9. Image Quality Readiness
    if quality.get("ocr_readiness", 100) < 50:
        add_reason("POOR_QUALITY",
                   "Capture quality (resolution/blur/lighting) is below recommended standard.", "LOW")

    total_score = min(score, 100)

    # Determine Risk Level Category
    if total_score >= 80 or database.blacklisted:
        risk_level: Any = "CRITICAL"
        recommendation = "REJECT_OR_INTERCEPT" if database.blacklisted else "IMMEDIATE_REVIEW"
    elif total_score >= 60:
        risk_level = "HIGH PRIORITY REVIEW"
        recommendation = "SECONDARY_INSPECTION"
    elif total_score >= 30:
        risk_level = "MEDIUM RISK"
        recommendation = "SECONDARY_INSPECTION"
    else:
        risk_level = "LOW RISK"
        recommendation = "PROCEED_WITH_OFFICER_REVIEW"

    if document_type != "passport" and total_score < 60 and not database.blacklisted:
        recommendation = "SECONDARY_MANUAL_VERIFICATION"
    incomplete = []
    if face.match is None:
        incomplete.append("Face verification incomplete: " + face.reason)
    if database.status in {"UNAVAILABLE", "UNABLE_TO_CHECK", "NOT_FOUND"}:
        incomplete.append("Identity could not be verified against the simulated registry.")
    if tamper.tamper_status == "UNAVAILABLE":
        incomplete.append("Forensic analysis is unavailable.")
    if incomplete:
        reasons.extend({"code": "VERIFICATION_INCOMPLETE", "applicable": True, "points": 0,
                        "severity": "MEDIUM", "description": message} for message in incomplete)
    if (incomplete or not validation.valid or face.match is False or tamper.content_tamper_detected) and risk_level == "LOW RISK" and document_type == "passport":
        recommendation = "SECONDARY_INSPECTION"
    checks = [{"signal": code, "applicable": applicable,
               "points": sum(r["points"] for r in reasons if r["code"] == code)}
              for code, applicable in [("MRZ_MISSING", mrz_applicable), ("MRZ_CHECK_FAILED", mrz_applicable),
                  ("OCR_MRZ_CONFLICT", mrz_applicable), ("DOCUMENT_EXPIRED", expiry_applicable)]]
    return RiskResult(
        checks=checks,
        risk_score=total_score,
        risk_level=risk_level,
        recommendation=recommendation,
        reasons=reasons,
    )

