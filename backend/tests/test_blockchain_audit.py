"""Provider unit tests use synthetic private data; optional integration uses real Hardhat."""
import copy
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.database import Base
from app.models import VerificationCase
from app.audit_models import BlockchainAudit
from app.services import blockchain_service as service
from app.services.audit_canonicalizer import canonical_json, snapshot, audit_digest, case_key
from app.services.blockchain_config import BlockchainConfig

CASE = "CASE-AUDIT-TEST"
SECRET = "test-only-key-with-at-least-32-bytes"
CONFIG = BlockchainConfig(enabled=True, contract_address="0x" + "12" * 20, hmac_key=SECRET)


class FakeChain:
    records = {}
    calls = []
    def __init__(self, config):
        self.config = config
    def read(self, key, kind, version):
        return self.records.get((key, kind, version), {"exists": False})
    def send(self, key, kind, version, digest):
        self.calls.append((key, kind, version, digest))
        self.records[(key, kind, version)] = {"exists": True, "digest": digest, "timestamp": 1789400000}
        return "0x" + "ab" * 32
    def receipt(self, tx_hash):
        return {"transaction_hash": tx_hash, "block_number": 7}
    def locate(self, key, kind, version):
        return {"transaction_hash": "0x" + "ab" * 32, "block_number": 7}


@pytest.fixture
def saved(tmp_path, monkeypatch):
    factory = sessionmaker(bind=create_engine(f"sqlite:///{tmp_path / 'audit.db'}", connect_args={"check_same_thread": False}))
    Base.metadata.create_all(factory.kw['bind'])
    monkeypatch.setattr(service, "SessionLocal", factory)
    from app.routers import blockchain
    monkeypatch.setattr(blockchain, "SessionLocal", factory)
    monkeypatch.setattr(service, "SESSIONS_DIR", tmp_path)
    monkeypatch.setattr(service, "get_config", lambda: CONFIG)
    monkeypatch.setattr(service, "EVMClient", FakeChain)
    FakeChain.records, FakeChain.calls = {}, []
    payload = {"case_id": CASE, "timestamp": "2026-09-14T12:00:00+00:00", "document_type": "aadhaar",
        "ocr": {"fields": {"full_name": {"normalized": "Manis Singh"}, "id_number": {"normalized": "698453159260"},
                "masked_document_number": {"normalized": "XXXX XXXX 9260"}, "date_of_birth": {"normalized": "2002-01-16"}},
                "raw_text": "private OCR text", "processed_image": "C:/private/image.png"},
        "face": {"status": "MATCH", "match": True, "similarity": .99, "document_face_crop": "data:image/png;base64,private", "embedding": [1]*512},
        "risk": {"risk_score": 0, "risk_level": "LOW RISK"}, "officer_decision": None}
    path = tmp_path / f"{CASE}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with factory() as db:
        db.add(VerificationCase(case_id=CASE, risk_score=0, watchlist_match=False, duplicate_identity=False))
        db.commit()
    return payload, path, factory


def test_canonical_order_numbers_and_utf8():
    assert canonical_json({"b": 1.0, "a": "नाम", "c": -0.0}) == '{"a":"नाम","b":1,"c":0}'
    assert canonical_json({"a": True, "b": None}) == canonical_json({"b": None, "a": True})


@pytest.mark.parametrize("number", [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_rejected(number):
    with pytest.raises(ValueError): canonical_json({"score": number})


def test_case_key_and_hmac_stability():
    assert len(case_key(CASE)) == 66 and case_key(CASE) == case_key(CASE)
    assert CASE not in case_key(CASE)
    assert audit_digest({"a": 1, "b": 2}, SECRET) == audit_digest({"b": 2.0, "a": 1.0}, SECRET)
    assert audit_digest({"a": 2}, SECRET) != audit_digest({"a": 1}, SECRET)
    assert audit_digest({"a": 1}, SECRET) != audit_digest({"a": 1}, SECRET + "different")


def test_weak_hmac_key_rejected():
    with pytest.raises(ValueError): audit_digest({}, "weak")


def test_snapshot_excludes_images_paths_embeddings_and_transient_data(saved):
    case, _, _ = saved
    base = snapshot(case, {}, "SCREENING_RESULT", 1)
    text = canonical_json(base)
    for forbidden in ["private OCR text", "C:/private/image.png", "data:image", "embedding"]:
        assert forbidden not in text
    changed = copy.deepcopy(case)
    changed.update(updated_at="later", filename="different.png")
    changed['face']['document_face_crop'] = "different image"
    assert snapshot(changed, {}, "SCREENING_RESULT", 1) == base


def test_disabled_skips_provider_and_rows(saved, monkeypatch):
    monkeypatch.setattr(service, "get_config", lambda: replace(CONFIG, enabled=False))
    assert service.prepare(CASE)['status'] == 'NOT_ANCHORED'
    assert not FakeChain.calls
    with saved[2]() as db: assert db.query(BlockchainAudit).count() == 0


def test_anchor_idempotency_and_metadata(saved):
    first = service.prepare(CASE)
    second = service.prepare(CASE)
    assert first['id'] == second['id']
    anchored = service.operate(first['id'])
    service.operate(first['id'])
    assert len(FakeChain.calls) == 1
    assert anchored['status'] == 'ANCHORED' and anchored['block_number'] == 7
    assert anchored['transaction_hash'] and anchored['anchored_at']
    with saved[2]() as db: assert db.get(BlockchainAudit, first['id']).transaction_hash == anchored['transaction_hash']


def test_verify_requires_fresh_digest_equality(saved):
    record = service.prepare(CASE)
    service.operate(record['id'])
    assert service.operate(record['id'], verify=True)['status'] == 'VERIFIED'
    with saved[2]() as db:
        db.query(VerificationCase).filter_by(case_id=CASE).update({"risk_score": 9})
        db.commit()
    result = service.operate(record['id'], verify=True)
    assert result['status'] == 'TAMPER_DETECTED' and result['digest_match'] is False
    with saved[2]() as db:
        db.query(VerificationCase).filter_by(case_id=CASE).update({"risk_score": 0})
        db.commit()
    assert service.operate(record['id'], verify=True)['status'] == 'VERIFIED'


def test_json_edit_bypasses_cache_and_fails_verification(saved):
    record = service.prepare(CASE); service.operate(record['id'])
    case, path, _ = saved
    case['risk']['risk_score'] = 20
    path.write_text(json.dumps(case), encoding='utf-8')
    assert service.operate(record['id'], verify=True)['status'] == 'TAMPER_DETECTED'


def test_retry_does_not_rebase_modified_unanchored_case(saved):
    record = service.prepare(CASE)
    case, path, _ = saved
    case['risk']['risk_score'] = 20
    path.write_text(json.dumps(case), encoding='utf-8')
    result = service.operate(service.prepare(CASE)['id'])
    assert result['status'] == 'TAMPER_DETECTED' and not FakeChain.calls


def test_frozen_payload_tampering_detected(saved):
    record = service.prepare(CASE); service.operate(record['id'])
    with saved[2]() as db:
        db.get(BlockchainAudit, record['id']).canonical_payload = '{}'
        db.commit()
    assert service.operate(record['id'], verify=True)['status'] == 'TAMPER_DETECTED'


@pytest.mark.parametrize('error,status', [(service.ChainUnavailable(), 'CHAIN_UNAVAILABLE'), (ValueError('private-key-must-not-leak'), 'FAILED')])
def test_chain_failures_sanitized(saved, monkeypatch, error, status):
    record = service.prepare(CASE)
    def fail(_): raise error
    monkeypatch.setattr(service, 'EVMClient', fail)
    result = service.operate(record['id'])
    assert result['status'] == status and result['digest_match'] is None
    assert 'private-key-must-not-leak' not in json.dumps(result)


def test_no_record_never_verified(saved):
    record = service.prepare(CASE)
    result = service.operate(record['id'], verify=True)
    assert result['status'] == 'NOT_ANCHORED' and result['digest_match'] is None


def test_wrong_chain_binding_fails(saved, monkeypatch):
    record = service.prepare(CASE)
    monkeypatch.setattr(service, 'get_config', lambda: replace(CONFIG, chain_id=11155111))
    assert service.operate(record['id'])['status'] == 'FAILED'
    assert not FakeChain.calls


def test_confirmation_timeout_retry_reconciles_same_transaction(saved, monkeypatch):
    from web3.exceptions import TimeExhausted
    record = service.prepare(CASE)
    def pending(self, tx_hash):
        raise TimeExhausted('Receipt timeout')
    monkeypatch.setattr(FakeChain, 'receipt', pending)
    first = service.operate(record['id'])
    assert first['status'] == 'PENDING' and first['transaction_hash']
    # The mined record is found on the next read, even though receipt wait timed out.
    second = service.operate(record['id'])
    assert second['status'] == 'ANCHORED' and len(FakeChain.calls) == 1


def test_concurrent_retries_do_not_duplicate_transactions(saved):
    from concurrent.futures import ThreadPoolExecutor
    record = service.prepare(CASE)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(service.operate, [record['id'], record['id']]))
    assert all(result['status'] == 'ANCHORED' for result in results)
    assert len(FakeChain.calls) == 1


def test_missing_hmac_is_safe_and_creates_no_claim(saved, monkeypatch):
    monkeypatch.setattr(service, 'get_config', lambda: replace(CONFIG, hmac_key=''))
    assert service.prepare_safely(CASE)['status'] == 'FAILED'
    assert not FakeChain.calls


def test_contract_call_privacy(saved):
    record = service.prepare(CASE); service.operate(record['id'])
    key, kind, version, digest = FakeChain.calls[0]
    assert len(key) == len(digest) == 66 and kind == 0 and version == 1
    encoded = json.dumps(FakeChain.calls)
    for value in ['Manis Singh', '698453159260', 'XXXX XXXX 9260', '2002-01-16', 'image.png', 'private OCR text', 'embedding', 'data:image', CASE]:
        assert value not in encoded


def test_officer_separate_records_and_version_history(saved):
    screening = service.prepare(CASE); service.operate(screening['id'])
    case, path, factory = saved
    for version, decision in [(1, 'APPROVE'), (2, 'MANUAL_VERIFICATION')]:
        case['officer_decision'] = {'decision': decision, 'notes': 'Private officer notes', 'officer_id': 'TEST', 'timestamp': f'2026-09-14T12:0{version}:00Z'}
        path.write_text(json.dumps(case), encoding='utf-8')
        with factory() as db:
            row = db.query(VerificationCase).filter_by(case_id=CASE).first()
            row.decision, row.officer_notes, row.officer_id = decision, 'Private officer notes', 'TEST'
            db.commit()
        record = service.prepare(CASE, 'OFFICER_DECISION', new_decision=True)
        assert record['version'] == version
        assert service.prepare(CASE, 'OFFICER_DECISION', new_decision=True)['id'] == record['id']
        service.operate(record['id'])
    assert service.operate(screening['id'], verify=True)['status'] == 'VERIFIED'
    for record in service.list_audits(CASE):
        assert service.operate(record['id'], verify=True)['status'] == 'VERIFIED'
    assert [call[1] for call in FakeChain.calls] == [0, 1, 1]


def test_audit_api_uses_existing_local_access_pattern(saved):
    client = TestClient(app)
    response = client.post(f'/api/cases/{CASE}/audit/anchor')
    assert response.status_code == 200 and response.json()['status'] == 'ANCHORED'
    assert client.get(f'/api/cases/{CASE}/audit/verify').json()['status'] == 'VERIFIED'
    body = client.get(f'/api/cases/{CASE}/audit').text
    assert 'canonical_payload' not in body and SECRET not in body and 'Manis Singh' not in body
    assert client.post('/api/cases/CASE-MISSING/audit/anchor').status_code == 404
    assert client.post(f'/api/cases/{CASE}/audit/anchor?record_type=INVALID').status_code == 422


def test_screening_succeeds_when_chain_offline(monkeypatch):
    from test_document_routing import image_bytes, TEXT
    from app.routers import screening
    from app.services.aadhaar_service import extract_aadhaar
    from app.services.document_type_service import not_applicable_mrz
    monkeypatch.setattr(service, 'get_config', lambda: CONFIG)
    def offline(_): raise service.ChainUnavailable()
    monkeypatch.setattr(service, 'EVMClient', offline)
    monkeypatch.setattr(screening, 'extract_document', lambda *args: {'document': {'type': 'AADHAAR'}, 'fields': extract_aadhaar(TEXT, []), 'mrz': not_applicable_mrz(), 'confidence': 99})
    with TestClient(app) as client:
        response = client.post('/api/screen', files={'file': ('test.png', image_bytes(), 'image/png')})
        assert response.status_code == 200
        case_id = response.json()['case_id']
        assert client.get(f'/api/cases/{case_id}/audit').json()['records'][0]['status'] == 'CHAIN_UNAVAILABLE'


@pytest.mark.skipif(os.getenv('RUN_HARDHAT_INTEGRATION') != '1', reason='Run with the local deployed Hardhat configuration')
def test_local_hardhat_real_transaction(saved, monkeypatch):
    from dotenv import dotenv_values
    config = dotenv_values(Path(__file__).resolve().parents[1] / '.env.audit-local')
    real = replace(CONFIG, contract_address=config['BLOCKCHAIN_CONTRACT_ADDRESS'], private_key=config['BLOCKCHAIN_WRITER_PRIVATE_KEY'], hmac_key=config['BLOCKCHAIN_AUDIT_HMAC_KEY'])
    # Retrieve the actual class; saved fixture replaced the module binding.
    import importlib.util
    spec = importlib.util.spec_from_file_location('audit_evm_integration', Path(service.__file__))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(service, 'EVMClient', module.EVMClient)
    monkeypatch.setattr(service, 'get_config', lambda: real)
    # Unique key per integration run; do not collide with append-only earlier tests.
    import uuid
    unique = 'CASE-INTEGRATION-' + uuid.uuid4().hex[:20]
    case, path, factory = saved
    case['case_id'] = unique
    new_path = path.with_name(unique + '.json'); new_path.write_text(json.dumps(case), encoding='utf-8')
    with factory() as db:
        db.add(VerificationCase(case_id=unique, risk_score=0)); db.commit()
    record = service.prepare(unique)
    anchored = service.operate(record['id'])
    assert anchored['status'] == 'ANCHORED', anchored
    assert anchored['transaction_hash'] and anchored['block_number'] > 0
    assert service.operate(record['id'], verify=True)['status'] == 'VERIFIED'
    with factory() as db:
        db.query(VerificationCase).filter_by(case_id=unique).update({'risk_score': 99}); db.commit()
    assert service.operate(record['id'], verify=True)['status'] == 'TAMPER_DETECTED'
