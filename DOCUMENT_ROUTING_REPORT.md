# Document-aware screening fix

## Baseline

- `python -m pytest backend/tests -q`: 20 passed in 103.98 seconds. One sandbox-related pytest cache warning.
- `python test_backend.py`: `BACKEND_SMOKE_OK`.
- `python test_e2e.py`: HTTP 200 and `E2E_OK`.
- `npm run build` in `frontend`: passed. Initial Vite `spawn EPERM` was a sandbox restriction; the permitted retry passed.

## Routing and extraction

The FastAPI entry point remains `backend/app/main.py`, and screening remains `/api/screen` in `backend/app/routers/screening.py`. The upload-only route remains a quality-analysis endpoint. Screening reads OCR, classifies its contents, then routes extraction. A user-selected type is a hint, not authority to run passport checks.

- PASSPORT: existing visual extraction, MRZ parsing/check digits, expiry, biometrics, database and risk.
- AADHAAR: label/pattern extraction, QR detection, biometrics, database and risk. MRZ and expiry are explicitly `NOT_APPLICABLE`.
- VISA / NATIONAL_ID: their existing visual field extractors, followed by manual verification. Visa expiry applies when extracted. This task does not implement issuer-specific visa or national-ID MRZ validation; TD3 is not imposed on them.
- UNKNOWN, including unreadable OCR: no passport extraction or passport penalties; manual verification.

Classification reports deterministic evidence signals rather than invented probabilities. Aadhaar uses identifying text or the combination of Government of India and a 12-digit identifier. Passport MRZ candidates require a header, name separator, lengths and fixed-position field structure. Ordinary disclaimer sentences cannot be padded into a passport MRZ. Existing OCR O/0 country-code confusion remains supported.

Aadhaar names come from a label or plausible nearby line preceding DOB/YOB, with disclaimer/header exclusions. English names on bilingual cards are supported. DOB must parse to a real calendar date; YOB is retained without inventing a full date. Gender requires a complete allowed English word. Identifiers require exactly 12 digits; conflicting candidates remain missing. Country is India, not an assertion of Indian citizenship. A general case-boundary rule recovers OCR-merged names such as `ManisSingh`.

## Privacy and database

The complete normalized identifier is used transiently for local matching. OCR text, regions, fields and returned database data are masked before API serialization and case JSON persistence. The verification-case identifier is stored as SHA-256 with a `SHA256` prefix. SQLite documents already have a document-type column; no tables or seeded records were deleted. Identifier column declarations now accommodate hashes. SQLite does not enforce VARCHAR length, so existing databases need no destructive migration.

Lookup supports existing normalized or space-separated identifiers and SHA-256 tokens, filters document type, and retains local watchlist/person checks. A watchlist-only identifier hit is also reported even without a document row.

Important limits: hashing is not encryption and low-entropy identifiers remain susceptible to guessing. Original uploaded and preprocessed images still follow the existing local retention behavior and may visibly contain the identifier. Old saved cases are not retroactively redacted.

## Risk and forensic semantics

Risk reasons contain applicable evidence only. An explicit checks list reports passport MRZ, checksum, VIZ/MRZ and expiry applicability, with zero points for Aadhaar. Required fields are document-specific. Aadhaar requires name and identifier; DOB/YOB and gender are extracted where available.

Forensics reports `FORENSIC_SIGNAL`, `INCONCLUSIVE`, possible recompression, metadata anomalies, and `content_tamper_detected: false`. Current image heuristics cannot establish content tampering and contribute no fraud points. MRZ failures and visual conflicts retain their direct passport risk signals without being counted again as tampering. No ML confidence is fabricated.

QR detection returns found-but-not-verified or not found, with an explicit unavailable result on detector failure. Secure QR cryptographic verification is not implemented. The application does not claim UIDAI authentication or that an Aadhaar is genuine.

## Biometrics and existing-test correction

InsightFace / ArcFace and the 0.45 match threshold are retained. The pre-existing Haar/pixel fallback invented portrait regions for cartoons or blank images; it was removed. Unavailable ArcFace returns `UNABLE_TO_VERIFY`, and no face remains a failed detection. Both portrait and selfie now pass the existing blur, darkness, size and face-count gates. Duplicate embedding extraction also respects quality gates.

Two existing biometric tests used cartoon fixtures and expected fabricated detections. Their input fixtures now use a real, bundled public-domain photograph; assertions were retained and the match test strengthened to require ArcFace and a match. The other 18 original tests were not weakened. Real same-person and different-person comparisons on an Aadhaar-style specimen also run, alongside controlled 512-dimensional embedding tests.

## Regression evidence

No original failing Aadhaar image was present among the supplied fixtures. Tests reproduce its equivalent text in OCR tokens and a rendered image, then submit the rendered image through the real HTTP/OCR pipeline with the deliberately wrong `passport` hint.

Observed result: AADHAAR; Manis Singh; 2002-01-16; MALE; `XXXX XXXX 9260`; MRZ and expiry `NOT_APPLICABLE`; QR not found; risk 0 with secondary/manual verification. The text-only test provides no selfie and correctly reports biometrics not provided. Separate specimen tests use real photographs with ArcFace and assert same-person match and different-person mismatch. This does not substitute for retesting the user's original photo and selfie.

The additional suite covers classification, routed MRZ invocation/non-invocation, extraction, masking and saved-case responses, DOB/YOB, bilingual English fields, invalid dates, disclaimer rejection, gender rejection, risk applicability, recompression, QR semantics, UNKNOWN/failed OCR, and real and controlled biometric comparisons.

## Files

Created:

- `backend/app/services/document_type_service.py`
- `backend/app/services/aadhaar_service.py`
- `backend/tests/test_document_routing.py`
- `backend/tests/demo_samples/astronaut_public_domain.png` — NASA Eileen Collins photograph, copied from installed scikit-image sample data.
- `backend/tests/demo_samples/grace_hopper_public_domain.jpg` — U.S. Navy Grace Hopper photograph, copied from installed Matplotlib sample data.
- `DOCUMENT_ROUTING_REPORT.md`

Modified:

- `backend/app/config.py`
- `backend/app/models.py`
- `backend/app/routers/screening.py`
- `backend/app/schemas/screening.py`
- `backend/app/services/ocr_service.py`
- `backend/app/services/mrz_service.py`
- `backend/app/services/ocr_normalize.py`
- `backend/app/services/field_extractor.py`
- `backend/app/services/screening_services.py`
- `backend/app/services/face_service.py`
- `backend/tests/test_screening_pipeline.py`
- `frontend/src/types/index.ts`
- `frontend/src/components/DocumentTypeSelector.tsx`
- `frontend/src/pages/NewScreeningPage.tsx`

Test execution also creates ordinary upload, preprocessing, case and database audit records. These are not replacement source fixtures or seeded production identities.

## Remaining limits

The registry/watchlist is the existing local prototype database with seeded demonstration records, not UIDAI or Interpol. The document classifier is rule-based, multilingual-only OCR remains limited, and difficult layouts may require manual review. MRV/issuer-specific national-ID checks and Secure QR authentication remain unsupported. Original photographs, a real webcam session and browser interaction were not supplied/tested; the frontend is checked by its TypeScript and production build. Image heuristics are inconclusive. ArcFace uses the installed pretrained model; no custom model was trained. No blockchain, LLM or ResNet50 was added.

## Run and test (PowerShell)

Final verification: **52 tests passed** (20 existing, 32 added), in 143.47 seconds. Four upstream InsightFace/scikit-image deprecation warnings remain. Backend smoke returned `BACKEND_SMOKE_OK`; E2E returned HTTP 200 and `E2E_OK`; frontend TypeScript/production build passed (1,825 modules). The real-OCR Aadhaar regression and real ArcFace same/different-person tests are part of this passing suite.

From the project directory:

```powershell
Set-Location 'C:\Users\Ashwin Rathinakumar\Downloads\SenitalAI_complete_modified_project\SenitalAI'
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
Set-Location 'C:\Users\Ashwin Rathinakumar\Downloads\SenitalAI_complete_modified_project\SenitalAI\frontend'
npm install
npm run dev -- --host 127.0.0.1
```

Verification:

```powershell
Set-Location 'C:\Users\Ashwin Rathinakumar\Downloads\SenitalAI_complete_modified_project\SenitalAI'
python -m pytest backend/tests -q -p no:cacheprovider
python test_backend.py
python test_e2e.py
python -m pytest backend/tests/test_document_routing.py -v -p no:cacheprovider -k 'real_ocr or real_arcface'
Set-Location frontend
npm run build
```

The regression image renderer uses Windows Arial. Face tests require the pretrained ArcFace model to be available; they do not silently replace it with a pixel comparator.
