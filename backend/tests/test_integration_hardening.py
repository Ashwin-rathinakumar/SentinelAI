"""Deterministic endpoint regressions; real OCR/biometrics remain covered separately."""
import copy
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.database import Base, get_db
from app.models import ScreeningCase
from app.routers import screening
from app.schemas.screening import FaceResult, DatabaseResult, ForensicResult
from app.services import session_store, blockchain_service, face_service
from app.services.case_persistence_service import load_case_snapshot
from app.services.screening_services import validate_document


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cases.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def db_override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(session_store, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(session_store, "_sessions", {})
    monkeypatch.setattr(screening, "save_upload", lambda *a: None)
    monkeypatch.setattr(screening, "analyze_document_quality", lambda *a: {"ocr_readiness": 95})
    fields = {key: {"normalized": value} for key, value in {
        "full_name": "ANANYA SHARMA", "passport_number": "P1234567",
        "date_of_expiry": "2035-01-01", "date_of_birth": "1995-01-01"}.items()}
    ocr = {"status": "SUCCESS", "confidence": 98, "fields": fields,
           "document": {"type": "PASSPORT"},
           "mrz": {**copy.deepcopy(fields), "mrz_detected": True, "mrz_valid": True}}
    monkeypatch.setattr(screening, "extract_document", lambda *a: copy.deepcopy(ocr))
    monkeypatch.setattr(screening, "compare_faces", lambda *a: FaceResult(status="MATCH", match=True, similarity=.9))
    monkeypatch.setattr(screening, "forensic_analysis", lambda *a: ForensicResult(tamper_risk="LOW", score=0))
    monkeypatch.setattr(screening, "database_lookup", lambda *a, **kw: DatabaseResult(found=True, status="FOUND"))
    monkeypatch.setattr(face_service, "get_embedding_from_image", lambda *a: None)
    monkeypatch.setattr(blockchain_service, "prepare_safely", lambda *a, **kw: {"status": "CHAIN_UNAVAILABLE"})
    try:
        with TestClient(app) as client:
            yield client, factory, ocr
    finally:
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def submit(client):
    return client.post('/api/screen', files={"file": ('document.png', b'image', 'image/png'),
                                           "selfie": ('selfie.png', b'image', 'image/png')})


@pytest.mark.parametrize('scenario,code', [('clean', None), ('face', 'FACE_MISMATCH'),
    ('tamper', 'TAMPER_HIGH'), ('blacklist', 'WATCHLIST_MATCH'), ('expired', 'DOCUMENT_EXPIRED')])
def test_scenarios_and_offline_audit(pipeline, monkeypatch, scenario, code):
    client, factory, ocr = pipeline
    if scenario == 'face':
        monkeypatch.setattr(screening, 'compare_faces', lambda *a: FaceResult(match=False, status='MISMATCH', similarity=.1))
    if scenario == 'tamper':
        monkeypatch.setattr(screening, 'forensic_analysis', lambda *a: ForensicResult(content_tamper_detected=True, tamper_risk='HIGH', score=80))
    if scenario == 'blacklist':
        monkeypatch.setattr(screening, 'database_lookup', lambda *a, **kw: DatabaseResult(blacklisted=True, status='BLACKLISTED'))
    if scenario == 'expired':
        ocr['fields']['date_of_expiry']['normalized'] = '2020-01-01'
        ocr['mrz']['date_of_expiry']['normalized'] = '2020-01-01'
    response = submit(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['blockchain_audit']['status'] == 'CHAIN_UNAVAILABLE'
    if code:
        assert code in {r['code'] for r in body['risk']['reasons']}
        assert body['risk']['risk_score'] > 0
        assert body['risk']['recommendation'] != 'PROCEED_WITH_OFFICER_REVIEW'
    else:
        assert body['risk']['risk_score'] == 0
        assert body['risk']['recommendation'] == 'PROCEED_WITH_OFFICER_REVIEW'
    if scenario == 'blacklist':
        assert body['risk']['risk_level'] == 'CRITICAL'
    case_id = body['case_id']
    with factory() as db:
        assert load_case_snapshot(db, case_id)['blockchain_audit'] == body['blockchain_audit']
    # Lose both file and cache: the complete response must survive in SQL.
    session_store._sessions.clear()
    session_store._session_path(case_id).unlink()
    recovered = client.get(f'/api/cases/{case_id}').json()['case']
    assert recovered['risk'] == body['risk']
    listed = next(c for c in client.get('/api/cases').json()['cases'] if c['case_id'] == case_id)
    assert listed['risk'] == body['risk']
    assert listed['document_type'] == 'passport'
    for decision, canonical in [('APPROVED', 'APPROVE'), ('REJECTED', 'REJECT'), ('SECONDARY_INSPECTION', 'MANUAL_VERIFICATION')]:
        result = client.post(f'/api/cases/{case_id}/decision', json={'decision': decision, 'remarks': 'Reviewed'})
        assert result.status_code == 200, result.text
        saved = client.get(f'/api/cases/{case_id}').json()['case']
        assert saved['risk'] == body['risk']
        assert saved['officer_decision']['decision'] == canonical
        assert saved['officer_decision']['notes'] == 'Reviewed'
        assert saved['officer_decision']['timestamp']
        with factory() as db:
            assert db.query(ScreeningCase).filter_by(case_id=case_id).one().decision == canonical
            assert load_case_snapshot(db, case_id)['officer_decision'] == saved['officer_decision']


@pytest.mark.parametrize('module', ['compare_faces', 'forensic_analysis', 'database_lookup'])
def test_optional_failure_is_reviewable(pipeline, monkeypatch, module):
    client, _, _ = pipeline
    def fail(*a, **kw):
        raise RuntimeError('simulated runtime failure')
    monkeypatch.setattr(screening, module, fail)
    response = submit(client)
    assert response.status_code == 200
    body = response.json()
    assert body['risk']['recommendation'] == 'SECONDARY_INSPECTION'
    assert any(r['code'] == 'VERIFICATION_INCOMPLETE' for r in body['risk']['reasons'])


def test_unrelated_mrz_names_are_mismatch():
    result = validate_document({'full_name': {'normalized': 'ALICE EXAMPLE'}},
        {'mrz_detected': True, 'mrz_valid': True, 'full_name': {'normalized': 'BOB OTHER'}})
    assert result.consistency['full_name'] == 'MISMATCH'


def test_session_cannot_escape_directory():
    assert session_store.get_session('../outside') is None
