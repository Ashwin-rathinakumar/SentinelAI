"""Structured field extraction from OCR text. Missing values are never invented."""

from __future__ import annotations

import re
from typing import Any

from app.services.ocr_normalize import (
    interpret_document_number,
    normalize_name,
    split_person_name,
    uppercase_compact,
)

REQUIRED_FIELDS = {
    "passport": ["full_name", "passport_number", "date_of_expiry"],
    "visa": ["name", "visa_number"],
    "national_id": ["name", "id_number"],
    "driving_license": ["name", "licence_number"],
    "permit": ["name"],
}

OPTIONAL_FIELDS = {
    "passport": [
        "surname",
        "given_names",
        "nationality",
        "date_of_birth",
        "gender",
        "date_of_issue",
        "issuing_country",
        "place_of_birth",
        "mrz",
    ],
    "visa": [
        "visa_type",
        "passport_number",
        "nationality",
        "date_of_birth",
        "issue_date",
        "expiry_date",
        "entries",
        "stay_duration",
        "entry_validation",
    ],
    "national_id": [
        "date_of_birth",
        "gender",
        "nationality",
        "issue_date",
        "expiry_date",
        "issuing_authority",
    ],
    "driving_license": [
        "date_of_birth",
        "issue_date",
        "expiry_date",
        "category",
        "issuing_authority",
    ],
    "permit": [
        "permit_number",
        "permit_type",
        "nationality",
        "date_of_birth",
        "issue_date",
        "expiry_date",
        "issuing_authority",
        "restrictions",
    ],
}

NOT_APPLICABLE = {
    "visa": ["place_of_birth", "mrz"],
    "national_id": ["passport_number", "mrz", "place_of_birth"],
    "driving_license": ["passport_number", "mrz", "nationality"],
    "permit": ["passport_number", "mrz"],
}

LABELS: dict[str, list[str]] = {
    "surname": [r"surname", r"family name", r"last name", r"nom\b"],
    "given_names": [r"given names?", r"first names?", r"forenames?", r"prenom", r"pr[eé]noms?"],
    "full_name": [r"full name", r"name of bearer", r"name\b"],
    "passport_number": [r"passport no\.?", r"passport number", r"document no\.?", r"doc(?:ument)? no\.?"],
    "nationality": [r"nationality", r"nationalit[eé]", r"citizenship"],
    "date_of_birth": [r"date of birth", r"birth date", r"dob", r"date de naissance"],
    "gender": [r"\bsex\b", r"gender", r"sexe"],
    "date_of_issue": [r"date of issue", r"date of issuance", r"issued on", r"issue date"],
    "date_of_expiry": [
        r"date of expiry",
        r"date of expiration",
        r"expiry date",
        r"expiration date",
        r"valid until",
        r"date d['’]expiration",
    ],
    "issuing_country": [r"issuing country", r"issuing state", r"code of issuing"],
    "place_of_birth": [r"place of birth", r"lieu de naissance"],
    "visa_number": [r"visa no\.?", r"visa number", r"control number"],
    "visa_type": [r"visa type", r"class", r"category", r"type of visa"],
    "entries": [r"entries", r"number of entries"],
    "stay_duration": [r"duration of stay", r"period of stay", r"length of stay"],
    "entry_validation": [r"valid for", r"annotation", r"entry validation"],
    "id_number": [r"id(?:entity)? (?:no|number|card no)", r"national id", r"nin", r"nic"],
    "issuing_authority": [r"issuing authority", r"authority", r"issued by"],
    "licence_number": [r"licen[cs]e no\.?", r"licen[cs]e number", r"dl number", r"driver(?:'s)? no"],
    "category": [r"categor(?:y|ies)", r"class(?:es)?", r"vehicle class"],
    "permit_number": [r"permit no\.?", r"permit number", r"authorization no"],
    "permit_type": [r"permit type", r"type of permit", r"authorization type"],
    "restrictions": [r"restrictions?", r"conditions?"],
    "issue_date": [r"issue date", r"date of issue", r"valid from"],
    "expiry_date": [r"expiry date", r"expiration", r"valid until", r"valid to"],
}

DATE_RE = re.compile(
    r"\b(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b"
)
PASSPORT_NO_RE = re.compile(r"\b([A-Z][A-Z0-9<]{5,8}\d)\b")
GENDER_RE = re.compile(r"\b(M|F|X|MALE|FEMALE)\b", re.I)


def _field(
    raw: str | None,
    normalized: str | None,
    status: str,
) -> dict[str, str | None]:
    return {"raw": raw, "normalized": normalized, "status": status}


def _detected(raw: str, normalized: str | None = None) -> dict[str, str | None]:
    return _field(raw, normalized if normalized is not None else raw, "DETECTED")


def _missing(kind: str) -> dict[str, str | None]:
    return _field(None, None, kind)


def _group_lines(regions: list[dict[str, Any]]) -> list[str]:
    if not regions:
        return []
    sorted_regions = sorted(
        regions,
        key=lambda item: (
            min((p[1] for p in item.get("box") or [[0.0, 0.0]]), default=0.0),
            min((p[0] for p in item.get("box") or [[0.0, 0.0]]), default=0.0),
        ),
    )
    lines: list[list[str]] = []
    current_y = None
    current: list[str] = []
    for region in sorted_regions:
        y = min((p[1] for p in region.get("box") or [[0.0, 0.0]]), default=0.0)
        if current_y is None or abs(y - current_y) <= 14:
            current.append(region["text"])
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            lines.append(current)
            current = [region["text"]]
            current_y = y
    if current:
        lines.append(current)
    return [" ".join(parts) for parts in lines]


def _value_after_label(line: str, label_re: re.Pattern[str]) -> str | None:
    match = label_re.search(line)
    if not match:
        return None
    rest = line[match.end() :].strip(" :.-")
    return rest or None


def _extract_by_labels(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    compiled = {
        key: re.compile(rf"(?:{'|'.join(patterns)})", re.I) for key, patterns in LABELS.items()
    }
    for index, line in enumerate(lines):
        for key, pattern in compiled.items():
            if key in found:
                continue
            value = _value_after_label(line, pattern)
            if value:
                found[key] = value
                continue
            if pattern.search(line) and index + 1 < len(lines):
                next_line = lines[index + 1].strip()
                if next_line and not any(other.search(next_line) for other in compiled.values()):
                    found[key] = next_line
    return found


def _normalize_date(raw: str) -> str | None:
    match = DATE_RE.search(raw)
    if not match:
        return None
    return match.group(1)


def _normalize_gender(raw: str) -> str | None:
    match = GENDER_RE.search(raw)
    if not match:
        return None
    token = match.group(1).upper()
    if token in {"M", "MALE"}:
        return "M"
    if token in {"F", "FEMALE"}:
        return "F"
    return "X"


def _from_mrz_field(mrz: dict[str, Any], key: str) -> tuple[str, str] | None:
    item = mrz.get(key)
    if not item or not item.get("raw"):
        return None
    raw = str(item["raw"])
    normalized = item.get("normalized")
    return raw, normalized if normalized is not None else raw


def _fill(
    key: str,
    labeled: dict[str, str],
    mrz: dict[str, Any] | None,
    mrz_keys: dict[str, str],
    required: set[str],
    optional: set[str],
    not_applicable: set[str],
    normalizer,
) -> dict[str, str | None]:
    if key in not_applicable:
        return _missing("NOT_APPLICABLE")

    if key in labeled:
        raw = labeled[key]
        return _detected(raw, normalizer(raw))

    if mrz and key in mrz_keys:
        mapped = _from_mrz_field(mrz, mrz_keys[key])
        if mapped:
            return _detected(mapped[0], mapped[1])

    if key in required:
        return _missing("REQUIRED_MISSING")
    if key in optional:
        return _missing("OPTIONAL_MISSING")
    return _missing("NOT_DETECTED")


def extract_fields(
    document_type: str,
    raw_text: str,
    regions: list[dict[str, Any]],
    mrz: dict[str, Any] | None,
) -> dict[str, Any]:
    lines = _group_lines(regions)
    if not lines and raw_text.strip():
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]

    labeled = _extract_by_labels(lines)
    required = set(REQUIRED_FIELDS.get(document_type, []))
    optional = set(OPTIONAL_FIELDS.get(document_type, []))
    not_applicable = set(NOT_APPLICABLE.get(document_type, []))

    if document_type == "passport":
        return _extract_passport(labeled, mrz, required, optional, not_applicable)
    if document_type == "visa":
        return _extract_visa(labeled, required, optional, not_applicable)
    if document_type == "national_id":
        return _extract_national_id(labeled, mrz, required, optional, not_applicable)
    if document_type == "driving_license":
        return _extract_licence(labeled, required, optional, not_applicable)
    return _extract_permit(labeled, required, optional, not_applicable)


def _name_from_sources(labeled: dict[str, str], mrz: dict[str, Any] | None) -> dict[str, Any]:
    raw_name = labeled.get("full_name") or labeled.get("given_names")
    surname = labeled.get("surname")
    given = labeled.get("given_names")

    if mrz:
        if not surname and mrz.get("surname") and mrz["surname"].get("raw"):
            surname = mrz["surname"]["normalized"] or mrz["surname"]["raw"]
        if not given and mrz.get("given_names") and mrz["given_names"].get("raw"):
            given = mrz["given_names"]["normalized"] or mrz["given_names"]["raw"]
        if not raw_name and mrz.get("full_name") and mrz["full_name"].get("raw"):
            raw_name = mrz["full_name"]["normalized"] or mrz["full_name"]["raw"]

    if surname and given:
        parsed = {
            "full_name": f"{given} {surname}".strip(),
            "surname": surname,
            "given_names": given,
        }
        source = f"{surname} {given}"
    elif raw_name:
        parsed = split_person_name(raw_name)
        source = raw_name
    elif surname:
        parsed = {"full_name": surname, "surname": surname, "given_names": None}
        source = surname
    else:
        return {
            "full_name": None,
            "surname": None,
            "given_names": None,
            "source": None,
        }

    return {
        "full_name": parsed.get("full_name"),
        "surname": parsed.get("surname"),
        "given_names": parsed.get("given_names"),
        "source": source,
    }


def _extract_passport(labeled, mrz, required, optional, not_applicable) -> dict[str, Any]:
    names = _name_from_sources(labeled, mrz)
    fields: dict[str, Any] = {}

    def name_field(key: str) -> dict[str, str | None]:
        value = names.get(key)
        if value:
            return _detected(names["source"] or value, normalize_name(value))
        if key in required:
            return _missing("REQUIRED_MISSING")
        return _missing("OPTIONAL_MISSING")

    fields["full_name"] = name_field("full_name")
    fields["surname"] = name_field("surname")
    fields["given_names"] = name_field("given_names")

    number_raw = labeled.get("passport_number")
    if not number_raw and mrz and mrz.get("passport_number") and mrz["passport_number"].get("raw"):
        number_raw = mrz["passport_number"]["raw"]
    if number_raw:
        fields["passport_number"] = _detected(number_raw, interpret_document_number(number_raw))
    else:
        guess = PASSPORT_NO_RE.search(" ".join(labeled.values()))
        fields["passport_number"] = (
            _detected(guess.group(1), interpret_document_number(guess.group(1)))
            if guess
            else _missing("REQUIRED_MISSING")
        )

    def simple(key: str, mrz_key: str | None, normalizer) -> dict[str, str | None]:
        mapping = {key: mrz_key} if mrz_key else {}
        return _fill(key, labeled, mrz, mapping, required, optional, not_applicable, normalizer)

    fields["nationality"] = simple("nationality", "nationality", lambda v: uppercase_compact(v)[:3] if len(uppercase_compact(v)) >= 3 else normalize_name(v).upper())
    fields["date_of_birth"] = simple("date_of_birth", "date_of_birth", _normalize_date)
    fields["gender"] = simple("gender", "sex", _normalize_gender)
    fields["date_of_issue"] = simple("date_of_issue", None, _normalize_date)
    fields["date_of_expiry"] = simple("date_of_expiry", "date_of_expiry", _normalize_date)
    fields["issuing_country"] = simple("issuing_country", "issuing_country", lambda v: uppercase_compact(v)[:3] if v else None)
    fields["place_of_birth"] = simple("place_of_birth", None, normalize_name)
    fields["mrz"] = (
        _detected("\n".join(mrz.get("raw_lines") or []), "\n".join(mrz.get("raw_lines") or []))
        if mrz and mrz.get("mrz_detected")
        else _missing("OPTIONAL_MISSING")
    )
    return fields


def _extract_visa(labeled, required, optional, not_applicable) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    name_raw = labeled.get("full_name") or labeled.get("given_names")
    if name_raw:
        parsed = split_person_name(name_raw)
        fields["name"] = _detected(name_raw, parsed["full_name"])
    else:
        fields["name"] = _missing("REQUIRED_MISSING")

    def grab(key: str, normalizer, alias: str | None = None) -> dict[str, str | None]:
        source_key = alias or key
        mapping_required = {key} if key in required else set()
        labeled_alias = dict(labeled)
        if alias and alias in labeled and key not in labeled:
            labeled_alias[key] = labeled[alias]
        return _fill(key, labeled_alias, None, {}, mapping_required | required, optional, not_applicable, normalizer)

    fields["visa_number"] = grab("visa_number", interpret_document_number)
    fields["visa_type"] = grab("visa_type", lambda v: normalize_name(v).upper())
    fields["passport_number"] = grab("passport_number", interpret_document_number)
    fields["nationality"] = grab("nationality", lambda v: normalize_name(v).upper())
    fields["date_of_birth"] = grab("date_of_birth", _normalize_date)
    fields["issue_date"] = grab("issue_date", _normalize_date, "date_of_issue")
    fields["expiry_date"] = grab("expiry_date", _normalize_date, "date_of_expiry")
    fields["entries"] = grab("entries", normalize_name)
    fields["stay_duration"] = grab("stay_duration", normalize_name)
    fields["entry_validation"] = grab("entry_validation", normalize_name)
    return fields


def _extract_national_id(labeled, mrz, required, optional, not_applicable) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    names = _name_from_sources(labeled, mrz)
    if names["full_name"]:
        fields["name"] = _detected(names["source"] or names["full_name"], names["full_name"])
    else:
        fields["name"] = _missing("REQUIRED_MISSING")

    number = labeled.get("id_number")
    if not number and mrz and mrz.get("document_number"):
        number = mrz["document_number"].get("raw")
    fields["id_number"] = (
        _detected(number, interpret_document_number(number)) if number else _missing("REQUIRED_MISSING")
    )
    fields["date_of_birth"] = _fill("date_of_birth", labeled, mrz, {"date_of_birth": "date_of_birth"}, required, optional, not_applicable, _normalize_date)
    fields["gender"] = _fill("gender", labeled, mrz, {"gender": "sex"}, required, optional, not_applicable, _normalize_gender)
    fields["nationality"] = _fill("nationality", labeled, mrz, {"nationality": "nationality"}, required, optional, not_applicable, lambda v: normalize_name(v).upper())
    fields["issue_date"] = _fill("issue_date", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["expiry_date"] = _fill("expiry_date", labeled, mrz, {"expiry_date": "date_of_expiry"}, required, optional, not_applicable, _normalize_date)
    fields["issuing_authority"] = _fill("issuing_authority", labeled, None, {}, required, optional, not_applicable, normalize_name)
    return fields


def _extract_licence(labeled, required, optional, not_applicable) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    name_raw = labeled.get("full_name") or labeled.get("surname")
    fields["name"] = (
        _detected(name_raw, split_person_name(name_raw)["full_name"]) if name_raw else _missing("REQUIRED_MISSING")
    )
    number = labeled.get("licence_number")
    fields["licence_number"] = (
        _detected(number, interpret_document_number(number)) if number else _missing("REQUIRED_MISSING")
    )
    fields["date_of_birth"] = _fill("date_of_birth", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["issue_date"] = _fill("issue_date", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["expiry_date"] = _fill("expiry_date", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["category"] = _fill("category", labeled, None, {}, required, optional, not_applicable, lambda v: normalize_name(v).upper())
    fields["issuing_authority"] = _fill("issuing_authority", labeled, None, {}, required, optional, not_applicable, normalize_name)
    return fields


def _extract_permit(labeled, required, optional, not_applicable) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    name_raw = labeled.get("full_name")
    fields["name"] = (
        _detected(name_raw, split_person_name(name_raw)["full_name"]) if name_raw else _missing("REQUIRED_MISSING")
    )
    number = labeled.get("permit_number")
    fields["permit_number"] = (
        _detected(number, interpret_document_number(number)) if number else _missing("OPTIONAL_MISSING")
    )
    fields["permit_type"] = _fill("permit_type", labeled, None, {}, required, optional, not_applicable, normalize_name)
    fields["nationality"] = _fill("nationality", labeled, None, {}, required, optional, not_applicable, lambda v: normalize_name(v).upper())
    fields["date_of_birth"] = _fill("date_of_birth", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["issue_date"] = _fill("issue_date", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["expiry_date"] = _fill("expiry_date", labeled, None, {}, required, optional, not_applicable, _normalize_date)
    fields["issuing_authority"] = _fill("issuing_authority", labeled, None, {}, required, optional, not_applicable, normalize_name)
    fields["restrictions"] = _fill("restrictions", labeled, None, {}, required, optional, not_applicable, normalize_name)
    return fields
