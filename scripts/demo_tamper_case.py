"""DEVELOPMENT / DEMO ONLY. Modify then safely restore a local SQLite risk score.

No HTTP tamper endpoint exists. Only an explicitly named case is modified.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.database import SessionLocal
from app.models import VerificationCase


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--risk-score", type=int, default=77)
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"CASE-[A-Za-z0-9-]{1,58}", args.case_id) or not 0 <= args.risk_score <= 100:
        parser.error("Use a valid case ID and risk score from 0 to 100")
    folder = ROOT / "backend" / "audit_demo"
    folder.mkdir(exist_ok=True)
    backup = folder / f"{args.case_id}.restore.json"
    with SessionLocal() as db:
        row = db.query(VerificationCase).filter_by(case_id=args.case_id).first()
        if row is None:
            parser.error("Saved SQLite case not found")
        if args.restore:
            data = json.loads(backup.read_text(encoding="utf-8"))
            if data["case_id"] != args.case_id or row.risk_score != data["modified"]:
                parser.error("Case changed since demo edit; refusing to overwrite newer data")
            row.risk_score = data["original"]
        else:
            # Exclusive backup prevents accidental loss of the original value.
            with backup.open("x", encoding="utf-8") as stream:
                json.dump({"case_id": args.case_id, "original": row.risk_score, "modified": args.risk_score}, stream)
            row.risk_score = args.risk_score
        db.commit()
    print("DEVELOPMENT DEMO:", "restored" if args.restore else "modified", args.case_id,
          "SQLite risk_score. Call the audit verify endpoint to compare against chain.")


if __name__ == "__main__":
    main()
