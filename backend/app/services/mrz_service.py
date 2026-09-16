"""ICAO 9303 MRZ detection, parsing, and check-digit validation."""

from __future__ import annotations

import re
from typing import Any

from app.services.ocr_normalize import (
    CONFUSION_TO_DIGIT,
    CONFUSION_TO_LETTER,
    mrz_sanitize_line,
    normalize_date_string,
    sanitize_mrz_field,
)

CHAR_VALUES = {
    **{str(index): index for index in range(10)},
    **{chr(ord("A") + index): 10 + index for index in range(26)},
    "<": 0,
}
WEIGHTS = (7, 3, 1)


def _char_value(char: str) -> int | None:
    return CHAR_VALUES.get(char)


def compute_check_digit(data: str) -> str | None:
    total = 0
    for index, char in enumerate(data):
        value = _char_value(char)
        if value is None:
            return None
        total += value * WEIGHTS[index % 3]
    return str(total % 10)


def validate_check_digit(data: str, check: str) -> tuple[bool, str | None]:
    expected = compute_check_digit(data)
    if expected is None:
        return False, "MRZ field contains invalid characters."
    if check != expected:
        return False, f"Check digit mismatch (expected {expected}, got {check})."
    return True, None


def _group_mrz_regions(regions: list[Any]) -> list[str]:
    """Group bounding boxes by Y-coordinate to reconstruct full horizontal MRZ lines."""
    dict_regions = [r for r in regions if isinstance(r, dict) and str(r.get("text", "")).strip()]
    if not dict_regions:
        return []

    # Sort by Y then X
    sorted_regions = sorted(
        dict_regions,
        key=lambda item: (
            min((p[1] for p in item.get("box") or [[0, 0]]), default=0),
            min((p[0] for p in item.get("box") or [[0, 0]]), default=0),
        ),
    )

    lines: list[list[str]] = []
    current_y = None
    current_line: list[str] = []

    for r in sorted_regions:
        box = r.get("box") or [[0, 0]]
        ys = [p[1] for p in box]
        h = max(ys) - min(ys) if len(ys) >= 2 else 20
        y = min(ys)
        threshold_y = max(12.0, h * 0.7)

        if current_y is None or abs(y - current_y) <= threshold_y:
            current_line.append(str(r["text"]))
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            if current_line:
                lines.append(current_line)
            current_line = [str(r["text"])]
            current_y = y
    if current_line:
        lines.append(current_line)

    return ["".join(parts) for parts in lines]


def _candidate_lines(raw_text: str, regions: list[Any]) -> tuple[list[str], str]:
    lines: list[str] = []

    # 1. Spatial line grouping from bounding boxes
    for spatially_merged in _group_mrz_regions(regions):
        sanitized = mrz_sanitize_line(spatially_merged)
        if len(sanitized) >= 25 and sanitized not in lines:
            lines.append(sanitized)

    # 2. Individual region elements
    dict_regions = [r for r in regions if isinstance(r, dict)]
    for region in sorted(
        dict_regions,
        key=lambda item: (
            min((point[1] for point in item.get("box") or [[0, 0]]), default=0),
            min((point[0] for point in item.get("box") or [[0, 0]]), default=0),
        ),
    ):
        sanitized = mrz_sanitize_line(str(region.get("text", "")))
        if len(sanitized) >= 25 and sanitized not in lines:
            lines.append(sanitized)

    for item in regions:
        if isinstance(item, str):
            sanitized = mrz_sanitize_line(item)
            if len(sanitized) >= 25 and sanitized not in lines:
                lines.append(sanitized)

    # 3. Raw text lines
    for raw_line in raw_text.splitlines():
        sanitized = mrz_sanitize_line(raw_line)
        if len(sanitized) >= 25 and sanitized not in lines:
            lines.append(sanitized)

    collapsed = mrz_sanitize_line(raw_text)
    return lines, collapsed


def _normalize_td3_line2(raw: str) -> str:
    if len(raw) < 28:
        return raw[:44].ljust(44, "<")
    prefix = raw[:28]
    rem = raw[28:]
    rem_clean = rem.rstrip("<")
    if rem_clean and rem_clean[-1].isdigit():
        check_digit = rem_clean[-1]
        opt = rem_clean[:-1]
        opt_15 = opt[:15].ljust(15, "<")
        return (prefix + opt_15 + check_digit)[:44]
    return raw[:44].ljust(44, "<")


def _find_td3(lines: list[str], collapsed: str) -> tuple[str, str] | None:
    candidates: list[tuple[int, str, str]] = []

    for i in range(len(lines)):
        first_candidate = lines[i]
        # Match TD3 Line 1 header P< or P[A-Z] followed by country and name with <<
        m1 = re.search(r"(P[<A-Z0-9][A-Z<]{3}[A-Z<]+<<[A-Z<]*)", first_candidate)
        if not m1:
            m1 = re.search(r"(P[<A-Z][A-Z0-9<]{3}[A-Z0-9<]{2,}<<[A-Z0-9<]*)", first_candidate)
        if not m1:
            continue
        line1_raw = m1.group(1)
        if "<<" not in line1_raw:
            continue
        line1 = line1_raw[:44].ljust(44, "<")

        for j in range(len(lines)):
            if i == j:
                continue
            second_candidate = lines[j]
            # Match TD3 Line 2 structure: 9 chars doc + check + 3 alpha nat + 6 digit DOB + check + sex + 6 digit exp + check
            m2 = re.search(r"([A-Z0-9<]{9}[0-9][A-Z015826<]{3}[0-9]{6}[0-9][MFX<][0-9]{6}[0-9][A-Z0-9<]*)", second_candidate)
            if not m2:
                continue
            line2 = _normalize_td3_line2(m2.group(1))

            if len(line1) == 44 and len(line2) == 44:
                score = i + j
                ok_doc, _ = validate_check_digit(line2[0:9], line2[9])
                if ok_doc:
                    score += 20
                ok_dob, _ = validate_check_digit(line2[13:19], line2[19])
                if ok_dob:
                    score += 20
                ok_exp, _ = validate_check_digit(line2[21:27], line2[27])
                if ok_exp:
                    score += 20

                comp_data = line2[0:10] + line2[13:20] + line2[21:43]
                ok_comp, _ = validate_check_digit(comp_data, line2[43])
                if ok_comp:
                    score += 30

                if any(noise in line1 for noise in ["COUNTRY", "PASSPORT", "PAYS", "TYPE"]):
                    score -= 50

                candidates.append((score, line1, line2))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1], candidates[0][2]

    return None



def _find_td2(lines: list[str], collapsed: str) -> tuple[str, str] | None:
    for i in range(len(lines)):
        first_candidate = lines[i]
        m1 = re.search(r"([IACV]<[A-Z]{3}[A-Z0-9<]{5,})", first_candidate)
        if not m1:
            continue
        line1_raw = m1.group(1)
        if "<<" not in line1_raw:
            continue
        line1 = line1_raw[:36].ljust(36, "<")

        for j in range(len(lines)):
            if i == j:
                continue
            second_candidate = lines[j]
            m2 = re.search(r"([A-Z0-9<]{9}[0-9][A-Z015826<]{3}[0-9]{6}[0-9][MFX<][0-9]{6}[0-9][A-Z0-9<]*)", second_candidate)
            if not m2:
                continue
            line2_raw = m2.group(1)
            line2 = line2_raw[:36].ljust(36, "<")

            if len(line1) == 36 and len(line2) == 36:
                return line1, line2

    return None


def _find_td1(lines: list[str], collapsed: str) -> tuple[str, str, str] | None:
    for i in range(len(lines)):
        m1 = re.search(r"([IAC]<[A-Z]{3}[A-Z0-9<]{9}[0-9][A-Z0-9<]*)", lines[i])
        if not m1:
            continue
        line1 = m1.group(1)[:30].ljust(30, "<")

        for j in range(len(lines)):
            if j == i:
                continue
            m2 = re.search(r"([0-9]{6}[0-9][MFX<][0-9]{6}[0-9][A-Z015826<]{3}[A-Z0-9<]*)", lines[j])
            if not m2:
                continue
            line2 = m2.group(1)[:30].ljust(30, "<")

            for k in range(len(lines)):
                if k == i or k == j:
                    continue
                if "<<" in lines[k]:
                    line3 = lines[k][:30].ljust(30, "<")
                    return line1, line2, line3

    return None


def _parse_names(name_field: str) -> tuple[str | None, str | None, str | None]:
    parts = name_field.split("<<")
    if not parts:
        return None, None, None
    surname = parts[0].replace("<", " ").strip()
    surname = re.sub(r"\s+", " ", surname) or None

    given = None
    if len(parts) > 1:
        given = parts[1].replace("<", " ").strip()
        given = re.sub(r"\s+", " ", given) or None

    if surname and given:
        full = f"{given} {surname}".strip()
    elif surname:
        full = surname
    elif given:
        full = given
    else:
        full = None

    return full, surname, given


def _field(raw: str | None, normalized: str | None = None) -> dict[str, str | None]:
    if raw is None:
        return {"raw": None, "normalized": None}
    return {
        "raw": raw,
        "normalized": normalized if normalized is not None else raw.replace("<", "").strip() or None,
    }


def _format_mrz_date(yymmdd: str) -> str | None:
    if not yymmdd or len(yymmdd) < 6:
        return None
    cleaned = yymmdd.translate(CONFUSION_TO_DIGIT)[:6]
    if not re.fullmatch(r"\d{6}", cleaned):
        return None
    return normalize_date_string(cleaned)


def _parse_td3(line1: str, line2: str) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, bool] = {}

    document_code = line1[0:2].replace("<", "")
    issuing_country = sanitize_mrz_field(line1[2:5], "alpha")
    full_name, surname, given_names = _parse_names(line1[5:44])

    passport_number_raw = line2[0:9]
    passport_number = passport_number_raw.replace("<", "")
    number_check = sanitize_mrz_field(line2[9], "numeric")
    nationality = sanitize_mrz_field(line2[10:13], "alpha")
    dob = sanitize_mrz_field(line2[13:19], "numeric")
    dob_check = sanitize_mrz_field(line2[19], "numeric")
    sex = line2[20].translate(CONFUSION_TO_LETTER)
    expiry = sanitize_mrz_field(line2[21:27], "numeric")
    expiry_check = sanitize_mrz_field(line2[27], "numeric")
    optional = line2[28:42]
    optional_check = line2[42]
    composite_check = sanitize_mrz_field(line2[43], "numeric")

    # 1. Document Number Check
    ok, error = validate_check_digit(passport_number_raw, number_check)
    checks["document_number"] = ok
    if not ok:
        errors.append(f"Passport Number check digit: {error}")

    # 2. Date of Birth Check
    ok, error = validate_check_digit(dob, dob_check)
    checks["date_of_birth"] = ok
    if not ok:
        errors.append(f"Date of Birth check digit: {error}")

    # 3. Expiry Date Check
    ok, error = validate_check_digit(expiry, expiry_check)
    checks["date_of_expiry"] = ok
    if not ok:
        errors.append(f"Date of Expiry check digit: {error}")

    # 4. Optional Data Check (if used and not blank)
    if optional_check != "<" and optional.replace("<", "") != "":
        ok, error = validate_check_digit(optional, optional_check)
        checks["optional_data"] = ok
        if not ok:
            errors.append(f"Optional Data check digit: {error}")
    else:
        checks["optional_data"] = True

    # 5. Composite Check Digit (covers positions 1-10, 14-20, 22-28, 29-43)
    composite_data = (
        passport_number_raw
        + number_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + optional
        + optional_check
    )
    ok, error = validate_check_digit(composite_data, composite_check)
    checks["composite"] = ok
    if not ok:
        errors.append(f"Composite check digit: {error}")

    is_valid = len(errors) == 0
    mrz_status = "MRZ_FOUND_AND_VALID" if is_valid else "MRZ_FOUND_AND_INVALID"

    return {
        "format": "TD3",
        "raw_lines": [line1, line2],
        "mrz_detected": True,
        "mrz_valid": is_valid,
        "status": mrz_status,
        "validation_performed": True,
        "checks": checks,
        "mrz_errors": errors,
        "document_code": _field(line1[0:2], document_code),
        "issuing_country": _field(line1[2:5], issuing_country),
        "surname": _field(surname),
        "given_names": _field(given_names),
        "full_name": _field(full_name),
        "passport_number": _field(passport_number_raw, passport_number),
        "nationality": _field(line2[10:13], nationality),
        "date_of_birth": _field(dob, _format_mrz_date(dob)),
        "sex": _field(sex, None if sex == "<" else sex),
        "date_of_expiry": _field(expiry, _format_mrz_date(expiry)),
        "optional_data": _field(optional, optional.replace("<", "") or None),
    }


def _parse_td2(line1: str, line2: str) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, bool] = {}

    document_code = line1[0:2].replace("<", "")
    issuing_country = sanitize_mrz_field(line1[2:5], "alpha")
    full_name, surname, given_names = _parse_names(line1[5:36])

    doc_number_raw = line2[0:9]
    doc_number = doc_number_raw.replace("<", "")
    number_check = sanitize_mrz_field(line2[9], "numeric")
    nationality = sanitize_mrz_field(line2[10:13], "alpha")
    dob = sanitize_mrz_field(line2[13:19], "numeric")
    dob_check = sanitize_mrz_field(line2[19], "numeric")
    sex = line2[20].translate(CONFUSION_TO_LETTER)
    expiry = sanitize_mrz_field(line2[21:27], "numeric")
    expiry_check = sanitize_mrz_field(line2[27], "numeric")
    optional = line2[28:35]
    composite_check = sanitize_mrz_field(line2[35], "numeric")

    # Document Number Check
    ok, error = validate_check_digit(doc_number_raw, number_check)
    checks["document_number"] = ok
    if not ok:
        errors.append(f"Document Number check digit: {error}")

    # DOB Check
    ok, error = validate_check_digit(dob, dob_check)
    checks["date_of_birth"] = ok
    if not ok:
        errors.append(f"Date of Birth check digit: {error}")

    # Expiry Check
    ok, error = validate_check_digit(expiry, expiry_check)
    checks["date_of_expiry"] = ok
    if not ok:
        errors.append(f"Date of Expiry check digit: {error}")

    # Composite Check
    composite_data = doc_number_raw + number_check + dob + dob_check + expiry + expiry_check + optional
    ok, error = validate_check_digit(composite_data, composite_check)
    checks["composite"] = ok
    if not ok:
        errors.append(f"Composite check digit: {error}")

    is_valid = len(errors) == 0
    return {
        "format": "TD2",
        "raw_lines": [line1, line2],
        "mrz_detected": True,
        "mrz_valid": is_valid,
        "status": "MRZ_FOUND_AND_VALID" if is_valid else "MRZ_FOUND_AND_INVALID",
        "validation_performed": True,
        "checks": checks,
        "mrz_errors": errors,
        "document_code": _field(line1[0:2], document_code),
        "issuing_country": _field(line1[2:5], issuing_country),
        "surname": _field(surname),
        "given_names": _field(given_names),
        "full_name": _field(full_name),
        "passport_number": _field(doc_number_raw, doc_number),
        "nationality": _field(line2[10:13], nationality),
        "date_of_birth": _field(dob, _format_mrz_date(dob)),
        "sex": _field(sex, None if sex == "<" else sex),
        "date_of_expiry": _field(expiry, _format_mrz_date(expiry)),
        "optional_data": _field(optional, optional.replace("<", "") or None),
    }


def _parse_td1(line1: str, line2: str, line3: str) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, bool] = {}

    document_code = line1[0:2].replace("<", "")
    issuing_country = sanitize_mrz_field(line1[2:5], "alpha")
    doc_number_raw = line1[5:14]
    doc_number = doc_number_raw.replace("<", "")
    number_check = sanitize_mrz_field(line1[14], "numeric")
    optional1 = line1[15:30]

    dob = sanitize_mrz_field(line2[0:6], "numeric")
    dob_check = sanitize_mrz_field(line2[6], "numeric")
    sex = line2[7].translate(CONFUSION_TO_LETTER)
    expiry = sanitize_mrz_field(line2[8:14], "numeric")
    expiry_check = sanitize_mrz_field(line2[14], "numeric")
    nationality = sanitize_mrz_field(line2[15:18], "alpha")
    optional2 = line2[18:29]
    composite_check = sanitize_mrz_field(line2[29], "numeric")
    full_name, surname, given_names = _parse_names(line3)

    # Document Number Check
    ok, error = validate_check_digit(doc_number_raw, number_check)
    checks["document_number"] = ok
    if not ok:
        errors.append(f"Document Number check digit: {error}")

    # DOB Check
    ok, error = validate_check_digit(dob, dob_check)
    checks["date_of_birth"] = ok
    if not ok:
        errors.append(f"Date of Birth check digit: {error}")

    # Expiry Check
    ok, error = validate_check_digit(expiry, expiry_check)
    checks["date_of_expiry"] = ok
    if not ok:
        errors.append(f"Date of Expiry check digit: {error}")

    # Composite Check
    composite_data = doc_number_raw + number_check + optional1 + dob + dob_check + expiry + expiry_check + optional2
    ok, error = validate_check_digit(composite_data, composite_check)
    checks["composite"] = ok
    if not ok:
        errors.append(f"Composite check digit: {error}")

    is_valid = len(errors) == 0
    return {
        "format": "TD1",
        "raw_lines": [line1, line2, line3],
        "mrz_detected": True,
        "mrz_valid": is_valid,
        "status": "MRZ_FOUND_AND_VALID" if is_valid else "MRZ_FOUND_AND_INVALID",
        "validation_performed": True,
        "checks": checks,
        "mrz_errors": errors,
        "document_code": _field(line1[0:2], document_code),
        "issuing_country": _field(line1[2:5], issuing_country),
        "document_number": _field(doc_number_raw, doc_number),
        "nationality": _field(line2[15:18], nationality),
        "date_of_birth": _field(dob, _format_mrz_date(dob)),
        "sex": _field(sex, None if sex == "<" else sex),
        "date_of_expiry": _field(expiry, _format_mrz_date(expiry)),
        "surname": _field(surname),
        "given_names": _field(given_names),
        "full_name": _field(full_name),
        "optional_data": _field((optional1 + optional2), (optional1 + optional2).replace("<", "") or None),
    }


def empty_mrz_result(reason: str | None = None, status: str = "MRZ_NOT_DETECTED") -> dict[str, Any]:
    errors = [reason] if reason else []
    return {
        "format": None,
        "raw_lines": [],
        "mrz_detected": False,
        "mrz_valid": False,
        "status": status,
        "validation_performed": False,
        "checks": {},
        "mrz_errors": errors,
        "document_code": None,
        "issuing_country": None,
        "surname": None,
        "given_names": None,
        "full_name": None,
        "passport_number": None,
        "document_number": None,
        "nationality": None,
        "date_of_birth": None,
        "sex": None,
        "date_of_expiry": None,
        "optional_data": None,
    }


def extract_mrz(raw_text: str, regions: list[dict[str, Any]]) -> dict[str, Any]:
    lines, collapsed = _candidate_lines(raw_text, regions)
    td3 = _find_td3(lines, collapsed)
    if td3:
        return _parse_td3(*td3)

    td1 = _find_td1(lines, collapsed)
    if td1:
        return _parse_td1(*td1)

    td2 = _find_td2(lines, collapsed)
    if td2:
        return _parse_td2(*td2)

    # Check for incomplete / malformed MRZ fragments
    all_source_lines = [mrz_sanitize_line(line) for line in raw_text.splitlines()] + lines
    almost = [
        line
        for line in all_source_lines
        if (re.search(r"[PIACV]<[A-Z]{3}", line) and len(line) >= 10)
        or (line.startswith("P<") and len(line) >= 8)
        or ("<<" in line and len(line) >= 15)
    ]
    if almost:
        return empty_mrz_result(
            "MRZ-like text found but it does not match a complete ICAO line specification.",
            status="MRZ_UNREADABLE",
        )
    return empty_mrz_result(status="MRZ_NOT_DETECTED")

