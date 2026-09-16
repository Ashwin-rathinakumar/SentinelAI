"""SQLAlchemy database engine, session factory, and initialization."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BASE_DIR, DATABASE_URL

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "sentinelai.db"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


_engine_options = {"pool_pre_ping": True, "echo": False}
if DATABASE_URL.startswith("sqlite"):
    _engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **_engine_options)

# Enable WAL mode and foreign keys for SQLite
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Session:
    """FastAPI dependency that yields a DB session and auto-closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(seed: bool = True) -> None:
    """Create all tables and optionally seed demo data."""
    from app.models import (  # noqa: F401 — ensure models are registered
        Document,
        FaceEmbedding,
        FaceResult,
        OCRResult,
        ScreeningCase,
        TamperResult,
        Traveller,
        WatchlistCheck,
        WatchlistEntry,
    )
    from app.audit_models import BlockchainAudit  # noqa: F401 — additive table

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        logger.info("SQLite development tables are ready at %s", DB_PATH)
    else:
        logger.info("PostgreSQL database initialized.")

    if seed:
        from app.seed_database import seed_if_empty
        seed_if_empty()
