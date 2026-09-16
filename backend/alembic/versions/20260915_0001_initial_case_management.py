"""Initial traveller, document and screening result schema.

Revision ID: 20260915_0001
Revises: None
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    # Legacy physical table names are retained so existing screening services can
    # use the new Traveller/ScreeningCase/WatchlistEntry domain classes safely.
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("full_name", sa.String(256), nullable=False),
        sa.Column("date_of_birth", sa.String(10)),
        sa.Column("nationality", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("document_number", sa.String(70), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False, server_default="passport"),
        sa.Column("issue_date", sa.String(10)),
        sa.Column("expiry_date", sa.String(10)),
        sa.Column("status", sa.String(20), nullable=False, server_default="VALID"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_documents_document_number", "documents", ["document_number"])
    op.create_index("ix_documents_number_upper", "documents", ["document_number"])
    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id")),
        sa.Column("document_number", sa.String(70)),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="MEDIUM"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_watchlist_document_number", "watchlist", ["document_number"])
    # Pre-existing ArcFace storage needed by the unchanged screening endpoint.
    op.create_table(
        "face_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("model_name", sa.String(64), nullable=False, server_default="ArcFace"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "verification_cases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), nullable=False, unique=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id")),
        sa.Column("extracted_document_number", sa.String(70)),
        # Existing pipeline compatibility fields; the new API does not calculate risk or decisions.
        sa.Column("face_similarity", sa.Float()),
        sa.Column("mrz_valid", sa.Boolean()),
        sa.Column("watchlist_match", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duplicate_identity", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tamper_score", sa.Float()),
        sa.Column("risk_score", sa.Integer()),
        sa.Column("decision", sa.String(32)),
        sa.Column("officer_id", sa.String(64)),
        sa.Column("officer_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_verification_cases_case_id", "verification_cases", ["case_id"], unique=True)
    op.create_table(
        "ocr_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("confidence", sa.Float()),
        sa.Column("extracted_fields", JSON_TYPE, nullable=False),
        sa.Column("raw_text", sa.Text()),
        sa.Column("details", JSON_TYPE, nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_ocr_results_case_id", "ocr_results", ["case_id"], unique=True)
    op.create_table(
        "face_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="NOT_PROVIDED"),
        sa.Column("similarity", sa.Float()),
        sa.Column("match", sa.Boolean()),
        sa.Column("model_name", sa.String(64)),
        sa.Column("threshold", sa.Float()),
        sa.Column("details", JSON_TYPE, nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_face_results_case_id", "face_results", ["case_id"], unique=True)
    op.create_table(
        "tamper_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("detected", sa.Boolean()),
        sa.Column("score", sa.Float()),
        sa.Column("details", JSON_TYPE, nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_tamper_results_case_id", "tamper_results", ["case_id"], unique=True)
    op.create_table(
        "watchlist_checks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("case_id", sa.String(64), sa.ForeignKey("verification_cases.case_id", ondelete="CASCADE"), nullable=False),
        sa.Column("watchlist_entry_id", sa.Integer(), sa.ForeignKey("watchlist.id", ondelete="SET NULL")),
        sa.Column("matched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("match_score", sa.Float()),
        sa.Column("details", JSON_TYPE, nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_watchlist_checks_case_id", "watchlist_checks", ["case_id"])


def downgrade() -> None:
    op.drop_table("watchlist_checks")
    op.drop_table("tamper_results")
    op.drop_table("face_results")
    op.drop_table("ocr_results")
    op.drop_table("verification_cases")
    op.drop_table("face_embeddings")
    op.drop_table("watchlist")
    op.drop_table("documents")
    op.drop_table("persons")
