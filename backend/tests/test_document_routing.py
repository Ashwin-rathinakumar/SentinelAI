"""Regression coverage uses equivalent OCR text; no personal source image supplied."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.services.document_type_service import detect_document_type, not_applicable_mrz
from app.services.aadhaar_service import extract_aadhaar, mask_numbers, detect_qr
from app.services.mrz_service import extract_mrz
from app.services import ocr_service, face_service
from app.services.screening_services import validate_document, calculate_risk, forensic_analysis, database_lookup
from app.schemas.screening import FaceResult, ForensicResult, DatabaseResult

TEXT = '''Government of India
Manis Singh
DOB: 16/01/2002
MALE
6984 5315 9260
Aadhaar is proof of identity, not of citizenship or date of birth
It should be used with verification (online authentication)'''
PASSPORT = 'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C<3UTO6908061F9406236ZE184226B<<<<<14'


def image_bytes(text=TEXT):
    image = Image.new('RGB', (1500, 850), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 30)
    for i, line in enumerate(text.splitlines()):
        draw.text((50, 50+i*90), line, fill='black', font=font)
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    return buf.getvalue()


@pytest.mark.parametrize('text,expected', [(TEXT, 'AADHAAR'), (PASSPORT, 'PASSPORT'),
    ('Government of India\n1234 5678 9012', 'AADHAAR'), ('ordinary receipt', 'UNKNOWN'),
    ('VISA\nName: Test Person', 'VISA'), ('National identity card', 'NATIONAL_ID')])
def test_classification(text, expected):
    result = detect_document_type(text)
    assert result['type'] == expected
    assert 'confidence' not in result


@pytest.mark.parametrize('key,expected', [('full_name', 'Manis Singh'), ('date_of_birth', '2002-01-16'),
    ('gender', 'MALE'), ('id_number', '698453159260'), ('masked_document_number', 'XXXX XXXX 9260'),
    ('issuing_country', 'India')])
def test_aadhaar_fields(key, expected):
    assert extract_aadhaar(TEXT, [])[key]['normalized'] == expected


@pytest.mark.parametrize('text', ['Aadhaar is proof of identity not date of birth\nIt should be used with verification',
    'DOB: 31/02/2002\nV', 'DOB: It should be used with verification\nM'])
def test_disclaimer_and_invalid_values(text):
    fields = extract_aadhaar(text, [])
    assert fields['date_of_birth']['normalized'] is None
    assert fields['gender']['normalized'] is None
    assert fields['full_name']['normalized'] is None
    assert not extract_mrz(text, [])['mrz_detected']


def test_year_bilingual_and_other_identity():
    fields = extract_aadhaar('भारत सरकार\nअनिता देवी\nAnita Devi\nYear of Birth: 1990\nFEMALE\n1234 5678 9012', [])
    assert fields['full_name']['normalized'] == 'Anita Devi'
    assert fields['year_of_birth']['normalized'] == '1990'
    assert fields['gender']['normalized'] == 'FEMALE'
    assert fields['id_number']['normalized'] == '123456789012'


def test_mask_all_nested_values():
    result = mask_numbers({'raw_text': TEXT, 'fields': extract_aadhaar(TEXT, []), 'regions': [{'text': '698453159260'}]})
    assert '698453159260' not in json.dumps(result)
    assert '6984 5315 9260' not in json.dumps(result)


def test_aadhaar_router_never_invokes_mrz(monkeypatch):
    monkeypatch.setattr(ocr_service, '_best_ocr', lambda _: ([{'text': line, 'confidence': .99} for line in TEXT.splitlines()], None, 0, 'enhanced'))
    mrz_spy = Mock(side_effect=AssertionError('Aadhaar invoked MRZ'))
    monkeypatch.setattr(ocr_service, 'extract_mrz', mrz_spy)
    result = ocr_service.extract_document('aadhaar-routing', image_bytes(), '.png', 'passport')
    assert result['document']['type'] == 'AADHAAR'
    assert result['mrz']['status'] == 'NOT_APPLICABLE'
    assert result['expiry'] == {'applicable': False, 'status': 'NOT_APPLICABLE'}
    mrz_spy.assert_not_called()


def risk_for(kind='AADHAAR', text=TEXT, face=None, tamper=None):
    fields = extract_aadhaar(text, []) if kind == 'AADHAAR' else {}
    mrz = not_applicable_mrz()
    validation = validate_document(fields, mrz, kind.lower())
    return calculate_risk({'ocr_readiness': 95}, {'confidence': 99, 'document': {'type': kind}},
        mrz, validation, tamper or ForensicResult(tamper_risk='LOW', score=0),
        face or FaceResult(status='MATCH', match=True, similarity=.9), DatabaseResult())


def test_aadhaar_no_passport_penalties():
    result = risk_for()
    assert result.risk_score == 0
    assert result.recommendation == 'SECONDARY_MANUAL_VERIFICATION'
    assert all(not c['applicable'] and c['points'] == 0 for c in result.checks)
    assert all(reason["code"] == "VERIFICATION_INCOMPLETE" and reason["points"] == 0 for reason in result.reasons)


def test_unknown_manual_review():
    assert risk_for('UNKNOWN').recommendation == 'SECONDARY_MANUAL_VERIFICATION'


def test_heuristics_never_establish_tampering():
    rng = np.random.default_rng(4)
    buf = io.BytesIO()
    Image.fromarray(rng.integers(0, 255, (250, 250, 3), dtype=np.uint8)).save(buf, 'PNG')
    forensic = forensic_analysis(buf.getvalue(), {'ocr_readiness': 99}, validate_document(extract_aadhaar(TEXT, []), {}, 'aadhaar'))
    assert forensic.recompression_detected
    assert forensic.content_tamper_detected is False
    assert forensic.tamper_status == 'INCONCLUSIVE'
    assert risk_for(tamper=forensic).risk_score == 0


@pytest.mark.parametrize('match', [True, False])
def test_aadhaar_biometric_embedding_comparison(monkeypatch, match):
    # Controlled ArcFace-sized embeddings exercise actual similarity/threshold logic;
    # this is not a claim that the generated card contains a real human portrait.
    monkeypatch.setattr(face_service, 'get_face_model_name', lambda: 'ArcFace')
    monkeypatch.setattr(face_service, '_using_insightface', True)
    embedding = np.zeros(512, dtype=np.float32)
    embedding[0] = 1
    other = embedding.copy() if match else np.roll(embedding, 1)
    detections = iter([[face_service.FaceDetection(bbox=[0, 0, 1000, 700], embedding=e)] for e in [embedding, other]])
    monkeypatch.setattr(face_service, 'detect_faces', lambda _: next(detections))
    result = face_service.verify_faces(image_bytes(), image_bytes())
    assert result.match is match
    assert result.threshold == .45
    assert result.model == 'ArcFace'
    assert risk_for(face=result).risk_score == (0 if match else 25)


def test_passport_checksum_still_enforced():
    assert extract_mrz(PASSPORT, [])['mrz_valid']
    assert not extract_mrz(PASSPORT.replace('L898902C<3', 'L898902C<9'), [])['mrz_valid']


def test_passport_router_invokes_mrz(monkeypatch):
    monkeypatch.setattr(ocr_service, '_best_ocr', lambda _: ([{'text': line, 'confidence': .99} for line in PASSPORT.splitlines()], None, 0, 'enhanced'))
    spy = Mock(wraps=extract_mrz)
    monkeypatch.setattr(ocr_service, 'extract_mrz', spy)
    result = ocr_service.extract_document('passport-routing', image_bytes(), '.png', 'aadhaar')
    assert result['document']['type'] == 'PASSPORT'
    assert result['mrz']['applicable'] and result['mrz']['mrz_valid']
    spy.assert_called_once()


def test_invalid_date_normalization():
    from app.services.ocr_normalize import normalize_date_string
    assert normalize_date_string('It should be used with verification') is None
    assert normalize_date_string('31/02/2002') is None


def test_failed_ocr_routes_unknown(monkeypatch):
    from app.routers import screening
    monkeypatch.setattr(screening, 'extract_document', lambda *args: {'status': 'FAILED', 'fields': {}})
    with TestClient(app) as client:
        body = client.post('/api/screen', files={'file': ('blank.png', image_bytes(), 'image/png')}).json()
    assert body['document']['type'] == 'UNKNOWN'
    assert body['mrz']['status'] == 'NOT_APPLICABLE'
    assert body['risk']['recommendation'] == 'SECONDARY_MANUAL_VERIFICATION'
    assert all(not c['applicable'] and c['points'] == 0 for c in body['risk']['checks'])


def test_qr_detection_is_not_authentication():
    qr = __import__('cv2').QRCodeEncoder_create().encode('test payload only')
    qr = __import__('cv2').copyMakeBorder(qr, 8, 8, 8, 8, __import__('cv2').BORDER_CONSTANT, value=255)
    qr = __import__('cv2').resize(qr, (400, 400), interpolation=__import__('cv2').INTER_NEAREST)
    assert detect_qr(qr)['status'] == 'QR_DETECTED_NOT_VERIFIED'
    assert detect_qr(np.full((300, 300), 255, np.uint8))['status'] == 'QR_NOT_FOUND'


@pytest.mark.parametrize('selfie_file,expected', [('astronaut_public_domain.png', True),
                                               ('grace_hopper_public_domain.jpg', False)])
def test_real_arcface_aadhaar_portrait(selfie_file, expected):
    samples = Path(__file__).parent / 'demo_samples'
    specimen = Image.open(io.BytesIO(image_bytes())).convert('RGB')
    portrait = Image.open(samples / 'astronaut_public_domain.png').crop((150, 30, 310, 200))
    specimen.paste(portrait.resize((320, 340)), (1120, 100))
    buf = io.BytesIO()
    specimen.save(buf, 'PNG')
    result = face_service.verify_faces(buf.getvalue(), (samples / selfie_file).read_bytes())
    assert result.model == 'ArcFace'
    assert result.match is expected, result.model_dump()
    assert result.threshold == .45
    assert result.image_quality == 'BIOMETRIC_EMBEDDING_MATCH'


def test_no_fabricated_face_or_pixel_fallback():
    result = face_service.verify_faces(image_bytes(), image_bytes())
    assert result.match is None
    assert result.status == 'FAILED'
    assert result.similarity is None


def test_real_ocr_aadhaar_api_regression():
    # Real OCR, HTTP route, validation, forensics, registry, risk and saved-case reads.
    # Deliberately submit a WRONG passport hint to reproduce the reported failure.
    with TestClient(app) as client:
        response = client.post('/api/screen', files={'file': ('regression.png', image_bytes(), 'image/png')}, data={'document_type': 'passport'})
        assert response.status_code == 200
        body = response.json()
        assert body['document']['type'] == 'AADHAAR'
        assert body['mrz']['status'] == body['expiry']['status'] == 'NOT_APPLICABLE'
        assert body['ocr']['fields']['full_name']['normalized'] == 'Manis Singh'
        assert body['ocr']['fields']['date_of_birth']['normalized'] == '2002-01-16'
        assert body['ocr']['fields']['gender']['normalized'] == 'MALE'
        assert body['ocr']['fields']['id_number']['normalized'] == 'XXXX XXXX 9260'
        assert body['risk']['risk_score'] < 30
        assert body['risk']['recommendation'] == 'SECONDARY_MANUAL_VERIFICATION'
        assert '698453159260' not in response.text and '6984 5315 9260' not in response.text
        saved = client.get('/api/cases/' + body['case_id']).text
        assert '698453159260' not in saved and '6984 5315 9260' not in saved
        assert database_lookup('B7654321').blacklisted
        assert database_lookup('A12345678').found


def _region(text, x1, y1, x2, y2):
    return {'text': text, 'confidence': .95,
            'box': [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}


def test_bilingual_d0b_layout_regression():
    """Reproduces the actual OCR tokens and relative boxes without retaining PII imagery."""
    regions = [
        _region('Governmentof India', 280, 79, 617, 114),
        _region('Manis Singh', 355, 212, 527, 248),
        _region('可a / D0B: 16/01/2002', 355, 251, 732, 294),
        _region('/ MALE', 355, 305, 527, 345),
        _region('1234 5678 9012', 355, 390, 700, 430),
        _region('Aadhaar is proof of identity,not of citizenship', 489, 473, 988, 503),
        _region('or date of birth.It should be used with verification(online', 490, 504, 1111, 532),
    ]
    raw = '\n'.join(region['text'] for region in regions)
    fields = extract_aadhaar(raw, regions)
    assert fields['full_name']['normalized'] == 'Manis Singh'
    assert fields['date_of_birth']['normalized'] == '2002-01-16'
    assert fields['gender']['normalized'] == 'MALE'
    validation = validate_document(fields, not_applicable_mrz(), 'aadhaar')
    assert 'MISSING_REQUIRED_FIELD' not in validation.reason_codes


@pytest.mark.parametrize('label', [
    'DOB 16/01/2002',
    'D0B: 16/01/2002',
    'D O B : 16 / 01 / 2002',
    'Date of Birth: 16-01-2002',
    'जन्मतिथि / DOB: 16/01/2002',
])
def test_dob_label_and_spacing_variants(label):
    fields = extract_aadhaar(f'MANIS SINGH\n{label}\nMALE', [])
    assert fields['full_name']['normalized'] == 'MANIS SINGH'
    assert fields['date_of_birth']['normalized'] == '2002-01-16'


def test_merged_name_above_dob():
    fields = extract_aadhaar('Government of India\nManisSingh\nD0B:16/01/2002\nMALE', [])
    assert fields['full_name']['normalized'] == 'Manis Singh'


def test_layout_chooses_nearest_aligned_name():
    regions = [
        _region('Ravi Kumar', 700, 60, 880, 95),
        _region('Manis Singh', 350, 205, 525, 245),
        _region('D0B: 16/01/2002', 352, 250, 700, 290),
    ]
    fields = extract_aadhaar('\n'.join(r['text'] for r in regions), regions)
    assert fields['full_name']['normalized'] == 'Manis Singh'


@pytest.mark.parametrize('candidate', [
    'Government of India',
    'Aadhaar is proof of identity',
    'It should be used with verification',
    'Issued Date',
    'MALE',
])
def test_headers_and_disclaimer_never_become_name(candidate):
    fields = extract_aadhaar(f'{candidate}\nD0B: 16/01/2002', [])
    assert fields['full_name']['normalized'] is None


def test_missing_name_not_fabricated_from_distant_region():
    regions = [
        _region('Ravi Kumar', 800, 20, 980, 55),
        _region('D0B: 16/01/2002', 350, 300, 700, 340),
        _region('MALE', 350, 350, 450, 390),
    ]
    fields = extract_aadhaar('\n'.join(r['text'] for r in regions), regions)
    assert fields['full_name']['normalized'] is None
    assert fields['full_name']['status'] == 'REQUIRED_MISSING'


def test_d0b_invalid_calendar_date_rejected():
    fields = extract_aadhaar('Manis Singh\nD0B: 31/02/2002\nMALE', [])
    assert fields['date_of_birth']['normalized'] is None
