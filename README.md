# SentinelAI

SentinelAI is an explainable SIH hackathon prototype for screening **synthetic/demo identity documents**. It is an officer decision-support workflow: the application surfaces evidence and recommends review; it does not declare that a document is definitively forged.

## Architecture

The repository preserves the existing React + Vite frontend and FastAPI backend. A screening request moves through upload validation and storage, document quality analysis, local OCR, identity-field extraction, ICAO passport MRZ parsing and check-digit validation, OCR/MRZ consistency checks, deterministic document validation, prototype forensic heuristics, optional 1:1 selfie comparison, a synthetic database lookup, transparent risk scoring, and JSON-backed case/audit persistence.

OCR prefers RapidOCR when installed and falls back to local Tesseract OCR. The fallback returns OCR text, confidence values, and bounding boxes. No uploaded document is sent to an external service.

## Local setup

From the repository root:

```bash


```

Tesseract must also be installed on the host for the fallback (`tesseract-ocr` on Debian/Ubuntu). In a second terminal:

```bash
cd frontend
npm ci
npm run dev
```

The frontend defaults to `http://127.0.0.1:8000`; set `VITE_API_URL` when the API runs elsewhere.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Backend health check |
| POST | `/api/upload` | Existing validated upload and quality analysis |
| POST | `/api/screen` | Complete screening pipeline; accepts document and optional selfie multipart files |
| GET | `/api/documents/{document_number}/status` | Synthetic database lookup |
| GET | `/api/cases` | Masked case history |
| GET | `/api/cases/{case_id}` | Full persisted case record |

`POST /api/screen` returns quality, OCR, extracted fields, MRZ details and check results, validation reason codes, tamper indicators, face result, simulated database result, risk score, recommendation, and case ID.

## Risk scoring

The score is deliberately transparent. MRZ failure contributes 20 points, OCR/MRZ mismatch 20, forensic anomaly 20, face mismatch 20, a synthetic blacklist match 30, expiry 10, and low OCR confidence 5. The score is capped at 100. Scores from 0–29 are **LOW RISK**, 30–59 are **MEDIUM RISK**, and 60–100 are **HIGH PRIORITY REVIEW**.

## Synthetic demo data

The simulated database contains `A1234567` as valid, `B7654321` as valid but blacklisted, `C2468135` as expired, and `D1357902` as suspicious. These are synthetic values only. The project does not connect to government databases and must not be tested with real passports, Aadhaar cards, driving licences, or other real identity documents.

## Verification

The repository includes `test_backend.py` for route, MRZ, and database smoke checks and `test_e2e.py` for a synthetic multipart screening flow. The production frontend build is verified with `npm run build`.

## Limitations and privacy

This is a locally runnable prototype. Tesseract is not a production-grade identity OCR system, the optional face comparison is a 1:1 pixel-similarity prototype rather than a trained biometric embedding model, and forensic analysis produces review signals rather than forensic certainty. Case JSON files are stored under `backend/data/sessions` when created. Use synthetic data and remove generated uploads and cases before sharing the repository.
