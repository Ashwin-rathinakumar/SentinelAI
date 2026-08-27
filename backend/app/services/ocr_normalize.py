"""OCR character-confusion helpers and normalization utilities. Raw OCR is never mutated."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Literal

CONFUSION_TO_DIGIT = str.maketrans(
    {
        "O": "0",
        "Q": "0",
        "D": "0",
        "I": "1",
        "L": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
        "G": "6",
    }
)

CONFUSION_TO_LETTER = str.maketrans(
    {
        "0": "O",
        "1": "I",
        "5": "S",
        "8": "B",
        "2": "Z",
        "6": "G",
    }
)

MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4, "JUNE": 6,
    "JULY": 7, "AUGUST": 8, "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


def preserve_raw(value: str | None) -> str | None:
    if value is None:
        return None
    return value


def collapse_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def strip_non_alnum(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value)


def uppercase_compact(value: str) -> str:
    return strip_non_alnum(value).upper()


def normalize_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = unicodedata.normalize("NFKC", raw)
    cleaned = cleaned.replace(" ,", ",").replace(", ", ", ")
    cleaned = collapse_spaces(cleaned)
    return cleaned.strip(" ,")


def split_person_name(raw: str) -> dict[str, str | None]:
    """Support 'JOHN DOE', 'DOE JOHN', 'DOE, JOHN', hyphenated and apostrophe names."""
    text = normalize_name(raw)
    if not text:
        return {"full_name": None, "surname": None, "given_names": None}

    if "," in text:
        left, right = [part.strip() for part in text.split(",", 1)]
        return {
            "full_name": f"{right} {left}".strip(),
            "surname": left or None,
            "given_names": right or None,
        }

    parts = text.split(" ")
    if len(parts) == 1:
        return {"full_name": parts[0], "surname": parts[0], "given_names": None}

    # Default western visual-zone order: given names then surname.
    return {
        "full_name": text,
        "surname": parts[-1],
        "given_names": " ".join(parts[:-1]),
    }


def interpret_document_number(raw: str) -> str:
    """Normalized ID interpretation. Does not change the stored raw OCR string."""
    compact = uppercase_compact(raw)
    if not compact:
        return compact

    chars = list(compact)
    # First character of many travel docs is a letter; remaining often digits.
    if chars and chars[0].isdigit():
        chars[0] = chars[0].translate(CONFUSION_TO_LETTER)
    for index in range(1, len(chars)):
        if chars[index].isalpha() and index > 1:
            continue
        if chars[index].isalpha():
            prev_digit = index > 0 and chars[index - 1].isdigit()
            next_digit = index + 1 < len(chars) and chars[index + 1].isdigit()
            if prev_digit or next_digit:
                chars[index] = chars[index].translate(CONFUSION_TO_DIGIT)
    return "".join(chars)


def mrz_sanitize_line(line: str) -> str:
    """Clean candidate line by removing spaces and standardizing filler characters."""
    if not line:
        return ""
    compact = re.sub(r"\s+", "", line.upper())
    compact = compact.replace("«", "<").replace("(", "<").replace(")", "<").replace("[", "<").replace("]", "<").replace("{", "<").replace("}", "<")
    compact = re.sub(r"[^A-Z0-9<]", "<", compact)
    return compact


def sanitize_mrz_field(raw: str, field_type: Literal["alpha", "numeric", "alphanumeric"]) -> str:
    """Correct OCR character confusion strictly according to ICAO 9303 field specification."""
    if not raw:
        return ""
    if field_type == "alpha":
        return raw.translate(CONFUSION_TO_LETTER).replace("<", "")
    if field_type == "numeric":
        return raw.translate(CONFUSION_TO_DIGIT)
    return raw.replace("<", "")


def normalize_date_string(raw: str | None) -> str | None:
    """Parse various date formats (YYYY-MM-DD, DD/MM/YYYY, DD-MMM-YYYY, YYMMDD) to ISO YYYY-MM-DD."""
    if not raw:
        return None
    raw_clean = collapse_spaces(raw.strip()).upper()

    # 1. ISO format: YYYY-MM-DD or YYYY.MM.DD or YYYY/MM/DD
    match = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", raw_clean)
    if match:
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    # 2. DD-MM-YYYY or DD/MM/YYYY
    match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", raw_clean)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass

    # 3. Textual month e.g. 06 AUG 1969 or 06-AUG-1969 or AUG 06 1969
    for name, month_num in MONTH_MAP.items():
        pattern = rf"\b(\d{1,2})[\s\-/.]{name}[\s\-/.]+(\d{4})\b"
        match = re.search(pattern, raw_clean)
        if match:
            day, year = int(match.group(1)), int(match.group(2))
            try:
                return date(year, month_num, day).isoformat()
            except ValueError:
                pass

    # 4. YYMMDD (6 digits from MRZ)
    digits = strip_non_alnum(raw_clean)
    if len(digits) == 6 and digits.isdigit():
        yy, mm, dd = int(digits[:2]), int(digits[2:4]), int(digits[4:6])
        current_yy = date.today().year % 100
        year = 2000 + yy if yy <= (current_yy + 25) else 1900 + yy
        try:
            return date(year, mm, dd).isoformat()
        except ValueError:
            pass

    return raw_clean


def compare_date_values(date_a: str | None, date_b: str | None) -> bool:
    """Compare two dates allowing for 2-digit vs 4-digit year differences."""
    if not date_a or not date_b:
        return False
    digits_a = strip_non_alnum(date_a)
    digits_b = strip_non_alnum(date_b)

    if digits_a == digits_b:
        return True

    # If one is 8 digits (YYYYMMDD) and one is 6 digits (YYMMDD)
    if len(digits_a) == 8 and len(digits_b) == 6:
        return digits_a[2:] == digits_b
    if len(digits_a) == 6 and len(digits_b) == 8:
        return digits_b[2:] == digits_a

    norm_a = normalize_date_string(date_a)
    norm_b = normalize_date_string(date_b)
    if norm_a and norm_b:
        return norm_a == norm_b

    return False

