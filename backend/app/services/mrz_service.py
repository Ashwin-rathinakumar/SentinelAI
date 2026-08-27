"""ICAO 9303 MRZ detection and check-digit validation."""

from __future__ import annotations

import re
from typing import Any

from app.services.ocr_normalize import mrz_sanitize_line

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
        return False, f"Check digit mismatch (expected {expected})."
    return True, None


def _candidate_lines(raw_text: str, regions: list[dict[str, Any]]) -> tuple[list[str], str]:
    lines: list[str] = []
    for region in sorted(
        regions,
        key=lambda item: (
            min((point[1] for point in item.get("box") or [[0, 0]]), default=0),
            min((point[0] for point in item.get("box") or [[0, 0]]), default=0),
        ),
    ):
        sanitized = mrz_sanitize_line(region["text"])
        if len(sanitized) >= 28:
            lines.append(sanitized)

    for raw_line in raw_text.splitlines():
        sanitized = mrz_sanitize_line(raw_line)
        if len(sanitized) >= 28 and sanitized not in lines:
            lines.append(sanitized)

    collapsed = mrz_sanitize_line(raw_text)
    return lines, collapsed


def _find_td3(lines: list[str], collapsed: str) -> tuple[str, str] | None:
    pattern = re.compile(r"(P[A-Z<][A-Z<]{3}[A-Z<]{39})([A-Z0-9<]{44})")
    for index, line in enumerate(lines[:-1]):
        first = line[:44].ljust(44, "<")[:44]
        second = lines[index + 1][:44].ljust(44, "<")[:44]
        if first.startswith("P") and len(first) == 44 and len(second) == 44:
            return first, second
    match = pattern.search(collapsed)
    if match:
        return match.group(1), match.group(2)
    return None


def _find_td1(lines: list[str], collapsed: str) -> tuple[str, str, str] | None:
    if len(lines) >= 3:
        trio = [line[:30].ljust(30, "<")[:30] for line in lines[-3:]]
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
    surname = parts[0].replace(" ", " ")
    given = parts[1] if len(parts) > 1 else None
    full = " ".join([given, surname]).strip() if given else surname
    return full, surname, given


def _field(raw: str | None, normalized: str | None = None) -> dict[str, str | None]:
    if raw is None:
        return {"raw": None, "normalized": None}
    return {"raw": raw, "normalized": normalized if normalized is not None else raw.replace("<", "")}


def _parse_td3(line1: str, line2: str) -> dict[str, Any]:
    errors: list[str] = []
    validation_performed = True

    document_code = line1[0:2]
    issuing_country = line1[2:5]
    full_name, surname, given_names = _parse_names(line1[5:44])

    passport_number = line2[0:9]
    number_check = line2[9]
    nationality = line2[10:13]
    dob = line2[13:19]
    dob_check = line2[19]
    sex = line2[20]
    expiry = line2[21:27]
    expiry_check = line2[27]
    optional = line2[28:42]
    optional_check = line2[42]
    composite_check = line2[43]

    for data, check, label in (
        (passport_number, number_check, "passport number"),
        (dob, dob_check, "date of birth"),
        (expiry, expiry_check, "expiry date"),
        (optional, optional_check, "optional data"),
    ):
        ok, error = validate_check_digit(data, check)
        if not ok:
            errors.append(f"{label}: {error}")

    composite_data = (
        passport_number
        + number_check
        + dob
        + dob_check
        + expiry
        + expiry_check
        + optional
        + optional_check
    )
    ok, error = validate_check_digit(composite_data, composite_check)
    if not ok:
        errors.append(f"composite: {error}")

    return {
        "format": "TD3",
        "raw_lines": [line1, line2],
        "mrz_detected": True,
        "mrz_valid": len(errors) == 0,
        "validation_performed": validation_performed,
        "mrz_errors": errors,
        "document_code": _field(document_code),
        "issuing_country": _field(issuing_country),
        "surname": _field(surname),
        "given_names": _field(given_names),
        "full_name": _field(full_name),
        "passport_number": _field(passport_number, passport_number.replace("<", "")),
        "nationality": _field(nationality),
        "date_of_birth": _field(dob, _format_mrz_date(dob)),
        "sex": _field(sex, None if sex == "<" else sex),
        "date_of_expiry": _field(expiry, _format_mrz_date(expiry)),
        "optional_data": _field(optional, optional.replace("<", "") or None),
    }


def _parse_td1(line1: str, line2: str, line3: str) -> dict[str, Any]:
    errors: list[str] = []
    document_code = line1[0:2]
    issuing_country = line1[2:5]
    document_number = line1[5:14]
    number_check = line1[14]
    optional1 = line1[15:30]

    dob = line2[0:6]
    dob_check = line2[6]
    sex = line2[7]
    expiry = line2[8:14]
    expiry_check = line2[14]
    nationality = line2[15:18]
    optional2 = line2[18:29]
    composite_check = line2[29]
    full_name, surname, given_names = _parse_names(line3)

    for data, check, label in (
        (document_number, number_check, "document number"),
        (dob, dob_check, "date of birth"),
        (expiry, expiry_check, "expiry date"),
    ):
        ok, error = validate_check_digit(data, check)
        if not ok:
            errors.append(f"{label}: {error}")

    ok, error = validate_check_digit(
        document_number + number_check + optional1 + dob + dob_check + expiry + expiry_check + optional2,
        composite_check,
    )
    if not ok:
        errors.append(f"composite: {error}")

    return {
        "format": "TD1",
        "raw_lines": [line1, line2, line3],
        "mrz_detected": True,
        "mrz_valid": len(errors) == 0,
        "validation_performed": True,
        "mrz_errors": errors,
        "document_code": _field(document_code),
        "issuing_country": _field(issuing_country),
        "document_number": _field(document_number, document_number.replace("<", "")),
        "nationality": _field(nationality),
        "date_of_birth": _field(dob, _format_mrz_date(dob)),
        "sex": _field(sex, None if sex == "<" else sex),
        "date_of_expiry": _field(expiry, _format_mrz_date(expiry)),
        "surname": _field(surname),
        "given_names": _field(given_names),
        "full_name": _field(full_name),
        "optional_data": _field((optional1 + optional2), (optional1 + optional2).replace("<", "") or None),
    }


def _format_mrz_date(yymmdd: str) -> str | None:
    if not re.fullmatch(r"\d{6}", yymmdd):
        return None
    year, month, day = yymmdd[0:2], yymmdd[2:4], yymmdd[4:6]
    return f"{year}-{month}-{day}"


def empty_mrz_result(reason: str | None = None) -> dict[str, Any]:
    errors = [reason] if reason else []
    return {
        "format": None,
        "raw_lines": [],
        "mrz_detected": False,
        "mrz_valid": False,
        "validation_performed": False,
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

    almost = [line for line in lines if len(line) >= 28]
    if almost:
        return empty_mrz_result("MRZ-like text found but it does not match a complete ICAO line set.")
    return empty_mrz_result()
