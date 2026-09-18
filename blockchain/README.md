# SentinelAI local blockchain audit

This is a working local prototype audit layer. The blockchain does NOT verify the authenticity of an identity. It preserves cryptographic evidence that selected saved screening results have not changed since anchoring. OCR, MRZ, ArcFace, risk and officer review remain the existing application responsibilities.

## Start a fresh local demonstration

Run these PowerShell commands from the repository directory `SenitalAI`. Use separate terminals for long-running processes. Install the backend's existing prerequisites as usual.

Terminal 1:

```powershell
cd blockchain
npm ci
npx hardhat node --hostname 127.0.0.1
```

Terminal 2, starting from the repository directory:

```powershell
cd blockchain
npx hardhat run scripts/deploy.js --network localhost
npx hardhat run scripts/configure-local.js --network localhost
```

Deployment prints the actual contract address, chain ID, transaction and block. Configuration creates a random writer, funds it with fake local ETH, authorizes it, and writes ignored `backend/.env.audit-local`. Neither the private key nor HMAC secret is printed. Rerunning configuration preserves existing writer/HMAC secrets and reauthorizes or funds the writer when necessary. Deployment reuses a valid live local contract. A restarted Hardhat node loses previous on-chain history; use new demo cases after restarting and configuring. Hardhat's default accounts are development accounts only.

Terminal 3, starting from the repository directory:

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn app.main:app --app-dir backend --env-file backend/.env.audit-local --host 127.0.0.1 --port 8000
```

Terminal 4, starting from the repository directory:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1
```

Use one backend worker. Without enabled blockchain configuration, ordinary startup remains supported and auditing is disabled. The completed demonstration used port 8001 to avoid disturbing an existing backend on 8000. Point the frontend's existing API configuration to the desired backend if using another port.

## Configuration

All backend variables and placeholders are in `backend/.env.example`:

- `BLOCKCHAIN_ENABLED`: defaults to `false`.
- `BLOCKCHAIN_RPC_URL`: defaults to `http://127.0.0.1:8545`.
- `BLOCKCHAIN_CHAIN_ID`: defaults to `31337`; provider must match.
- `BLOCKCHAIN_CONTRACT_ADDRESS`: deployed SentinelAudit address.
- `BLOCKCHAIN_WRITER_PRIVATE_KEY`: server-only authorized signer.
- `BLOCKCHAIN_AUDIT_HMAC_KEY`: server-only secret, at least 32 UTF-8 bytes. The helper generates 32 random bytes encoded as hex; the HMAC key is the UTF-8 text of that hex string, not hex-decoded bytes.
- `BLOCKCHAIN_AUDIT_HMAC_KEY_ID`: defaults to `local-v1`; records retain this identifier.
- `BLOCKCHAIN_RPC_TIMEOUT`: defaults to 3 seconds.
- `BLOCKCHAIN_RECEIPT_TIMEOUT`: defaults to 15 seconds.

Keep the HMAC key backed up securely for the lifetime of the records. Losing it prevents verification. Rotation and multi-key historical verification require an explicit migration; they are not implemented. The wallet key can be changed to another authorized writer on the same contract. Existing records bind to their chain, contract, HMAC key ID and format.

`blockchain/.env.example` also documents optional testnet deployment variables. The deployment script permits chain IDs 31337, 80002 and 11155111 only. No public deployment was performed. A testnet deployment needs its own funded signer, authorized backend writer and configuration; do not reuse local development keys there.

## Contract and privacy

`SentinelAudit.sol` has an immutable owner and an owner-managed writer allowlist. `anchorRecord`, `getRecord` and `recordExists` address a record by `(bytes32 caseKey, RecordType, version)`. Existing records cannot be overwritten. Types are `SCREENING_RESULT = 0` and `OFFICER_DECISION = 1`. The contract stores a bytes32 digest, block timestamp, submitter and existence flag, and emits `AuditAnchored`. Backend retries reconcile an existing record instead of writing duplicates.

The case key is SHA-256 of the internal case ID's UTF-8 bytes. The proof is HMAC-SHA256 of `sentinel-audit-v1` canonical JSON. This avoids exposing a plain hash of guessable identity fields. Case keys are pseudonymous, not a guarantee of unlinkability if an observer already knows a case ID. Chain timing and writer addresses remain public metadata.

Canonicalization sorts string keys by Unicode order, uses compact UTF-8 JSON, preserves array order and exact string content, emits JSON null/booleans, and formats finite numbers as plain decimal with trailing fractional zeros removed. Thus `1` and `1.0` agree, and negative zero becomes zero. Nonfinite/unsupported values fail. Strings are not Unicode-normalized. This is a versioned application format, not a claim of RFC 8785 compatibility.

The snapshot selects saved identity fields, document routing, quality, MRZ/expiry/QR/validation, face outcome, database/watchlist result, forensic result, risk and persisted SQL summary values. Stable screening completion time is included. Raw OCR text, runtime timings, paths, images, crops and embeddings are excluded. Decision snapshots separately contain saved disposition, officer, notes and time. Sensitive canonical payloads remain in the local audit table; only case key, type, version and HMAC digest are transaction arguments. Audit API responses expose metadata, never that payload or either secret.

## Persistence and verification

After ordinary JSON/SQLite persistence, the backend reserves an immutable audit snapshot in the additive `blockchain_audits` table and schedules anchoring as a background task. The screening response does not wait for chain confirmation. Outage leaves the saved screening usable and the audit retryable.

Verification rereads the saved JSON and SQL values rather than the session cache, reconstructs the snapshot, recomputes HMAC, reads the contract and requires digest equality. A receipt alone cannot yield `VERIFIED`. Editing a reserved but unanchored record does not replace its original digest. Current officer disposition is checked against live saved values; older decision versions are checked against their retained off-chain historical snapshots. The original screening excludes officer mutations.

Endpoints follow the existing local application's unauthenticated API pattern:

- `GET /api/blockchain/status`
- `GET /api/cases/{case_id}/audit`
- `POST /api/cases/{case_id}/audit/anchor`
- `GET /api/cases/{case_id}/audit/verify`

Anchor/verify accept optional query parameters `record_type=SCREENING_RESULT|OFFICER_DECISION` and `version`. They accept no caller-provided digest, private payload or contract. Without a version, verification selects the latest record of that type. The result card shows transaction metadata, verification time, retry controls and a prominent integrity failure state.

## Tests and real demonstration

With the configured local node still running, from the repository directory:

```powershell
$env:RUN_HARDHAT_INTEGRATION='1'
python -m pytest backend/tests -q -p no:cacheprovider
Remove-Item Env:RUN_HARDHAT_INTEGRATION
python test_backend.py
python test_e2e.py
cd blockchain
npx hardhat test
cd ../frontend
npm run build
```

Normal tests without that environment variable skip the optional real-chain integration. For a real local Aadhaar demonstration against port 8000:

```powershell
python scripts/run_audit_demo.py --api http://127.0.0.1:8000 --document backend/uploads/d1f34082db6c41918a898d1714b6d283.jpeg
```

The script verifies, edits only the new demo case's SQL risk score, detects tampering, restores the score in a `finally` block, verifies again and anchors a separate officer decision. Use another local Aadhaar file if this ignored upload is unavailable. Optional `--selfie` exercises the existing selfie flow. Evidence is saved under ignored `backend/audit_demo`.

For individual steps, replace the example case ID with a newly anchored demo case:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/cases/CASE-DEMO/audit/verify
python scripts/demo_tamper_case.py --case-id CASE-DEMO
Invoke-RestMethod http://127.0.0.1:8000/api/cases/CASE-DEMO/audit/verify
python scripts/demo_tamper_case.py --case-id CASE-DEMO --restore
Invoke-RestMethod http://127.0.0.1:8000/api/cases/CASE-DEMO/audit/verify
```

The tamper utility is DEVELOPMENT / DEMO ONLY, keeps a local restore backup and refuses unsafe restoration over a newer value. No tamper HTTP endpoint exists. To demonstrate outage, stop Terminal 1 with Ctrl+C, then run:

```powershell
python scripts/run_audit_demo.py --api http://127.0.0.1:8000 --document backend/uploads/d1f34082db6c41918a898d1714b6d283.jpeg --outage
```

## Prototype limitations

Hardhat node state is ephemeral: restarting does not restore mined history. An identical deployment address on a fresh chain does not recover old proofs. Keep a node running throughout an integrity demonstration. For a fresh run, preserve the old configuration in a secure location outside Git, then configure a fresh deployment and create new demo cases; do not delete existing case/audit history or expect old records to verify against the new chain. Configuration generation deliberately refuses to overwrite the current key file.

The completed run deliberately left the node stopped after proving outage. Its transaction evidence is documented in `../BLOCKCHAIN_AUDIT_REPORT.md`; those receipts are evidence from the completed run, not a currently reachable persistent chain.

There is no durable job queue, automatic restart reconciliation, multi-worker nonce coordination, external authentication, production key custody, finality/reorganization policy or persistent chain deployment. Retry through the audit endpoint/card. One process serializes submissions; contract and database uniqueness provide additional duplicate protection. A compromised trusted server/HMAC key can create new misleading attestations, while existing contract slots remain immutable on that chain. Selected results are protected; excluded images, raw OCR and unrelated fields are not covered. Local payload and original upload retention remain subject to the application's existing privacy protections. The npm installation reported 20 development dependency advisories (10 low, 3 moderate, 7 high); production dependency remediation and deployment hardening remain outstanding.

Tooling references: [Hardhat 2 setup](https://v2.hardhat.org/hardhat-runner/docs/guides/project-setup) and [web3.py transaction documentation](https://web3py.readthedocs.io/en/stable/transactions.html).
