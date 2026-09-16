# Phase 3: blockchain audit implementation report

Delivered a working local prototype using a real Hardhat EVM and an append-only Solidity contract. The blockchain does NOT verify the authenticity of an identity. It preserves cryptographic evidence that selected saved screening results have not changed since anchoring. No mainnet deployment was performed.

## Baseline and final validation

Before blockchain changes, the existing backend suite passed **67 tests**, with 4 warnings. `python test_backend.py` returned `BACKEND_SMOKE_OK`; `python test_e2e.py` returned HTTP 200 and `E2E_OK`; the frontend production build passed.

Final validation:

- Backend including actual local-Hardhat integration: **92 passed**, 5 dependency deprecation warnings, 85.91 seconds. All original 67 tests remain passing.
- Solidity contract suite: **12 passed**.
- Backend smoke: **BACKEND_SMOKE_OK**, including the four new audit routes.
- E2E: **HTTP 200, E2E_OK**.
- Frontend: **production build passed**, 1,827 modules transformed.

The added tests cover deterministic canonicalization/HMAC/case keys; nonfinite values and weak keys; exclusion of raw OCR, paths, crops and embeddings; disabled/unavailable and wrong-contract handling; API access consistent with the existing local application; real and mocked anchoring; metadata persistence; idempotency, concurrent retry and confirmation timeout recovery; JSON/SQL/snapshot tampering; refusal to rebase edited pending records; independent officer versions; and screening success during chain outage. An explicit captured-call privacy test checks the provided name, identity numbers, DOB and image/embedding values cannot appear in contract arguments. The integration test submits a real signed transaction, verifies against the deployed contract and detects a SQL modification.

## Real local deployment and demonstration

Network: Hardhat localhost, **chain ID 31337**.

Contract: `0x5FbDB2315678afecb367f032d93F642f64180aa3`.

Deployment transaction: `0x1713be5c6be81936b381e5452c7e3286ce85aeadf6fe64d32c9abb5cc8d2b7fa`, block **1**.

A new real Aadhaar demo case, `CASE-20260914-635692F4`, completed over HTTP 200 with name/DOB extracted, MRZ and expiry `NOT_APPLICABLE`, risk **0**, and `SECONDARY_MANUAL_VERIFICATION`. This run supplied the document without a selfie; it does not claim a newly measured face-match score. Existing real ArcFace regression tests remained passing.

Screening anchor transaction: `0xfd60b16613a2b0f54b59814102b1bd860f51548df4bd1b373a29fa431b3f87a5`, block **5**, timestamp **2026-09-14T18:31:07+00:00**.

The live API returned `VERIFIED` with `digest_match: true`. The development utility changed that new case's SQLite risk score from 0 to 77. Verification returned `TAMPER_DETECTED` with `digest_match: false`. Restoring 0 returned `VERIFIED` again. No pre-existing user case was edited for this demonstration.

The subsequent officer disposition received its own `OFFICER_DECISION v1` transaction: `0x72bcda59097ccfd3fa5c995279cd81d6e1ded9391d4609bdd721494bfd620c07`, block **6**. Its digest verified; the original screening still verified separately.

After actually stopping the Hardhat process, another real Aadhaar screening, `CASE-20260914-72636BB5`, returned **HTTP 200**, name/DOB extraction, MRZ/expiry `NOT_APPLICABLE`, risk **0**, and `SECONDARY_MANUAL_VERIFICATION`. Its audit returned **CHAIN_UNAVAILABLE**, with null transaction hash and block number. No blockchain-caused HTTP 500 occurred.

Local sanitized evidence is retained in ignored `backend/audit_demo/chain-evidence.json` and `backend/audit_demo/outage-evidence.json`. The node was left stopped to preserve the final outage demonstration state. Hardhat history was temporary; these are recorded results of that running chain, not claims that the stopped chain is currently queryable. The demonstration backend was started on port 8001; the existing port 8000 service was not replaced.

## Architecture and integrity boundary

Existing screening saves JSON and SQLite first. An additive audit service reserves the canonical payload/digest locally, then submits in a FastAPI background task. Its failures are contained and leave screening functional. A SQL uniqueness constraint and serialized local submissions prevent accidental duplicate logical records. A transaction hash is saved before waiting for confirmation; retries reconcile already-mined contract records/events.

`SentinelAudit` uses an immutable owner, authorized writers, two record types and a mapping keyed by case key/type/version. Writers may append only to unused slots. Each slot stores digest, timestamp, submitter and existence; events expose the same opaque proof metadata. There are no PII, image, embedding or arbitrary JSON/string payload fields.

`sentinel-audit-v1` canonicalization uses sorted string keys, compact UTF-8 JSON, deterministic booleans/null, ordered arrays and finite plain-decimal numbers. Integer-valued floats equal integers; negative zero equals zero. Exact Unicode string content is retained. The case key is SHA-256 of UTF-8 case ID; the proof is HMAC-SHA256 of canonical UTF-8 bytes using the configured secret's UTF-8 bytes. The generated secret is random hex text. HMAC reduces offline guessing exposure from low-entropy identity data; it does not replace server trust or access control.

Screening snapshots cover persisted document/identity, quality, applicability, MRZ, expiry, QR, validation, selected face output, database/watchlist, forensic and risk results, completion timestamp, plus relevant SQL scalar values. Raw OCR, images, crops, embeddings, paths and transient timings are excluded. Officer notes and disposition remain off-chain in a separate versioned snapshot. Canonical payloads contain sensitive local data and need the same protection as existing case storage.

Verification rereads case JSON from disk and SQL directly, bypassing the session cache, recomputes the current proof and compares with the contract. `VERIFIED` requires on-chain digest equality, not merely a receipt. Editing a pending record cannot silently establish a new baseline. Historical officer versions are verified from their retained historical payload; only the latest decision has corresponding live decision fields. Later officer decisions do not alter the original screening snapshot.

## Database, API and UI

The additive `blockchain_audits` table stores ID, case ID, record type/version, format/key ID, case key, digest, off-chain canonical payload, status, transaction hash, block, chain ID, contract, anchor/verification/creation timestamps and sanitized error. `(case_id, record_type, version)` is unique. Existing screening tables and data are not destructively migrated.

Endpoints:

- `GET /api/blockchain/status`: configured network availability.
- `GET /api/cases/{case_id}/audit`: public audit metadata for saved records.
- `POST /api/cases/{case_id}/audit/anchor`: reserve/anchor/retry a server-derived snapshot.
- `GET /api/cases/{case_id}/audit/verify`: recompute and compare, with optional record type/version.

The routes follow the current unauthenticated local API model and reject caller-supplied proof content by exposing no such parameters. They never return the canonical payload, HMAC secret or wallet key. Contract authorization restricts direct chain writes; it does not provide user authentication to this prototype's HTTP API.

The existing screening page gains a typed Blockchain Audit card showing status, network, chain ID, type/version, transaction hash, block, contract, anchor time and last verification time. It includes verify/retry buttons and a prominent red tamper state, and supports disabled/offline and older responses. Frontend validation was TypeScript/Vite build; no additional browser visual acceptance test is claimed.

## Files created in this phase

- `blockchain/contracts/SentinelAudit.sol`, `blockchain/hardhat.config.js`, `blockchain/package.json`, `blockchain/package-lock.json`, `blockchain/.env.example`, `blockchain/README.md`.
- `blockchain/scripts/deploy.js`, `blockchain/scripts/configure-local.js`, `blockchain/test/SentinelAudit.test.js`.
- `backend/.env.example`, `backend/app/audit_models.py`, `backend/app/routers/blockchain.py`.
- `backend/app/services/audit_canonicalizer.py`, `blockchain_config.py`, `blockchain_service.py`, `sentinel_audit_abi.json`.
- `backend/tests/test_blockchain_audit.py`.
- `frontend/src/components/BlockchainAuditCard.tsx` and `BlockchainAuditCard.css`.
- `scripts/demo_tamper_case.py`, `scripts/run_audit_demo.py`, and this report.

## Existing files modified in this phase

- `.gitignore`: secrets, deployment outputs and demo backups/evidence ignored.
- `backend/app/database.py`: registers the additive audit table before table creation (this file already existed in the working baseline despite being untracked in Git).
- `backend/app/main.py`: audit router registration.
- `backend/app/routers/screening.py`: post-persistence screening/officer audit hooks and background submission.
- `backend/app/schemas/screening.py`: optional audit response metadata.
- `backend/requirements.txt`: web3 dependency.
- `frontend/src/types/index.ts`, `frontend/src/services/api.ts`: typed audit API integration.
- `frontend/src/pages/NewScreeningPage.tsx`: insert the audit card into the existing result page.

The working tree already contained earlier document-routing changes and untracked files. Those were preserved. No Phase 3 change modifies OCR/Aadhaar extraction, MRZ rules, ArcFace model/threshold, routing logic, risk weights, forensic heuristics or watchlist behavior.

## Exact execution and limitations

The complete terminal-by-terminal startup, environment variable reference, verification calls, tamper/restore commands and restart cautions are in [blockchain/README.md](blockchain/README.md). The commands used for the live demo from the repository directory were:

```powershell
python -m uvicorn app.main:app --app-dir backend --env-file backend/.env.audit-local --host 127.0.0.1 --port 8001
python scripts/run_audit_demo.py --document backend/uploads/d1f34082db6c41918a898d1714b6d283.jpeg
# After stopping the local Hardhat node:
python scripts/run_audit_demo.py --document backend/uploads/d1f34082db6c41918a898d1714b6d283.jpeg --outage
```

Backend verification used `$env:RUN_HARDHAT_INTEGRATION='1'` followed by `python -m pytest backend/tests -q -p no:cacheprovider`; contract tests used `npx hardhat test` in `blockchain`; smoke/E2E used the original scripts; frontend used `npm run build` in `frontend`.

Secrets were generated only into ignored local configuration, never embedded in source or example files. Generated node logs, deployment metadata, database artifacts and demonstration backups remain ignored. Keep keys backed up securely. Key rotation/history migration, a persistent chain, durable jobs, multi-worker nonce coordination, authenticated HTTP access, production key custody and finality/reorganization handling remain future work. A fresh Hardhat process loses old chain records even if a repeated deployment has the same address. Selected snapshot integrity does not cover excluded raw images or guarantee identity truth. Development npm dependencies reported 20 advisories (10 low, 3 moderate, 7 high), so production dependency hardening also remains outstanding.

This is a tested local audit prototype, not a production-ready identity or blockchain system.
