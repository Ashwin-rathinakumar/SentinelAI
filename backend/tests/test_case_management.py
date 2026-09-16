"""Database case API tests, isolated from the development database."""

from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, get_db
from app.main import app
from app.models import (
    Document,
    FaceResult as FaceResultModel,
    OCRResult as OCRResultModel,
    ScreeningCase,
    TamperResult as TamperResultModel,
    Traveller,
    WatchlistCheck as WatchlistCheckModel,
)
from app.routers.cases import find_database_case

SAMPLES_DIR = Path(__file__).resolve().parent / "demo_samples"


@pytest.fixture()
def db_session_and_client(tmp_path):
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'case-api.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    factory = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        with factory() as db:
            yield db, test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def client(db_session_and_client):
    _, test_client = db_session_and_client
    return test_client


def test_create_list_and_retrieve_case_with_ai_results(client):
    payload = {
        "case_id": "CASE-20260915-DB000001",
        "traveller": {"full_name": "TEST TRAVELLER", "date_of_birth": "1990-01-01", "nationality": "IND"},
        "document": {"document_number": "TEST0001", "document_type": "passport"},
        "extracted_document_number": "TEST0001",
        "ocr_result": {"status": "COMPLETED", "confidence": 97.2, "extracted_fields": {"full_name": "TEST TRAVELLER"}},
        "face_result": {"status": "MATCH", "similarity": 0.91, "match": True, "model_name": "ArcFace", "threshold": 0.45},
        "tamper_result": {"status": "CLEAR", "detected": False, "score": 3.0},
        "watchlist_checks": [{"matched": False, "match_score": 0.0, "details": {"source": "local"}}],
    }
    created = client.post("/api/cases", json=payload)
    assert created.status_code == 201, created.text
    case = created.json()["case"]
    assert case["case_id"] == payload["case_id"]
    assert case["traveller"]["full_name"] == "TEST TRAVELLER"
    assert case["ocr_result"]["extracted_fields"]["full_name"] == "TEST TRAVELLER"
    assert case["face_result"]["match"] is True
    assert case["tamper_result"]["detected"] is False
    assert case["watchlist_checks"][0]["matched"] is False

    retrieved = client.get("/api/cases/CASE-20260915-DB000001")
    assert retrieved.status_code == 200
    assert retrieved.json()["case"] == case
    listed = client.get("/api/cases")
    assert listed.status_code == 200
    assert any(item["case_id"] == case["case_id"] for item in listed.json()["cases"])


def test_case_id_conflict_and_missing_case(client):
    payload = {"case_id": "CASE-20260915-DB000002"}
    assert client.post("/api/cases", json=payload).status_code == 201
    assert client.post("/api/cases", json=payload).status_code == 409
    assert client.get("/api/cases/CASE-NOT-FOUND").status_code == 404


def test_document_requires_traveller(client):
    response = client.post("/api/cases", json={"document": {"document_number": "ORPHAN"}})
    assert response.status_code == 422


def test_screen_pipeline_automatically_persists_to_database(db_session_and_client):
    db, client = db_session_and_client
    sample_file = SAMPLES_DIR / "case1_valid_passport.png"
    selfie_file = SAMPLES_DIR / "case1_selfie_match.png"
    assert sample_file.exists()

    with open(sample_file, "rb") as doc_f, open(selfie_file, "rb") as selfie_f:
        resp = client.post(
            "/api/screen",
            files={
                "file": ("case1.png", doc_f, "image/png"),
                "selfie": ("selfie.png", selfie_f, "image/png"),
            },
            data={"document_type": "passport", "officer_id": "INSPECTOR-CASE-DB"},
        )
    assert resp.status_code == 200
    res = resp.json()
    case_id = res["case_id"]
    assert case_id.startswith("CASE-")

    # Verify directly from database models
    db_case = find_database_case(db, case_id)
    assert db_case is not None
    assert db_case.case_id == case_id
    assert db_case.document is not None
    assert db_case.traveller is not None
    assert db_case.ocr_result is not None
    assert db_case.ocr_result.status in ("SUCCESS", "LOW_CONFIDENCE", "COMPLETED")
    assert db_case.face_result is not None
    assert db_case.face_result.status in ("MATCH", "MISMATCH", "FAILED")
    assert db_case.tamper_result is not None
    assert db_case.tamper_result.score is not None
    assert len(db_case.watchlist_checks) > 0


def test_screen_pipeline_idempotency(db_session_and_client):
    db, _ = db_session_and_client
    from app.services.case_persistence_service import persist_screening_case
    from app.schemas.screening import FaceResult, ForensicResult, DatabaseResult, RiskResult

    test_case_id = "CASE-20260915-IDEMP001"
    face = FaceResult(status="MATCH", similarity=0.88, match=True, model="ArcFace", threshold=0.45)
    tamper = ForensicResult(tamper_risk="LOW", score=2.0, indicators=[])
    database = DatabaseResult(found=True, status="VALID", blacklisted=False)
    risk = RiskResult(risk_score=10, risk_level="LOW RISK", recommendation="PROCEED")

    # First persistence
    persist_screening_case(
        db,
        case_id=test_case_id,
        file_id="idemp001",
        document_type="passport",
        doc_number="P998877",
        extracted_fields={"full_name": {"normalized": "JANE DOE"}},
        mrz={"full_name": {"normalized": "JANE DOE"}, "mrz_valid": True},
        quality={"ocr_readiness": 95},
        ocr={"status": "SUCCESS", "confidence": 98.0, "raw_text": "JANE DOE"},
        tamper=tamper,
        face=face,
        database=database,
        risk=risk,
    )

    # Second persistence with same case_id
    persist_screening_case(
        db,
        case_id=test_case_id,
        file_id="idemp001",
        document_type="passport",
        doc_number="P998877",
        extracted_fields={"full_name": {"normalized": "JANE DOE"}},
        mrz={"full_name": {"normalized": "JANE DOE"}, "mrz_valid": True},
        quality={"ocr_readiness": 95},
        ocr={"status": "SUCCESS", "confidence": 99.0, "raw_text": "JANE DOE"},
        tamper=tamper,
        face=face,
        database=database,
        risk=risk,
    )

    # Verify no duplicate rows
    cases = db.scalars(select(ScreeningCase).where(ScreeningCase.case_id == test_case_id)).all()
    assert len(cases) == 1
    ocr_rows = db.scalars(select(OCRResultModel).where(OCRResultModel.case_id == test_case_id)).all()
    assert len(ocr_rows) == 1
    face_rows = db.scalars(select(FaceResultModel).where(FaceResultModel.case_id == test_case_id)).all()
    assert len(face_rows) == 1
    tamper_rows = db.scalars(select(TamperResultModel).where(TamperResultModel.case_id == test_case_id)).all()
    assert len(tamper_rows) == 1
    wl_rows = db.scalars(select(WatchlistCheckModel).where(WatchlistCheckModel.case_id == test_case_id)).all()
    assert len(wl_rows) == 1


def test_screen_pipeline_missing_optional_data_safe(db_session_and_client):
    db, client = db_session_and_client
    sample_file = SAMPLES_DIR / "case1_valid_passport.png"
    assert sample_file.exists()

    with open(sample_file, "rb") as doc_f:
        resp = client.post(
            "/api/screen",
            files={"file": ("case1_no_selfie.png", doc_f, "image/png")},
            data={"document_type": "passport"},
        )
    assert resp.status_code == 200
    case_id = resp.json()["case_id"]

    db_case = find_database_case(db, case_id)
    assert db_case is not None
    assert db_case.face_result is not None
    assert db_case.face_result.status == "NOT_PROVIDED"
    assert db_case.face_result.match is None
