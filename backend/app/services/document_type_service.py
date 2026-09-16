"""Conservative OCR-based routing. Signals are rules, not ML probabilities."""
import re
from enum import StrEnum


class DocumentType(StrEnum):
    PASSPORT = 'PASSPORT'
    AADHAAR = 'AADHAAR'
    VISA = 'VISA'
    NATIONAL_ID = 'NATIONAL_ID'
    UNKNOWN = 'UNKNOWN'


IDENTIFIER = re.compile(r'(?<!\d)\d{4}[ \t]*\d{4}[ \t]*\d{4}(?!\d)')


def detect_document_type(text: str) -> dict:
    signals = []
    aadhaar = bool(re.search(r'\baadhaa?r\b|unique identification|आधार', text, re.I))
    india = bool(re.search(r'government of india|भारत सरकार', text, re.I))
    number = bool(IDENTIFIER.search(text))
    if aadhaar or (india and number):
        signals = [label for yes, label in [(aadhaar, 'Aadhaar / Unique Identification'),
                   (india, 'Government of India'), (number, '12-digit identifier pattern')] if yes]
        kind = DocumentType.AADHAAR
    elif re.search(r'\bvisa\b|^V<[A-Z]{3}', text, re.I | re.M):
        kind, signals = DocumentType.VISA, ['Visa label / MRV header']
    elif re.search(r'\bpassport\b|^P<[A-Z]{3}[A-Z<]+<<', text, re.I | re.M):
        kind, signals = DocumentType.PASSPORT, ['Passport label / TD3 header']
    elif re.search(r'national identity|national id\b|identity card|^[IAC]<[A-Z]{3}', text, re.I | re.M):
        kind, signals = DocumentType.NATIONAL_ID, ['National identity label / ID MRZ header']
    else:
        kind = DocumentType.UNKNOWN
    return {'type': kind.value, 'signals': signals, 'method': 'deterministic_rules'}


def not_applicable_mrz() -> dict:
    return {'applicable': False, 'status': 'NOT_APPLICABLE', 'type': None,
            'format': None, 'mrz_detected': False, 'mrz_valid': None,
            'validation_performed': False, 'checks': {}, 'raw_lines': [], 'mrz_errors': []}
