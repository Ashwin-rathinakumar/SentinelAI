"""SQLAlchemy ORM models for SentinelAI identity verification database."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    LargeBinary,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


JSONType = JSON().with_variant(JSONB(), "postgresql")


class Traveller(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(256), nullable=False)
    date_of_birth = Column(String(10), nullable=True)  # ISO YYYY-MM-DD
    nationality = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    documents = relationship("Document", back_populates="traveller", cascade="all, delete-orphan")
    face_embeddings = relationship("FaceEmbedding", back_populates="traveller", cascade="all, delete-orphan")
    watchlist_entries = relationship("WatchlistEntry", back_populates="traveller", cascade="all, delete-orphan")

    @property
    def person_id(self):
        return self.id


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    document_number = Column(String(70), nullable=False, index=True)
    document_type = Column(String(20), nullable=False, default="passport")
    issue_date = Column(String(10), nullable=True)
    expiry_date = Column(String(10), nullable=True)
    status = Column(String(20), nullable=False, default="VALID")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    traveller = relationship("Traveller", back_populates="documents")

    @property
    def person(self):
        return self.traveller

    __table_args__ = (
        Index("ix_documents_number_upper", "document_number"),
    )


class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=False)
    embedding = Column(LargeBinary, nullable=False)  # pickled np.ndarray
    model_name = Column(String(64), nullable=False, default="ArcFace")
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    traveller = relationship("Traveller", back_populates="face_embeddings")

    @property
    def person(self):
        return self.traveller


class WatchlistEntry(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    document_number = Column(String(70), nullable=True, index=True)
    reason = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False, default="MEDIUM")
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    traveller = relationship("Traveller", back_populates="watchlist_entries")

    @property
    def person(self):
        return self.traveller


class ScreeningCase(Base):
    __tablename__ = "verification_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), unique=True, nullable=False)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    extracted_document_number = Column(String(70), nullable=True)
    face_similarity = Column(Float, nullable=True)
    mrz_valid = Column(Boolean, nullable=True)
    watchlist_match = Column(Boolean, nullable=False, default=False)
    duplicate_identity = Column(Boolean, nullable=False, default=False)
    tamper_score = Column(Float, nullable=True)
    risk_score = Column(Integer, nullable=True)
    decision = Column(String(32), nullable=True)
    officer_id = Column(String(64), nullable=True)
    officer_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    document = relationship("Document")
    ocr_result = relationship("OCRResult", back_populates="case", uselist=False, cascade="all, delete-orphan")
    face_result = relationship("FaceResult", back_populates="case", uselist=False, cascade="all, delete-orphan")
    tamper_result = relationship("TamperResult", back_populates="case", uselist=False, cascade="all, delete-orphan")
    watchlist_checks = relationship("WatchlistCheck", back_populates="case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_verification_cases_case_id", "case_id", unique=True),
    )


class _CaseResultMixin:
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True)
    details = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class OCRResult(_CaseResultMixin, Base):
    __tablename__ = "ocr_results"
    status = Column(String(32), nullable=False, default="PENDING")
    confidence = Column(Float)
    extracted_fields = Column(JSONType, nullable=False, default=dict)
    raw_text = Column(Text)
    case = relationship("ScreeningCase", back_populates="ocr_result")

    __table_args__ = (
        Index("ix_ocr_results_case_id", "case_id", unique=True),
    )


class FaceResult(_CaseResultMixin, Base):
    __tablename__ = "face_results"
    status = Column(String(32), nullable=False, default="NOT_PROVIDED")
    similarity = Column(Float)
    match = Column(Boolean)
    model_name = Column(String(64))
    threshold = Column(Float)
    case = relationship("ScreeningCase", back_populates="face_result")

    __table_args__ = (
        Index("ix_face_results_case_id", "case_id", unique=True),
    )


class TamperResult(_CaseResultMixin, Base):
    __tablename__ = "tamper_results"
    status = Column(String(32), nullable=False, default="PENDING")
    detected = Column(Boolean)
    score = Column(Float)
    case = relationship("ScreeningCase", back_populates="tamper_result")

    __table_args__ = (
        Index("ix_tamper_results_case_id", "case_id", unique=True),
    )


class WatchlistCheck(Base):
    __tablename__ = "watchlist_checks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String(64), ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    watchlist_entry_id = Column(Integer, ForeignKey("watchlist.id", ondelete="SET NULL"), nullable=True)
    matched = Column(Boolean, nullable=False, default=False)
    match_score = Column(Float)
    details = Column(JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    case = relationship("ScreeningCase", back_populates="watchlist_checks")
    watchlist_entry = relationship("WatchlistEntry")


# Compatibility names used by the established screening, face and blockchain
# services. They now point to the domain names exposed by the new data layer.
Person = Traveller
Watchlist = WatchlistEntry
VerificationCase = ScreeningCase
