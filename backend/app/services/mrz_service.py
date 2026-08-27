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


def _candidate_lines(raw_text: str, regions: list[Any]) -> tuple[list[str], str]:
    lines: list[str] = []
    dict_regions = [r for r in regions if isinstance(r, dict)]
    for region in sorted(
        dict_regions,
        key=lambda item: (
            min((point[1] for point in item.get("box") or [[0, 0]]), default=0),
            min((point[0] for point in item.get("box") or [[0, 0]]), default=0),
        ),
    ):
        sanitized = mrz_sanitize_line(str(region.get("text", "")))
        if len(sanitized) >= 28:
            lines.append(sanitized)

    for item in regions:
        if isinstance(item, str):
            sanitized = mrz_sanitize_line(item)
            if len(sanitized) >= 28 and sanitized not in lines:
                lines.append(sanitized)

    for raw_line in raw_text.splitlines():
        sanitized = mrz_sanitize_line(raw_line)
        if len(sanitized) >= 28 and sanitized not in lines:
            lines.append(sanitized)

    collapsed = mrz_sanitize_line(raw_text)
    return lines, collapsed



def _find_td3(lines: list[str], collapsed: str) -> tuple[str, str] | None:
    """TD3 is 2 lines of 44 characters (Passports)."""
    for index, line in enumerate(lines[:-1]):
        first = line[:44].ljust(44, "<")[:44]
        second = lines[index + 1][:44].ljust(44, "<")[:44]
        if first.startswith("P") and len(first) == 44 and len(second) == 44:
            return first, second
    
    # Try finding in collapsed or concatenated stream
    match = re.search(r"(P[A-Z0-9<]{43})([A-Z0-9<]{44})", collapsed)
    if match:
        return match.group(1), match.group(2)
    return None


def _find_td2(lines: list[str], collapsed: str) -> tuple[str, str] | None:
    """TD2 is 2 lines of 36 characters (Visas, official docs)."""
    for index, line in enumerate(lines[:-1]):
        first = line[:36].ljust(36, "<")[:36]
        second = lines[index + 1][:36].ljust(36, "<")[:36]
        if first[0] in {"I", "A", "C", "V", "P"} and len(first) == 36 and len(second) == 36:
            return first, second
    match = re.search(r"([IACVP][A-Z0-9<]{35})([A-Z0-9<]{36})", collapsed)
    if match:
        return match.group(1), match.group(2)
    return None


def _find_td1(lines: list[str], collapsed: str) -> tuple[str, str, str] | None:
    """TD1 is 3 lines of 30 characters (National ID cards)."""
    if len(lines) >= 3:
        for index in range(len(lines) - 2):
            trio = [lines[index + i][:30].ljust(30, "<")[:30] for i in range(3)]
            if all(len(item) == 30 for item in trio) and trio[0][0] in {"I", "A", "C"}:
                return trio[0], trio[1], trio[2]
    match = re.search(r"([IAC][A-Z0-9<]{29})([A-Z0-9<]{30})([A-Z0-9<]{30})", collapsed)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return None


def _parse_names(name_field: str) -> tuple[str | None, str | None, str | None]:
    parts = name_field.replace("<", " ").split("  ")
    parts = [re.sub(r"\s+", " ", part).strip() for part in parts if part.strip()]
    if not parts:
        return None, None, None
    surname = parts[0].strip()
    given = parts[1].strip() if len(parts) > 1 else None
    full = f"{given} {surname}".strip() if given else surname
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

    almost = [line for line in lines if len(line) >= 28]
    if almost:
        return empty_mrz_result(
            "MRZ-like text found but it does not match a complete ICAO line specification.",
            status="MRZ_UNREADABLE",
        )
    return empty_mrz_result(status="MRZ_NOT_DETECTED")

