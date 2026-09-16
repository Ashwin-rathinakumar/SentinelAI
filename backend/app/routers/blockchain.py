"""Audit endpoints inherit the prototype's existing local API access pattern.

No endpoint accepts a caller-provided digest, wallet, payload or contract address.
Only already-persisted cases can be anchored using the server's authorized writer.
"""
from typing import Literal
from fastapi import APIRouter, HTTPException, Path, Query
from app.database import SessionLocal
from app.audit_models import BlockchainAudit
from app.services import blockchain_service as audit

router = APIRouter(prefix="/api", tags=["blockchain audit"])
CaseId = Path(pattern=r"^CASE-[A-Za-z0-9-]{1,58}$")
RecordType = Literal["SCREENING_RESULT", "OFFICER_DECISION"]


@router.get("/blockchain/status")
def status():
    return audit.network_status()


@router.get("/cases/{case_id}/audit")
def records(case_id: str = CaseId):
    try:
        return {"records": audit.list_audits(case_id)}
    except LookupError:
        raise HTTPException(404, "Saved case not found") from None


@router.post("/cases/{case_id}/audit/anchor")
def anchor(case_id: str = CaseId, record_type: RecordType = "SCREENING_RESULT", version: int | None = Query(None, ge=1)):
    try:
        if version is None:
            result = audit.prepare(case_id, record_type)
        else:
            with SessionLocal() as db:
                row = db.query(BlockchainAudit).filter_by(case_id=case_id, record_type=record_type, version=version).first()
                if row is None:
                    raise LookupError()
                result = audit.metadata(row)
        return audit.anchor_safely(result["id"]) if "id" in result else result
    except LookupError:
        raise HTTPException(404, "Saved case/audit not found") from None
    except Exception:
        return {"status": "FAILED", "error_message": "Cannot reserve audit. Check saved decision and audit configuration."}


@router.get("/cases/{case_id}/audit/verify")
def verify(case_id: str = CaseId, record_type: RecordType = "SCREENING_RESULT", version: int | None = Query(None, ge=1)):
    with SessionLocal() as db:
        query = db.query(BlockchainAudit).filter_by(case_id=case_id, record_type=record_type)
        if version is not None:
            query = query.filter_by(version=version)
        row = query.order_by(BlockchainAudit.version.desc()).first()
        if row is None:
            return {"status": "NOT_ANCHORED", "record_type": record_type, "version": version or 1, "digest_match": None}
        audit_id = row.id
    return audit.operate(audit_id, verify=True)
