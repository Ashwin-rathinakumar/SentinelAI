from pathlib import Path
import sys
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.services.mrz_service import extract_mrz
from app.services.screening_services import database_lookup, forensic_analysis

client = TestClient(app)
SAMPLES_DIR = Path(__file__).resolve().parent / 'demo_samples'


def test_system_health():
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'healthy'
    assert 'version' in data


def test_mrz_td3_check_digits_valid():
    lines = [
        'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<',
        'L898902C<3UTO6908061F9406236ZE184226B<<<<<14',
    ]
    res = extract_mrz('\n'.join(lines), lines)
    assert res['mrz_detected'] is True
    assert res['mrz_valid'] is True
    assert res['checks']['document_number'] is True
    assert res['checks']['date_of_birth'] is True
    assert res['checks']['date_of_expiry'] is True
    assert res['checks']['composite'] is True


def test_mrz_td3_tampered_check_digit():
    lines = [
        'P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<',
        'L898902C<9UTO6908061F9406236ZE184226B<<<<<14',
    ]
    res = extract_mrz('\n'.join(lines), lines)
    assert res['mrz_detected'] is True
    assert res['mrz_valid'] is False
    assert res['checks']['document_number'] is False


def test_database_watchlist_lookup():
    rec = database_lookup('B7654321')
    assert rec.found is True
    assert rec.blacklisted is True
    assert rec.status == 'BLACKLISTED'


def test_database_active_lookup():
    rec = database_lookup('A12345678')
    assert rec.found is True
    assert rec.blacklisted is False
    assert rec.status == 'FOUND'



def test_screen_case1_valid_passport():
    sample_file = SAMPLES_DIR / 'case1_valid_passport.png'
    selfie_file = SAMPLES_DIR / 'case1_selfie_match.png'
    assert sample_file.exists()

    with open(sample_file, 'rb') as doc_f, open(selfie_file, 'rb') as selfie_f:
        resp = client.post(
            '/api/screen',
            files={
                'file': ('case1.png', doc_f, 'image/png'),
                'selfie': ('selfie.png', selfie_f, 'image/png'),
            },
            data={'document_type': 'passport', 'officer_id': 'TEST-OFFICER'},
        )
    assert resp.status_code == 200
    res = resp.json()
    assert res['case_id'].startswith('CASE-')
    assert res['mrz']['mrz_valid'] is True
    assert res['risk']['risk_level'] in ['LOW RISK', 'MEDIUM RISK']
    assert res['quality']['ocr_readiness'] > 60


def test_screen_case4_watchlist_triggers_high_risk():
    sample_file = SAMPLES_DIR / 'case4_watchlist_blacklisted.png'
    assert sample_file.exists()

    with open(sample_file, 'rb') as doc_f:
        resp = client.post(
            '/api/screen',
            files={'file': ('case4.png', doc_f, 'image/png')},
            data={'document_type': 'passport'},
        )
    assert resp.status_code == 200
    res = resp.json()
    assert res['database']['blacklisted'] is True
    assert res['risk']['risk_score'] >= 50
    assert 'HIGH' in res['risk']['risk_level']


def test_officer_decision_lifecycle():
    sample_file = SAMPLES_DIR / 'case1_valid_passport.png'
    with open(sample_file, 'rb') as doc_f:
        screen_resp = client.post(
            '/api/screen',
            files={'file': ('case_decision_test.png', doc_f, 'image/png')},
            data={'document_type': 'passport'},
        )
    case_id = screen_resp.json()['case_id']

    dec_resp = client.post(
        f'/api/cases/{case_id}/decision',
        json={
            'decision': 'APPROVE',
            'notes': 'Physical security features and holograms inspected and confirmed.',
            'officer_id': 'INSPECTOR-102',
        },
    )
    assert dec_resp.status_code == 200
    saved_case = dec_resp.json()['case']
    assert saved_case['officer_decision']['decision'] == 'APPROVE'
    assert saved_case['officer_decision']['officer_id'] == 'INSPECTOR-102'

    get_resp = client.get(f'/api/cases/{case_id}')
    assert get_resp.status_code == 200
    assert get_resp.json()['case']['officer_decision']['decision'] == 'APPROVE'
