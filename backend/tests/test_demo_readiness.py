"""Readiness must distinguish optional outages from essential database failure."""
import sys
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import app
from app import database
from app.services import face_service, ocr_engine, blockchain_service


def test_ready_without_initialization_side_effects(monkeypatch):
    monkeypatch.setattr(ocr_engine, '_engine', object())
    monkeypatch.setattr(face_service, '_using_insightface', True)
    monkeypatch.setattr(blockchain_service, 'network_status', lambda: {'enabled': True, 'rpc_reachable': True, 'contract_reachable': True})
    result = TestClient(app).get('/health/readiness').json()
    assert result['status'] == 'READY'
    assert result['database'] == result['ocr'] == result['face'] == 'OK'


def test_optional_chain_outage_is_degraded(monkeypatch):
    monkeypatch.setattr(ocr_engine, '_engine', object())
    monkeypatch.setattr(face_service, '_using_insightface', True)
    monkeypatch.setattr(blockchain_service, 'network_status', lambda: {'enabled': True, 'rpc_reachable': False, 'contract_reachable': False})
    assert TestClient(app).get('/health/readiness').json()['status'] == 'DEGRADED_BUT_FUNCTIONAL'


def test_database_failure_is_not_ready(monkeypatch):
    @contextmanager
    def unavailable():
        raise RuntimeError('test database unavailable')
        yield
    monkeypatch.setattr(database, 'SessionLocal', unavailable)
    monkeypatch.setattr(blockchain_service, 'network_status', lambda: {'enabled': False, 'rpc_reachable': False, 'contract_reachable': False})
    result = TestClient(app).get('/health/readiness').json()
    assert result['status'] == 'NOT_READY'
    assert result['database'] == 'UNAVAILABLE'
