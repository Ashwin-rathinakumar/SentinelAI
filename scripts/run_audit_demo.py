"""Local demonstration against a running backend and real deployed Hardhat contract."""
import argparse
import json
import subprocess
import sys
import time
import mimetypes
from pathlib import Path
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8001")
    parser.add_argument("--document", type=Path, required=True)
    parser.add_argument("--selfie", type=Path)
    parser.add_argument("--outage", action="store_true")
    parser.add_argument("--document-type", default="unknown")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with args.document.open("rb") as stream:
        files = {"file": (args.document.name, stream, mimetypes.guess_type(args.document.name)[0] or "application/octet-stream")}
        if args.selfie:
            files["selfie"] = (args.selfie.name, args.selfie.read_bytes(), mimetypes.guess_type(args.selfie.name)[0] or "application/octet-stream")
        response = requests.post(args.api + "/api/screen", files=files, data={"document_type": args.document_type}, timeout=180)
    response.raise_for_status()
    case = response.json()
    base = args.api + "/api/cases/" + case["case_id"] + "/audit"
    record = None
    for _ in range(25):
        rows = requests.get(base, timeout=10).json()["records"]
        record = rows[0] if rows else None
        if record and record["status"] != "PENDING":
            break
        time.sleep(1)
    evidence = {"case_id": case["case_id"], "http_status": response.status_code,
        "document_type": case["document_type"], "name_extracted": bool(case['ocr']['fields'].get('full_name', {}).get('normalized')),
        "dob_extracted": bool(case['ocr']['fields'].get('date_of_birth', {}).get('normalized')),
        "mrz": case['mrz'].get('status'), "expiry": case['expiry'].get('status'), "risk_score": case['risk']['risk_score'],
        "recommendation": case['risk']['recommendation'], "audit": record}
    if args.outage:
        assert record and record['status'] == 'CHAIN_UNAVAILABLE', evidence
    else:
        assert record and record['status'] == 'ANCHORED', evidence
        verified = requests.get(base + '/verify', timeout=30).json()
        assert verified['status'] == 'VERIFIED' and verified['digest_match'] is True, verified
        evidence['original_verify'] = verified
        command = [sys.executable, str(root / 'scripts/demo_tamper_case.py'), '--case-id', case['case_id']]
        subprocess.run(command, check=True)
        try:
            tampered = requests.get(base + '/verify', timeout=30).json()
            assert tampered['status'] == 'TAMPER_DETECTED' and tampered['digest_match'] is False, tampered
            evidence['tamper_verify'] = tampered
        finally:
            subprocess.run(command + ['--restore'], check=True)
        restored = requests.get(base + '/verify', timeout=30).json()
        assert restored['status'] == 'VERIFIED', restored
        evidence['restored_verify'] = restored
        officer = requests.post(args.api + '/api/cases/' + case['case_id'] + '/decision',
            json={'decision': 'MANUAL_VERIFICATION', 'notes': 'Local audit demonstration', 'officer_id': 'DEMO'}, timeout=30)
        officer.raise_for_status()
        for _ in range(25):
            rows = requests.get(base, timeout=10).json()['records']
            decisions = [row for row in rows if row['record_type'] == 'OFFICER_DECISION']
            if decisions and decisions[-1]['status'] != 'PENDING': break
            time.sleep(1)
        decision_check = requests.get(base + '/verify?record_type=OFFICER_DECISION', timeout=30).json()
        assert decision_check['status'] == 'VERIFIED', decision_check
        assert requests.get(base + '/verify', timeout=30).json()['status'] == 'VERIFIED'
        evidence['officer_decision_verify'] = decision_check
    folder = root / 'backend/audit_demo'; folder.mkdir(exist_ok=True)
    path = folder / ('outage-evidence.json' if args.outage else 'chain-evidence.json')
    path.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps(evidence, indent=2))  # Only summary and public transaction metadata.


if __name__ == '__main__':
    main()
