"""OCR character-confusion helpers. Raw OCR is never mutated."""

from __future__ import annotations

import re
import unicodedata

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
            # Mixed IDs: keep letters in letter-looking positions, map obvious digit confusions
            # when surrounded by digits.
            prev_digit = index > 0 and chars[index - 1].isdigit()
            next_digit = index + 1 < len(chars) and chars[index + 1].isdigit()
            if prev_digit or next_digit:
                chars[index] = chars[index].translate(CONFUSION_TO_DIGIT)
    return "".join(chars)


def mrz_sanitize_line(line: str) -> str:
    compact = re.sub(r"\s+", "", line.upper())
    compact = re.sub(r"[^A-Z0-9<]", "<", compact)
    # Common OCR confusion in MRZ digit/letter fields is handled during parse,
    # not by silently rewriting this canonical raw candidate.
    return compact
