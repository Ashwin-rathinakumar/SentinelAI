"""Deterministic regression tests for passport OCR field extraction and MRZ parsing."""

from pathlib import Path
import sys
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services.field_extractor import extract_fields
from app.services.mrz_service import extract_mrz, compute_check_digit, validate_check_digit
from app.services.ocr_normalize import clean_nationality, normalize_date_string, split_person_name
from app.services.screening_services import validate_document


INDIAN_PASSPORT_VALID_MRZ = """Type / Type Country Code / Code Pays Passport No. / Passeport No.
P IND U1234567
Surname / Nom
SHARMA
Given Name(s) / Prénoms
ANANYA
Nationality / Nationalité Sex / Sexe Date of Birth / Date de naissance
INDIAN F 15/08/1995
Place of Birth / Lieu de naissance
NEW DELHI, DELHI
Place of Issue / Lieu de délivrance
NEW DELHI
Date of Issue / Date de délivrance Date of Expiry / Date d'expiration
01/01/2022 31/12/2032
P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<
U1234567<6IND9508152F3212312<<<<<<<<<<<<<<<<<<4"""


INDIAN_PASSPORT_TAMPERED_MRZ = """Type / Type Country Code / Code Pays Passport No. / Passeport No.
P IND U1234567
Surname / Nom
SHARMA
Given Name(s) / Prénoms
ANANYA
Nationality / Nationalité Sex / Sexe Date of Birth / Date de naissance
INDIAN F 15/08/1995
Place of Birth / Lieu de naissance
NEW DELHI, DELHI
Place of Issue / Lieu de délivrance
NEW DELHI
Date of Issue / Date de délivrance Date of Expiry / Date d'expiration
01/01/2022 31/12/2032
P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<
U1234567<8IND9508156F3212319<<<<<<<<<<<<<<<<<<4"""


def test_indian_passport_field_extraction_and_valid_mrz():
    lines = [line.strip() for line in INDIAN_PASSPORT_VALID_MRZ.splitlines() if line.strip()]
    regions = [{"text": line, "box": [[0, i * 40], [400, i * 40], [400, (i + 1) * 40], [0, (i + 1) * 40]]} for i, line in enumerate(lines)]

    mrz = extract_mrz(INDIAN_PASSPORT_VALID_MRZ, regions)
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is True
    assert mrz["status"] == "MRZ_FOUND_AND_VALID"
    assert mrz["checks"]["document_number"] is True
    assert mrz["checks"]["date_of_birth"] is True
    assert mrz["checks"]["date_of_expiry"] is True
    assert mrz["checks"]["composite"] is True
    assert mrz["passport_number"]["normalized"] == "U1234567"
    assert mrz["nationality"]["normalized"] == "IND"
    assert mrz["date_of_birth"]["normalized"] == "1995-08-15"
    assert mrz["date_of_expiry"]["normalized"] == "2032-12-31"
    assert mrz["surname"]["normalized"] == "SHARMA"
    assert mrz["given_names"]["normalized"] == "ANANYA"
    assert mrz["full_name"]["normalized"] == "ANANYA SHARMA"

    fields = extract_fields("passport", INDIAN_PASSPORT_VALID_MRZ, regions, mrz)
    assert fields["passport_number"]["normalized"] == "U1234567"
    assert fields["surname"]["normalized"] == "SHARMA"
    assert fields["given_names"]["normalized"] == "ANANYA"
    assert "ANANYA" in fields["full_name"]["normalized"] and "SHARMA" in fields["full_name"]["normalized"]
    assert fields["nationality"]["normalized"] == "INDIAN"
    assert fields["gender"]["normalized"] == "F"
    assert fields["date_of_birth"]["normalized"] == "1995-08-15"
    assert fields["date_of_issue"]["normalized"] == "2022-01-01"
    assert fields["date_of_expiry"]["normalized"] == "2032-12-31"
    assert fields["place_of_birth"]["normalized"] == "NEW DELHI, DELHI"
    assert fields["place_of_issue"]["normalized"] == "NEW DELHI"


def test_indian_passport_field_extraction_with_mrz_detected_even_if_tampered():
    lines = [line.strip() for line in INDIAN_PASSPORT_TAMPERED_MRZ.splitlines() if line.strip()]
    regions = [{"text": line, "box": [[0, i * 40], [400, i * 40], [400, (i + 1) * 40], [0, (i + 1) * 40]]} for i, line in enumerate(lines)]

    mrz = extract_mrz(INDIAN_PASSPORT_TAMPERED_MRZ, regions)
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is False
    assert mrz["status"] == "MRZ_FOUND_AND_INVALID"
    assert mrz["checks"]["document_number"] is False
    assert mrz["checks"]["date_of_birth"] is False
    assert mrz["checks"]["date_of_expiry"] is False
    assert mrz["checks"]["composite"] is False
    assert mrz["passport_number"]["normalized"] == "U1234567"

    fields = extract_fields("passport", INDIAN_PASSPORT_TAMPERED_MRZ, regions, mrz)
    assert fields["passport_number"]["normalized"] == "U1234567"
    assert fields["surname"]["normalized"] == "SHARMA"
    assert fields["given_names"]["normalized"] == "ANANYA"
    assert "ANANYA" in fields["full_name"]["normalized"] and "SHARMA" in fields["full_name"]["normalized"]
    assert fields["nationality"]["normalized"] == "INDIAN"


@pytest.mark.parametrize("label", ["Given Name", "Given Name(s)", "Given Names", "GivenName(s)"])
def test_given_name_label_variants_do_not_leak_suffix(label):
    raw_text = f"Surname\nSHARMA\n{label}\nANANYA\nDate of Expiry\n31/12/2032"
    fields = extract_fields("passport", raw_text, [], None)
    assert fields["surname"]["raw"] == "SHARMA"
    assert fields["surname"]["normalized"] == "SHARMA"
    assert fields["given_names"]["raw"] == "ANANYA"
    assert fields["given_names"]["normalized"] == "ANANYA"
    assert fields["full_name"]["normalized"] == "ANANYA SHARMA"


def _region(text, x1, y1, x2, y2):
    return {"text": text, "box": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], "score": 0.95}


def test_real_case_399a0c78_layout_and_consistency_regression():
    """Exercise the production parser with the real OCR text/layout, not mocked fields."""
    regions = [
        _region("/Surname", 537, 191, 715, 219),
        _region("SHARMA", 561, 237, 697, 271),
        _region("/GivenName(s)", 533, 281, 834, 314),
        _region("ANANYA", 559, 332, 698, 370),
        _region("a/Nationality", 537, 382, 754, 412),
        _region("f/Sex", 865, 376, 978, 407),
        _region("fa/Date ofBirth", 1090, 373, 1339, 403),
        _region("15/08/1995", 1100, 424, 1319, 458),
        _region("INDIAN", 557, 433, 703, 469),
        _region("/PlaceofBirth", 535, 480, 799, 511),
        _region("NEW DELHI, DELHI", 557, 531, 915, 566),
        _region("/Pacssue", 536, 583, 863, 610),
        _region("NEW DELHI", 555, 630, 763, 666),
        _region("R市l&K/Holder'sSignature", 137, 650, 469, 678),
        # Slight Y differences originally made expiry sort before issue.
        _region("可chvfaf/Dateoflssue", 535, 683, 889, 712),
        _region("ffafa/DateofExpiry", 992, 679, 1316, 711),
        _region("01/01/2022", 557, 733, 778, 768),
        _region("31/12/2032", 1006, 731, 1229, 765),
        _region("P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<", 88, 848, 1337, 893),
        _region("U1234567<8IND9508156F3212319<<<<<<<<<<<<<<<<<<4", 87, 926, 1340, 967),
    ]
    raw_text = "\n".join(region["text"] for region in regions)
    mrz = extract_mrz(raw_text, regions)
    fields = extract_fields("passport", raw_text, regions, mrz)

    assert fields["surname"] == {"raw": "SHARMA", "normalized": "SHARMA", "status": "DETECTED"}
    assert fields["given_names"] == {"raw": "ANANYA", "normalized": "ANANYA", "status": "DETECTED"}
    assert fields["full_name"]["normalized"] == "ANANYA SHARMA"
    assert fields["place_of_issue"]["normalized"] == "NEW DELHI"
    assert fields["date_of_issue"]["normalized"] == "2022-01-01"
    assert fields["date_of_expiry"]["normalized"] == "2032-12-31"

    # The visible source digits are invalid, but visual-zone identity values agree.
    assert mrz["status"] == "MRZ_FOUND_AND_INVALID"
    assert mrz["mrz_valid"] is False
    validation = validate_document(fields, mrz, "passport")
    assert validation.consistency == {
        "passport_number": "MATCH",
        "date_of_birth": "MATCH",
        "date_of_expiry": "MATCH",
        "full_name": "MATCH",
        "nationality": "MATCH",
    }
    assert "OCR_MRZ_MISMATCH" not in validation.reason_codes
    assert "MRZ_CHECK_FAILED" in validation.reason_codes


def test_nationality_cleaning_prevents_date_pollution():
    assert clean_nationality("15/08/1995 INDIAN") == "INDIAN"
    assert clean_nationality("INDIAN 15/08/1995") == "INDIAN"
    assert clean_nationality("IND") == "INDIAN"
    assert clean_nationality("F 15/08/1995 INDIAN") == "INDIAN"
    assert clean_nationality("AMERICAN 01-JAN-1990") == "AMERICAN"
    assert clean_nationality("1990-01-01") is None


def test_name_assembly_from_components():
    labeled_text = "Surname: SHARMA\nGiven Name: ANANYA\nPassport No: U1234567\nExpiry: 31/12/2032"
    fields2 = extract_fields("passport", labeled_text, [], None)
    assert fields2["surname"]["normalized"] == "SHARMA"
    assert fields2["given_names"]["normalized"] == "ANANYA"
    assert fields2["full_name"]["normalized"] == "ANANYA SHARMA"


def test_passport_number_safe_fallback_from_unlabeled_text():
    raw_text = """PASSPORT
    REPUBLIC OF INDIA
    NATIONALITY: INDIAN
    SEX: F
    DOB: 15/08/1995
    U1234567
    DATE OF EXPIRY: 31/12/2032
    """
    fields = extract_fields("passport", raw_text, [], None)
    assert fields["passport_number"]["normalized"] == "U1234567"
    assert fields["passport_number"]["status"] == "DETECTED"


def test_mrz_spatial_fragment_reconstruction():
    # Simulate EasyOCR breaking TD3 line 1 and line 2 into 4 distinct bounding box boxes
    regions = [
        {"text": "P<INDSHARMA<<", "box": [[10, 800], [150, 800], [150, 825], [10, 825]]},
        {"text": "ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<", "box": [[155, 800], [450, 800], [450, 825], [155, 825]]},
        {"text": "U1234567<6IND9508152F3212312<<", "box": [[10, 835], [300, 835], [300, 860], [10, 860]]},
        {"text": "<<<<<<<<<<<<<<4", "box": [[305, 835], [450, 835], [450, 860], [305, 860]]},
    ]
    raw_text = "\n".join(r["text"] for r in regions)
    mrz = extract_mrz(raw_text, regions)
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is True
    assert mrz["passport_number"]["normalized"] == "U1234567"
    assert mrz["full_name"]["normalized"] == "ANANYA SHARMA"


def test_mrz_ocr_spaced_lines():
    line1 = "P < I N D S H A R M A < < A N A N Y A < < < < < < < < < < < < < < < < < < < < < < < < < < < <"
    line2 = "U 1 2 3 4 5 6 7 < 6 I N D 9 5 0 8 1 5 2 F 3 2 1 2 3 1 2 < < < < < < < < < < < < < < < < 4"
    mrz = extract_mrz(f"{line1}\n{line2}", [])
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is True
    assert mrz["passport_number"]["normalized"] == "U1234567"


def test_mrz_surrounding_ocr_noise():
    line1 = "|«P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "U1234567<6IND9508152F3212312<<<<<<<<<<<<<<<<<<4|]"
    mrz = extract_mrz(f"{line1}\n{line2}", [])
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is True
    assert mrz["passport_number"]["normalized"] == "U1234567"


def test_mrz_checksum_failures_detected():
    # Tamper check digit of passport number: replace '6' with '9'
    line1 = "P<INDSHARMA<<ANANYA<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
    line2 = "U1234567<9IND9508152F3212312<<<<<<<<<<<<<<<<<<0"
    mrz = extract_mrz(f"{line1}\n{line2}", [])
    assert mrz["mrz_detected"] is True
    assert mrz["mrz_valid"] is False
    assert mrz["status"] == "MRZ_FOUND_AND_INVALID"
    assert mrz["checks"]["document_number"] is False
    assert any("Passport Number check digit" in err for err in mrz["mrz_errors"])


def test_mrz_malformed_incomplete_reports_unreadable():
    # Incomplete line 1, no line 2
    raw_text = "P<INDSHARMA<<ANANYA"
    mrz = extract_mrz(raw_text, [])
    assert mrz["mrz_detected"] is False
    assert mrz["mrz_valid"] is False
    assert mrz["status"] == "MRZ_UNREADABLE"


def test_missing_mrz_reports_not_detected():
    raw_text = "Standard invoice document with total 100 USD"
    mrz = extract_mrz(raw_text, [])
    assert mrz["mrz_detected"] is False
    assert mrz["mrz_valid"] is False
    assert mrz["status"] == "MRZ_NOT_DETECTED"
