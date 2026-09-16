"""Additive audit metadata, isolated from existing screening tables."""
from sqlalchemy import Column, Integer, String, Text, DateTime, UniqueConstraint
from app.database import Base
from app.models import _utcnow


class BlockchainAudit(Base):
    __tablename__ = "blockchain_audits"
    id = Column(Integer, primary_key=True)
    case_id = Column(String(64), nullable=False, index=True)
    record_type = Column(String(32), nullable=False)
    version = Column(Integer, nullable=False)
    format_version = Column(String(32), nullable=False, default="sentinel-audit-v1")
    hmac_key_id = Column(String(64), nullable=False)
    case_key = Column(String(66), nullable=False)
    digest = Column(String(66), nullable=False)
    canonical_payload = Column(Text, nullable=False)  # OFF-CHAIN only
    status = Column(String(32), nullable=False, default="PENDING")
    transaction_hash = Column(String(66))
    block_number = Column(Integer)
    chain_id = Column(Integer, nullable=False)
    contract_address = Column(String(42), nullable=False)
    anchored_at = Column(DateTime)
    last_verified_at = Column(DateTime)
    error_message = Column(String(256))
    created_at = Column(DateTime, nullable=False, default=_utcnow)
    __table_args__ = (UniqueConstraint("case_id", "record_type", "version", name="uq_audit_record"),)
