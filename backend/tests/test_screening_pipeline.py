"""Comprehensive test suite for SentinelAI identity screening pipeline."""

from pathlib import Path
import sys
import numpy as np
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Initialize database tables and seed data before importing app
from app.database import init_db, SessionLocal
init_db(seed=True)

from app.main import app
from app.models import Person, Document, Watchlist, FaceEmbedding, VerificationCase
from app.services.mrz_service import extract_mrz
from app.services.screening_services import database_lookup, validate_document, calculate_risk
from app.services.face_service import (
    verify_faces,
    detect_faces,
    check_face_quality,
    store_embedding,
    search_duplicates,
    cosine_similarity,
)
from app.schemas.screening import FaceResult, ForensicResult, DatabaseResult, ValidationResult

client = TestClient(app, raise_server_exceptions=True)
SAMPLES_DIR = Path(__file__).resolve().parent / "demo_samples"


# ---------------------------------------------------------------------------
# 1. Health & Home Endpoints
# ---------------------------------------------------------------------------
def test_system_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_home_endpoint():
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "SentinelAI" in data["message"]


# ---------------------------------------------------------------------------
# 2. ICAO 9303 MRZ Engine & Check Digits
# ---------------------------------------------------------------------------
def test_mrz_td3_check_digits_valid():
    lines = [
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
    ]
    res = extract_mrz("\n".join(lines), lines)
    assert res["mrz_detected"] is True
    assert res["mrz_valid"] is True
    assert res["checks"]["document_number"] is True
    assert res["checks"]["date_of_birth"] is True
    assert res["checks"]["date_of_expiry"] is True
    assert res["checks"]["composite"] is True
    assert res["passport_number"]["normalized"] == "L898902C"


def test_mrz_td3_tampered_check_digit():
    lines = [
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C<9UTO6908061F9406236ZE184226B<<<<<14",
    ]
    res = extract_mrz("\n".join(lines), lines)
    assert res["mrz_detected"] is True
    assert res["mrz_valid"] is False
    assert res["checks"]["document_number"] is False


def test_mrz_td1_national_id():
    lines = [
        "I<UTO12345678<8<<<<<<<<<<<<<<<",
        "7408122F1204159UTO<<<<<<<<<<<6",
        "ERIKSSON<<ANNA<MARIA<<<<<<<<<<",
    ]
    res = extract_mrz("\n".join(lines), lines)
    assert res["mrz_detected"] is True
    assert res["format"] == "TD1"
    assert res["checks"]["document_number"] is True


def test_mrz_td2_visa():
    lines = [
        "V<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<",
        "L898902C<3UTO6908061F9406236<<<<<<<4",
    ]
    res = extract_mrz("\n".join(lines), lines)
    assert res["mrz_detected"] is True
    assert res["format"] == "TD2"


# ---------------------------------------------------------------------------
# 3. Database Layer & Watchlist Hardening
# ---------------------------------------------------------------------------
def test_database_watchlist_lookup():
    rec = database_lookup("B7654321")
    assert rec.found is True
    assert rec.blacklisted is True
    assert rec.status == "BLACKLISTED"


def test_database_active_lookup():
    rec = database_lookup("A12345678")
    assert rec.found is True
    assert rec.blacklisted is False
    assert rec.status == "FOUND"
    assert rec.record["full_name"] == "MARIA GARCIA"


def test_database_expired_lookup():
    rec = database_lookup("C2468135")
    assert rec.found is True
    assert rec.status == "EXPIRED"


def test_database_unable_to_check_when_null():
    rec = database_lookup(None)
    assert rec.found is False
    assert rec.status == "UNABLE_TO_CHECK"


def test_database_person_models_and_seed():
    db = SessionLocal()
    try:
        persons_count = db.query(Person).count()
        docs_count = db.query(Document).count()
        wl_count = db.query(Watchlist).count()
        assert persons_count >= 10
        assert docs_count >= 10
        assert wl_count >= 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Biometric Face Verification & Quality
# ---------------------------------------------------------------------------
def test_face_verification_no_selfie():
    sample_file = SAMPLES_DIR / "astronaut_public_domain.png"
    with open(sample_file, "rb") as f:
        doc_bytes = f.read()
    res = verify_faces(doc_bytes, None)
    assert res.status == "NOT_PROVIDED"
    assert res.face_detected_document is True
    assert res.face_detected_selfie is False


def test_face_verification_same_image_match():
    sample_file = SAMPLES_DIR / "astronaut_public_domain.png"
    selfie_file = SAMPLES_DIR / "astronaut_public_domain.png"
    with open(sample_file, "rb") as f1, open(selfie_file, "rb") as f2:
        doc_bytes = f1.read()
        selfie_bytes = f2.read()
    res = verify_faces(doc_bytes, selfie_bytes)
    assert res.face_detected_document is True
    assert res.face_detected_selfie is True
    assert res.similarity is not None
    assert res.model == "ArcFace"
    assert res.match is True


def test_face_quality_check():
    # Empty image should report NO_FACE_DETECTED
    empty_img = np.zeros((200, 200, 3), dtype=np.uint8)
    q = check_face_quality(empty_img, [])
    assert q.quality_pass is False
    assert q.no_face is True


# ---------------------------------------------------------------------------
# 5. Duplicate Identity Detection
# ---------------------------------------------------------------------------
def test_duplicate_identity_detection():
    # Create synthetic embedding
    dummy_emb = np.random.randn(512).astype(np.float32)
    norm = np.linalg.norm(dummy_emb)
    dummy_emb = dummy_emb / norm

    # Store embedding for Person #1
    store_embedding(person_id=1, embedding=dummy_emb, model_name="ArcFace_Test")

    # Search with almost identical embedding
    query_emb = dummy_emb + np.random.normal(0, 0.01, 512).astype(np.float32)
    query_emb = query_emb / np.linalg.norm(query_emb)

    matches = search_duplicates(query_emb, threshold=0.7)
    assert len(matches) > 0
    assert matches[0]["person_id"] == 1
    assert matches[0]["similarity"] > 0.90


# ---------------------------------------------------------------------------
# 6. VIZ vs MRZ Reconciliation
# ---------------------------------------------------------------------------
def test_viz_mrz_name_reconciliation():
    fields = {
        "full_name": {"raw": "ANNA MARIA ERIKSSON", "normalized": "ANNA MARIA ERIKSSON"},
        "passport_number": {"raw": "L898902C", "normalized": "L898902C"},
        "date_of_expiry": {"raw": "1994-06-23", "normalized": "1994-06-23"},
        "nationality": {"raw": "UTO", "normalized": "UTO"},
    }
    mrz = {
        "mrz_detected": True,
        "mrz_valid": True,
        "full_name": {"normalized": "ANNA MARIA ERIKSSON"},
        "passport_number": {"normalized": "L898902C"},
        "date_of_expiry": {"normalized": "1994-06-23"},
        "nationality": {"normalized": "UTO"},
    }
    val = validate_document(fields, mrz)
    assert val.consistency["full_name"] == "MATCH"
    assert val.consistency["passport_number"] == "MATCH"


# ---------------------------------------------------------------------------
# 7. Risk Engine Scoring & CRITICAL Tier
# ---------------------------------------------------------------------------
def test_risk_engine_critical_tier():
    quality = {"ocr_readiness": 90}
    ocr = {"confidence": 95}
    mrz = {"mrz_detected": True, "mrz_valid": True}
    validation = ValidationResult(valid=True, status="VALID", reason_codes=[], messages=[])
    tamper = ForensicResult(tamper_risk="LOW", score=5, indicators=[])
    face = FaceResult(status="MATCH", match=True, similarity=0.88)
    
    # Blacklisted record must trigger CRITICAL tier
    db_res = DatabaseResult(found=True, status="BLACKLISTED", blacklisted=True)
    risk = calculate_risk(quality, ocr, mrz, validation, tamper, face, db_res)
    assert risk.risk_level == "CRITICAL"
    assert risk.recommendation == "REJECT_OR_INTERCEPT"


# ---------------------------------------------------------------------------
# 8. Full End-to-End Screening Pipeline
# ---------------------------------------------------------------------------
def test_screen_case1_valid_passport():
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
            data={"document_type": "passport", "officer_id": "TEST-OFFICER"},
        )
    assert resp.status_code == 200
    res = resp.json()
    assert res["case_id"].startswith("CASE-")
    assert res["mrz"]["mrz_valid"] is True
    assert res["quality"]["ocr_readiness"] > 60


def test_screen_case4_watchlist_triggers_high_risk():
    sample_file = SAMPLES_DIR / "case4_watchlist_blacklisted.png"
    assert sample_file.exists()

    with open(sample_file, "rb") as doc_f:
        resp = client.post(
            "/api/screen",
            files={"file": ("case4.png", doc_f, "image/png")},
            data={"document_type": "passport"},
        )
    assert resp.status_code == 200
    res = resp.json()
    assert res["database"]["blacklisted"] is True
    assert res["risk"]["risk_score"] >= 35
    assert res["risk"]["risk_level"] in ["HIGH PRIORITY REVIEW", "CRITICAL"]


def test_officer_decision_lifecycle():
    sample_file = SAMPLES_DIR / "case1_valid_passport.png"
    with open(sample_file, "rb") as doc_f:
        screen_resp = client.post(
            "/api/screen",
            files={"file": ("case_decision_test.png", doc_f, "image/png")},
            data={"document_type": "passport"},
        )
    case_id = screen_resp.json()["case_id"]

    dec_resp = client.post(
        f"/api/cases/{case_id}/decision",
        json={
            "decision": "APPROVE",
            "notes": "Physical security features and holograms inspected and confirmed.",
            "officer_id": "INSPECTOR-102",
        },
    )
    assert dec_resp.status_code == 200
    saved_case = dec_resp.json()["case"]
    assert saved_case["officer_decision"]["decision"] == "APPROVE"
    assert saved_case["officer_decision"]["officer_id"] == "INSPECTOR-102"

    get_resp = client.get(f"/api/cases/{case_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["case"]["officer_decision"]["decision"] == "APPROVE"
