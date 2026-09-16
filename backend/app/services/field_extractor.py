"""Structured field extraction from OCR text and MRZ. Missing values are never invented."""

from __future__ import annotations

import re
from typing import Any

from app.services.ocr_normalize import (
    clean_nationality,
    interpret_document_number,
    normalize_date_string,
    normalize_name,
    split_person_name,
    strip_non_alnum,
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
        "place_of_issue",
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
    "surname": [r"surname", r"family\s*name", r"last\s*name", r"nom\b", r"उपनाम", r"nachname", r"apellidos?"],
    # Keep the optional "(s)" inside the label match. A shorter `names?`
    # alternative used to match only "GivenName" and leak "(s)" as its value.
    "given_names": [r"given\s*names?(?:\s*\(s\))?", r"first\s*names?", r"forenames?", r"prenom", r"pr[eé]noms?", r"दिया\s*गया\s*नाम", r"vorname", r"nombres?"],
    "full_name": [r"full\s*name", r"\bname\b", r"name\s*of\s*bearer", r"nom\s*et\s*pr[eé]noms?", r"\bनाम\b", r"vollst[aä]ndiger\s*name"],
    "passport_number": [r"passport\s*(?:no|number|num|id|\#|nr)\.?", r"pass(?:port)?\s*[-_]?\s*(?:no|number|num|nr)\.?", r"document\s*(?:no|number|num|\#)\.?", r"doc\s*no\.?", r"पासपोर्ट\s*सं(?:ख्या)?\.?"],
    "nationality": [r"nationality", r"nationalit[eé]", r"citizenship", r"staatsangeh[oö]rigkeit", r"राष्ट्रीयता", r"nacionalidad"],
    "date_of_birth": [r"date\s*of\s*birth", r"birth\s*date", r"\bdob\b", r"d\.o\.b", r"date\s*de\s*naissance", r"geburtsdatum", r"जन्म\s*तिथि", r"fecha\s*de\s*nacimiento"],
    "gender": [r"\bsex\b", r"\bgender\b", r"\bsexe\b", r"geschlecht", r"\bलिंग\b", r"\bsexo\b"],
    "place_of_birth": [r"place\s*of\s*birth", r"birth\s*place", r"lieu\s*de\s*naissance", r"geburtsort", r"जन्म\s*स्थान", r"lugar\s*de\s*nacimiento"],
    # The constrained variants cover common OCR confusion of capital I with
    # lowercase l/1, plus collapsed "Place of Issue" such as "Pacssue".
    "place_of_issue": [r"place\s*of\s*[iIl1]?ssue", r"p(?:lace|ac)e?\s*(?:of\s*)?[iIl1]?ssue", r"lieu\s*de\s*d[eé]livrance", r"ausstellungsort", r"जारी\s*करने\s*का\s*स्थान", r"lugar\s*de\s*expedici[oó]n"],
    "date_of_issue": [r"date\s*of\s*[iIl1]?ssue", r"date\s*of\s*issuance", r"[iIl1]?ssue\s*date", r"[iIl1]?ssued\s*on", r"date\s*de\s*d[eé]livrance", r"ausstellungsdatum", r"जारी\s*करने\s*की\s*तिथि", r"fecha\s*de\s*expedici[oó]n"],
    "date_of_expiry": [
        r"date\s*of\s*expiry",
        r"date\s*of\s*expiration",
        r"expiry\s*date",
        r"expiration\s*date",
        r"valid\s*until",
        r"valid\s*to",
        r"date\s*d['’]expiration",
        r"g[uü]ltig\s*bis",
        r"समाप्ति\s*की\s*तिथि",
        r"fecha\s*de\s*caducidad",
    ],
    "issuing_country": [r"issuing\s*country", r"issuing\s*state", r"code\s*of\s*issuing", r"country\s*code", r"pays\s*[eé]metteur", r"ausstellender\s*staat", r"देश\s*का\s*कोड"],
    "visa_number": [r"visa no\.?", r"visa number", r"control number"],
    "visa_type": [r"visa type", r"class", r"category", r"type of visa"],
    "entries": [r"entries", r"number of entries"],
    "stay_duration": [r"duration of stay", r"period of stay", r"length of stay"],
    "entry_validation": [r"valid for", r"annotation", r"entry validation"],
    "id_number": [r"id(?:entity)? (?:no|number|card no)", r"national id", r"nin", r"nic", r"aadhaar", r"pan no"],
    "issuing_authority": [r"issuing authority", r"authority", r"issued by", r"autorit[eé]"],
    "licence_number": [r"licen[cs]e no\.?", r"licen[cs]e number", r"dl number", r"driver(?:'s)? no"],
    "category": [r"categor(?:y|ies)", r"class(?:es)?", r"vehicle class"],
    "permit_number": [r"permit no\.?", r"permit number", r"authorization no"],
    "permit_type": [r"permit type", r"type of permit", r"authorization type"],
    "restrictions": [r"restrictions?", r"conditions?"],
    "issue_date": [r"issue date", r"date of issue", r"valid from"],
    "expiry_date": [r"expiry date", r"expiration", r"valid until", r"valid to"],
}

PASSPORT_NO_RE = re.compile(r"\b([A-Z][0-9]{7,8})\b|\b([A-Z][A-Z0-9]{6,8})\b")
GENDER_RE = re.compile(r"\b(M|F|X|MALE|FEMALE|HOMME|FEMME)\b", re.I)


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


def _bounds(region: dict[str, Any]) -> tuple[float, float, float, float]:
    box = region.get("box") or [[0.0, 0.0]]
    xs = [float(point[0]) for point in box]
    ys = [float(point[1]) for point in box]
    return min(xs), min(ys), max(xs), max(ys)


def _group_lines(regions: list[dict[str, Any]]) -> list[str]:
    if not regions:
        return []

    # Estimate adaptive threshold from median box height
    heights: list[float] = []
    for item in regions:
        box = item.get("box") or []
        if len(box) >= 4:
            ys = [p[1] for p in box]
            h = max(ys) - min(ys)
            if h > 0:
                heights.append(h)
    median_h = sorted(heights)[len(heights) // 2] if heights else 20.0
    threshold_y = max(14.0, median_h * 0.6)

    sorted_regions = sorted(
        regions,
        key=lambda item: (
            min((p[1] for p in item.get("box") or [[0.0, 0.0]]), default=0.0),
            min((p[0] for p in item.get("box") or [[0.0, 0.0]]), default=0.0),
        ),
    )
    lines: list[list[tuple[float, str]]] = []
    current_y = None
    current: list[tuple[float, str]] = []
    for region in sorted_regions:
        x, y, _x2, _y2 = _bounds(region)
        if current_y is None or abs(y - current_y) <= threshold_y:
            current.append((x, region["text"]))
            current_y = y if current_y is None else (current_y + y) / 2
        else:
            lines.append(current)
            current = [(x, region["text"])]
            current_y = y
    if current:
        lines.append(current)
    return [" ".join(text for _x, text in sorted(parts, key=lambda item: item[0])) for parts in lines]


def _extract_by_layout(regions: list[dict[str, Any]]) -> dict[str, str]:
    """Associate labels with the nearest value below them in the same column.

    This is deliberately conservative: candidates must be close, horizontally
    aligned, non-label text, and not an MRZ line. It prevents adjacent columns
    (or the holder-signature area) from being consumed as field values.
    """
    usable = [region for region in regions if str(region.get("text", "")).strip()]
    if not usable:
        return {}
    compiled = {key: re.compile(rf"(?:{'|'.join(patterns)})", re.I) for key, patterns in LABELS.items()}
    found: dict[str, str] = {}

    for label_region in usable:
        label_text = str(label_region["text"])
        lx1, ly1, lx2, ly2 = _bounds(label_region)
        label_height = max(ly2 - ly1, 1.0)
        matching_keys = [key for key, pattern in compiled.items() if pattern.search(label_text)]
        aliases = {"issue_date": "date_of_issue", "expiry_date": "date_of_expiry"}
        if len({aliases.get(key, key) for key in matching_keys}) > 1:
            # A single OCR box containing several column headings has no
            # per-label X coordinate. The ordered line parser handles it.
            continue
        for key, pattern in compiled.items():
            if key in found or key not in matching_keys:
                continue
            inline = _value_after_label(label_text, pattern, compiled)
            # Bilingual/multi-column headers often have more labels after the
            # first match; none of that header text is a value.
            inline_has_label = inline and any(other.search(inline) for other in compiled.values())
            if inline and not inline_has_label and inline.lower() != "(s)":
                found[key] = inline
                continue

            candidates: list[tuple[float, float, str]] = []
            for candidate in usable:
                if candidate is label_region:
                    continue
                text = str(candidate["text"]).strip()
                if not text or text.startswith(("P<", "V<", "I<")):
                    continue
                if any(other.search(text) for other in compiled.values()):
                    continue
                cx1, cy1, cx2, _cy2 = _bounds(candidate)
                vertical_gap = cy1 - ly2
                if vertical_gap < -4 or vertical_gap > max(90.0, label_height * 3.2):
                    continue
                overlap = max(0.0, min(lx2, cx2) - max(lx1, cx1))
                if overlap < min(lx2 - lx1, cx2 - cx1) * 0.2:
                    continue
                candidates.append((vertical_gap, abs(cx1 - lx1), text))
            if candidates:
                candidates.sort(key=lambda item: (item[0], item[1]))
                found[key] = candidates[0][2]
    return found


def _value_after_label(line: str, label_re: re.Pattern[str], compiled: dict[str, re.Pattern[str]] | None = None) -> str | None:
    match = label_re.search(line)
    if not match:
        return None
    rest = line[match.end() :].strip(" :.-/")
    if not rest:
        return None
    # If rest is just another label (e.g. bilingual header like / Nom or / Prénoms), return None
    if compiled:
        for other_pat in compiled.values():
            if other_pat.search(rest):
                # If the entire rest is just the other label
                other_m = other_pat.search(rest)
                if other_m and not rest[other_m.end():].strip(" :.-/"):
                    return None
    return rest or None


def _extract_by_labels(lines: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    compiled = {
        key: re.compile(rf"(?:{'|'.join(patterns)})", re.I) for key, patterns in LABELS.items()
    }

    # 1. Multi-column header & adjacent row parsing
    for index, line in enumerate(lines):
        # Find all matching labels on this line with their positions
        matched_labels: list[tuple[str, int, int]] = []
        for key, pattern in compiled.items():
            for m in pattern.finditer(line):
                matched_labels.append((key, m.start(), m.end()))
        matched_labels.sort(key=lambda item: item[1])

        # If multiple labels found on the same header line
        if len(matched_labels) > 1 and index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            # Check if next line contains dates
            dates_in_next = re.findall(r"\b\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}\b", next_line)
            label_keys = [item[0] for item in matched_labels]

            # Case: Date of Issue + Date of Expiry
            if "date_of_issue" in label_keys and "date_of_expiry" in label_keys:
                if len(dates_in_next) >= 2:
                    if "date_of_issue" not in found:
                        found["date_of_issue"] = dates_in_next[0]
                    if "date_of_expiry" not in found:
                        found["date_of_expiry"] = dates_in_next[1]
                elif len(dates_in_next) == 1:
                    if "date_of_issue" not in found:
                        found["date_of_issue"] = dates_in_next[0]

            # Case: Nationality + Sex + Date of Birth
            if "nationality" in label_keys or "gender" in label_keys or "date_of_birth" in label_keys:
                if dates_in_next and "date_of_birth" not in found:
                    found["date_of_birth"] = dates_in_next[0]
                sex_match = GENDER_RE.search(next_line)
                if sex_match and "gender" not in found:
                    found["gender"] = sex_match.group(1)
                nat_val = clean_nationality(next_line)
                if nat_val and "nationality" not in found:
                    found["nationality"] = nat_val

            # Case: Type + Country Code + Passport No
            if "passport_number" in label_keys or "issuing_country" in label_keys:
                p_match = PASSPORT_NO_RE.search(next_line)
                if p_match and "passport_number" not in found:
                    found["passport_number"] = p_match.group(1) or p_match.group(2)
                # 3-letter country code
                cc_match = re.search(r"\b([A-Z]{3})\b", next_line)
                if cc_match and "issuing_country" not in found:
                    found["issuing_country"] = cc_match.group(1)

        # Standard inline or next-line label matching
        for key, pattern in compiled.items():
            if key in found:
                continue
            value = _value_after_label(line, pattern, compiled)
            if value:
                found[key] = value
                continue
            if pattern.search(line) and index + 1 < len(lines):
                next_line = lines[index + 1].strip()
                if next_line and not any(other.search(next_line) for other in compiled.values()):
                    found[key] = next_line

    return found


def _normalize_date(raw: str) -> str | None:
    return normalize_date_string(raw)


def _normalize_gender(raw: str) -> str | None:
    match = GENDER_RE.search(raw)
    if not match:
        return None
    token = match.group(1).upper()
    if token in {"M", "MALE", "HOMME"}:
        return "M"
    if token in {"F", "FEMALE", "FEMME"}:
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
        norm = normalizer(raw)
        if norm:
            return _detected(raw, norm)

    if mrz and key in mrz_keys:
        mapped = _from_mrz_field(mrz, mrz_keys[key])
        if mapped:
            normalized = normalizer(mapped[1])
            if normalized:
                return _detected(mapped[0], normalized)

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
    # Spatial associations are stronger than flattened line order where OCR
    # detects several passport columns at nearly the same Y coordinate.
    labeled.update(_extract_by_layout(regions))
    required = set(REQUIRED_FIELDS.get(document_type, []))
    optional = set(OPTIONAL_FIELDS.get(document_type, []))
    not_applicable = set(NOT_APPLICABLE.get(document_type, []))

    if document_type == "passport":
        return _extract_passport(labeled, mrz, required, optional, not_applicable, raw_text, lines)
    if document_type == "visa":
        return _extract_visa(labeled, required, optional, not_applicable)
    if document_type == "national_id":
        return _extract_national_id(labeled, mrz, required, optional, not_applicable)
    if document_type == "driving_license":
        return _extract_licence(labeled, required, optional, not_applicable)
    return _extract_permit(labeled, required, optional, not_applicable)


def _name_from_sources(labeled: dict[str, str], mrz: dict[str, Any] | None) -> dict[str, Any]:
    raw_name = labeled.get("full_name")
    surname = labeled.get("surname")
    given = labeled.get("given_names")

    # If MRZ parsed names are available, use as authoritative cross-check/fallback
    if mrz:
        if not surname and mrz.get("surname") and mrz["surname"].get("raw"):
            surname = mrz["surname"].get("normalized") or mrz["surname"].get("raw")
        if not given and mrz.get("given_names") and mrz["given_names"].get("raw"):
            given = mrz["given_names"].get("normalized") or mrz["given_names"].get("raw")
        if not raw_name and mrz.get("full_name") and mrz["full_name"].get("raw"):
            raw_name = mrz["full_name"].get("normalized") or mrz["full_name"].get("raw")

    if surname and given:
        parsed = {
            "full_name": f"{given} {surname}".strip(),
            "surname": surname,
            "given_names": given,
        }
        source = f"{given} {surname}".strip()
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
        "sources": {
            "full_name": source,
            "surname": surname or source,
            "given_names": given or source,
        },
    }


def _extract_passport(
    labeled: dict[str, str],
    mrz: dict[str, Any] | None,
    required: set[str],
    optional: set[str],
    not_applicable: set[str],
    raw_text: str = "",
    lines: list[str] | None = None,
) -> dict[str, Any]:
    names = _name_from_sources(labeled, mrz)
    fields: dict[str, Any] = {}

    def name_field(key: str) -> dict[str, str | None]:
        value = names.get(key)
        if value:
            raw_source = (names.get("sources") or {}).get(key) or names.get("source") or value
            return _detected(raw_source, normalize_name(value))
        if key in required:
            return _missing("REQUIRED_MISSING")
        return _missing("OPTIONAL_MISSING")

    fields["full_name"] = name_field("full_name")
    fields["surname"] = name_field("surname")
    fields["given_names"] = name_field("given_names")

    # 1. Passport Number Extraction & Fallback
    number_raw = labeled.get("passport_number")
    if number_raw:
        cand_clean = strip_non_alnum(number_raw).upper()
        if not (any(c.isdigit() for c in cand_clean) and 6 <= len(cand_clean) <= 12):
            number_raw = None

    if not number_raw and mrz and mrz.get("passport_number") and mrz["passport_number"].get("raw"):
        number_raw = mrz["passport_number"]["raw"]

    if not number_raw and raw_text:
        # Search unmapped text for strong passport number candidates (e.g. U1234567)
        ignored_words = {"PASSPORT", "REPUBLIC", "INDIAN", "NATIONALITY", "GOVERNMENT", "DETAILS", "SIGNATURE", "EXPIRY", "ISSUED"}
        candidates = PASSPORT_NO_RE.findall(raw_text)
        for cand_tuple in candidates:
            cand = cand_tuple[0] or cand_tuple[1]
            cand_clean = strip_non_alnum(cand).upper()
            if (
                cand_clean not in ignored_words
                and any(c.isdigit() for c in cand_clean)
                and cand_clean[0].isalpha()
                and 7 <= len(cand_clean) <= 9
            ):
                number_raw = cand_clean
                break

    if number_raw:
        fields["passport_number"] = _detected(number_raw, interpret_document_number(number_raw))
    else:
        fields["passport_number"] = _missing("REQUIRED_MISSING")

    # 2. Nationality Normalization (prevent date pollution)
    nat_raw = labeled.get("nationality")
    cleaned_nat = clean_nationality(nat_raw)
    if not cleaned_nat and mrz and mrz.get("nationality") and mrz["nationality"].get("raw"):
        mrz_nat_raw = mrz["nationality"]["raw"]
        cleaned_nat = clean_nationality(mrz_nat_raw) or mrz_nat_raw
        if not nat_raw:
            nat_raw = mrz_nat_raw

    if cleaned_nat:
        fields["nationality"] = _detected(nat_raw or cleaned_nat, cleaned_nat)
    else:
        fields["nationality"] = _missing("OPTIONAL_MISSING")

    # 3. Dates Extraction & Chronological Disambiguation
    dob_raw = labeled.get("date_of_birth")
    dob_norm = _normalize_date(dob_raw) if dob_raw else None
    if not dob_norm and mrz and mrz.get("date_of_birth") and mrz["date_of_birth"].get("normalized"):
        dob_norm = mrz["date_of_birth"]["normalized"]
        if not dob_raw:
            dob_raw = mrz["date_of_birth"].get("raw")

    fields["date_of_birth"] = _detected(dob_raw, dob_norm) if dob_norm else _missing("OPTIONAL_MISSING")

    doi_raw = labeled.get("date_of_issue")
    doi_norm = _normalize_date(doi_raw) if doi_raw else None

    doe_raw = labeled.get("date_of_expiry")
    doe_norm = _normalize_date(doe_raw) if doe_raw else None
    if not doe_norm and mrz and mrz.get("date_of_expiry") and mrz["date_of_expiry"].get("normalized"):
        doe_norm = mrz["date_of_expiry"]["normalized"]
        if not doe_raw:
            doe_raw = mrz["date_of_expiry"].get("raw")

    # Disambiguate issue date and expiry date if swapped
    if doi_norm and doe_norm and doi_norm > doe_norm:
        doi_raw, doe_raw = doe_raw, doi_raw
        doi_norm, doe_norm = doe_norm, doi_norm

    fields["date_of_issue"] = _detected(doi_raw, doi_norm) if doi_norm else _missing("OPTIONAL_MISSING")
    fields["date_of_expiry"] = _detected(doe_raw, doe_norm) if doe_norm else _missing("REQUIRED_MISSING")

    # 4. Gender, Place of Birth, Place of Issue, Issuing Country
    def simple(key: str, mrz_key: str | None, normalizer) -> dict[str, str | None]:
        mapping = {key: mrz_key} if mrz_key else {}
        return _fill(key, labeled, mrz, mapping, required, optional, not_applicable, normalizer)

    fields["gender"] = simple("gender", "sex", _normalize_gender)
    fields["issuing_country"] = simple("issuing_country", "issuing_country", lambda v: uppercase_compact(v)[:3] if v else None)
    fields["place_of_birth"] = simple("place_of_birth", None, normalize_name)
    fields["place_of_issue"] = simple("place_of_issue", None, normalize_name)
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

