# SentinelAI

**AI-Powered Identity Document Screening, Risk Assessment & Audit System**

SentinelAI is an end-to-end identity and travel-document verification prototype built for Smart India Hackathon (SIH). It combines OCR, MRZ validation, face verification, tamper analysis, synthetic registry/watchlist checks, automated risk scoring, officer review, persistent case management, and blockchain-backed audit integrity in a single workflow.

> Built as a decision-support prototype for document screening and border-security style workflows using synthetic demo data.

---

## Why SentinelAI?

Manual identity verification at checkpoints can be slow, inconsistent, and difficult to scale.

SentinelAI demonstrates how multiple verification signals can be combined into one structured screening pipeline:

```text id="2ucq6a"
Document + Selfie
        ↓
OCR / Field Extraction
        ↓
MRZ Validation
        ↓
Document & Tamper Checks
        ↓
Face Verification
        ↓
Registry / Watchlist Check
        ↓
Risk Assessment
        ↓
Officer Review
        ↓
Persistent Decision
        ↓
Blockchain Audit
```

---

## Core Features

* Passport / identity-document upload
* OCR-based field extraction
* MRZ extraction and ICAO-style validation
* MRZ check-digit verification
* Document quality and authenticity checks
* Tamper and forensic signal analysis
* Selfie-to-document face verification
* Synthetic identity registry lookup
* Blacklist / watchlist detection
* Duplicate / mismatch detection
* Automated risk scoring
* Human-readable risk reasons
* Secondary-inspection recommendation
* Officer approval / rejection / review workflow
* Officer remarks and decision persistence
* Case reopening and retrieval
* Blockchain-based audit anchoring
* Audit integrity verification
* Graceful fallback when optional services are unavailable
* React-based officer dashboard
* FastAPI REST backend
* SQLite persistence layer

---

## Tech Stack

### Backend

* Python
* FastAPI
* SQLAlchemy
* SQLite
* RapidOCR / ONNX Runtime
* Face verification pipeline
* Pytest

### Frontend

* React
* TypeScript
* Vite

### Blockchain

* Solidity
* Hardhat
* Local Ethereum development network
* Canonicalized audit hashes

---

## System Architecture

```text id="ypf997"
┌───────────────────────────────┐
│        React Frontend         │
│        Vite + TypeScript      │
└──────────────┬────────────────┘
               │ REST API
               ▼
┌───────────────────────────────┐
│        FastAPI Backend        │
├───────────────────────────────┤
│ OCR / Field Extraction        │
│ MRZ Validation                │
│ Document Validation           │
│ Tamper Analysis               │
│ Face Verification             │
│ Registry / Watchlist Checks   │
│ Risk Engine                   │
└──────────────┬────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐   ┌──────────────┐
│   SQLite    │   │   Hardhat    │
│ Persistence │   │ Audit Ledger │
└─────────────┘   └──────────────┘
```

---

## Verification Pipeline

A typical screening request performs the following:

1. Document upload
2. Image preprocessing and quality analysis
3. Document-type detection
4. OCR and field extraction
5. MRZ parsing and check-digit validation
6. Document consistency validation
7. Tamper / forensic analysis
8. Face comparison against selfie or camera input
9. Registry lookup
10. Watchlist / blacklist verification
11. Risk-score calculation
12. Recommendation generation
13. Case persistence
14. Officer decision
15. Blockchain audit anchoring

---

## Risk Assessment

SentinelAI combines multiple verification signals into a single backend risk result.

Example risk signals include:

| Signal                    | Effect                    |
| ------------------------- | ------------------------- |
| Valid MRZ                 | No additional risk        |
| Invalid MRZ / check digit | Risk increase             |
| OCR–MRZ mismatch          | Risk increase             |
| Expired document          | Risk increase             |
| Face mismatch             | Significant risk signal   |
| Document tampering        | Significant risk signal   |
| Watchlist hit             | High-priority risk signal |
| Database mismatch         | Risk increase             |

The final result includes:

```json id="g5rlmj"
{
  "score": 65,
  "level": "HIGH",
  "reasons": [
    "Face mismatch detected",
    "Watchlist match detected"
  ],
  "recommendation": "SECONDARY_INSPECTION"
}
```

The scoring logic is prototype logic intended for demonstration and is not a production immigration decision system.

---

## Human-in-the-Loop Decision Flow

SentinelAI does not treat automated screening as the final authority.

After analysis, an officer can review:

* extracted identity
* MRZ status
* face result
* tamper findings
* registry status
* watchlist result
* risk score
* risk reasons
* system recommendation

The officer can then record:

* `APPROVED`
* `REJECTED`
* `SECONDARY_INSPECTION`

Officer remarks and timestamps are persisted with the case.

---

## Blockchain Audit Layer

SentinelAI uses a local Hardhat-based blockchain audit layer to demonstrate tamper-evident case auditing.

Instead of storing sensitive case information directly on-chain, the system:

1. canonicalizes relevant case data
2. generates a cryptographic hash
3. anchors the hash through a smart contract
4. stores the transaction / audit metadata
5. verifies integrity by recomputing and comparing hashes

The screening pipeline continues operating even if the blockchain service is temporarily unavailable.

---

## Database

The application uses SQLite for prototype persistence.

Main entities include:

```text id="c41s4g"
verification_cases
persons
documents
watchlist
watchlist_checks
ocr_results
face_results
face_embeddings
tamper_results
blockchain_audits
```

The registry and watchlist data are synthetic demonstration records.

---

## Validation Status

The final integrated build has been validated with:

```text id="pmlnof"
Backend tests:            127 passed
Persistence/readiness:     19 passed
Contract tests:            12 passed
Real demo scenarios:        4 passed
E2E:                       Passed
Smoke tests:               Passed
Python compilation:        Passed
Frontend build:            Passed
Blockchain anchoring:      Passed
Audit integrity check:     Passed
```

The remaining hardware-dependent verification is physical webcam interaction in the target browser/environment.

---

## Demo Scenarios

### Clean Traveller

Expected behavior:

```text id="s5eiev"
MRZ: VALID
Face: MATCH
Watchlist: CLEAR
Tamper: CLEAR
Risk: LOW
Recommendation: APPROVAL / normal review
```

### Face Mismatch

Expected behavior:

```text id="6nuk1x"
Face: MISMATCH
Risk: Increased
Reason: Face verification failure
Recommendation: Additional review
```

### Watchlist Match

Expected behavior:

```text id="3jdw0t"
Watchlist: MATCH
Risk: HIGH
Priority: HIGH
Recommendation: SECONDARY INSPECTION
```

### Invalid / Tampered Document

Expected behavior:

```text id="x89on1"
Validation or Tamper Check: FAILED
Risk: Increased
Reason: Visible in risk breakdown
Recommendation: Manual review
```

---

## Quick Start

### 1. Clone

```powershell id="mzvgqe"
git clone https://github.com/Ashwin-rathinakumar/SenitalAI.git
cd SenitalAI
```

### 2. Start Hardhat

```powershell id="euu8l8"
.\scripts\start-hardhat.ps1
```

### 3. Deploy Contract and Start Backend

In a new terminal:

```powershell id="9n6jhz"
.\scripts\deploy-local.ps1
.\scripts\start-backend.ps1
```

### 4. Start Frontend

In another terminal:

```powershell id="nwy8y2"
.\scripts\start-frontend.ps1
```

### 5. Verify System Health

```powershell id="ivn7y8"
python scripts/check-demo.py --warmup
```

Expected output:

```text id="t7tzkn"
Backend: OK
Database: OK
OCR: OK
Face Service: OK
Blockchain RPC: OK
Audit Contract: OK
Frontend: OK
Application status: READY
```

### 6. Open the Application

```text id="24lml6"
http://localhost:5173
```

API documentation:

```text id="wuncts"
http://127.0.0.1:8000/docs
```

---

## Project Structure

```text id="ee6gai"
SentinelAI/
│
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── main.py
│   │
│   ├── tests/
│   └── requirements.txt
│
├── blockchain/
│   ├── contracts/
│   ├── scripts/
│   └── hardhat.config.js
│
├── frontend/
│   ├── src/
│   └── package.json
│
├── scripts/
│   ├── start-hardhat.ps1
│   ├── deploy-local.ps1
│   ├── start-backend.ps1
│   ├── start-frontend.ps1
│   ├── check-demo.py
│   └── verify-final-demo.py
│
├── INTEGRATION_REPORT.md
└── README.md
```

---

## Synthetic Demo Registry

The project intentionally uses synthetic identities and watchlist records for safe, reproducible testing.

It is **not connected to any live government, immigration, passport, law-enforcement, or border-security database**.

This design keeps the prototype demonstrable without exposing or depending on sensitive real-world datasets.

---

## Security & Privacy

Do not use this repository with:

* real passports
* real biometric data
* sensitive identity information
* production credentials
* confidential government records

A production deployment would require additional controls such as:

* authentication and authorization
* encrypted storage and transport
* secrets management
* access logging
* data-retention controls
* secure biometric handling
* regulatory and privacy compliance
* hardened infrastructure

---

## Limitations

* Registry and watchlist data are synthetic.
* Blockchain currently uses a local Hardhat environment.
* Hardhat chain history resets when the local node is restarted.
* Risk scoring is demonstration logic, not a certified decision model.
* Physical webcam behavior depends on browser and device permissions.
* The prototype is not connected to real government databases.

---

## Disclaimer

SentinelAI is a research, educational, and hackathon prototype.

It must not be used as the sole basis for immigration, border-control, law-enforcement, identity, or other high-impact decisions.

Automated verification outputs are intended to support human review, not replace it.

---

## Project Status

**Prototype: Complete**

**Integration: Validated**

**Local Demo: Ready**

**Public Deployment: Optional / Future Work**

---

## SentinelAI

**Document Verification → Identity Validation → Risk Assessment → Human Review → Persistent Decision → Blockchain Audit**
