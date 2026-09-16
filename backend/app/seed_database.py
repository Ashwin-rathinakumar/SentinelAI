"""Seed the SQLite database with synthetic demo identities.

All records are clearly labelled as [SYNTHETIC/DEMO] and correspond
to the same identities previously stored in the DEMO_RECORDS dict.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session as SASession

from app.database import SessionLocal
from app.models import Document, Person, Watchlist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic identity records (migrated from former DEMO_RECORDS dict)
# ---------------------------------------------------------------------------
SEED_IDENTITIES: list[dict] = [
    {
        "full_name": "ANNA MARIA ERIKSSON",
        "date_of_birth": "1969-08-06",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "L898902C",
                "document_type": "passport",
                "expiry_date": "1994-06-23",
                "status": "EXPIRED",
                "note": "[SYNTHETIC/DEMO] Standard expired travel record (ICAO benchmark).",
            }
        ],
    },
    {
        "full_name": "JOHNATHAN DOE",
        "date_of_birth": "1985-04-12",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "P1234567",
                "document_type": "passport",
                "expiry_date": "2030-04-12",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Verified active synthetic traveler identity.",
            },
            {
                "document_number": "P12345678",
                "document_type": "passport",
                "expiry_date": "2030-04-12",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Alternate document number variant.",
            },
        ],
    },
    {
        "full_name": "SARAH JENKINS",
        "date_of_birth": "1990-11-23",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "A1234567",
                "document_type": "passport",
                "expiry_date": "2029-11-23",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Verified clear identity.",
            }
        ],
    },
    {
        "full_name": "MARIA GARCIA",
        "date_of_birth": "1990-01-15",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "A12345678",
                "document_type": "passport",
                "expiry_date": "2030-01-15",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Verified clear identity.",
            }
        ],
    },
    {
        "full_name": "VIKTOR KORZHOV",
        "date_of_birth": "1978-11-20",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "B7654321",
                "document_type": "passport",
                "expiry_date": "2027-11-20",
                "status": "SUSPICIOUS",
                "note": "[SYNTHETIC/DEMO] ALERT: Flagged on international border watch list.",
            }
        ],
        "watchlist": [
            {
                "document_number": "B7654321",
                "reason": "Reported stolen passport — flagged on international border watch list.",
                "severity": "HIGH",
                "active": True,
            }
        ],
    },
    {
        "full_name": "ELENA ROSTOVA",
        "date_of_birth": "1995-09-30",
        "nationality": "UTO",
        "documents": [
            {
                "document_number": "E9988776",
                "document_type": "passport",
                "expiry_date": "2031-09-30",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Verified clear identity.",
            }
        ],
    },
    {
        "full_name": "MARIA GARCIA",
        "date_of_birth": "1982-07-30",
        "nationality": "ESP",
        "documents": [
            {
                "document_number": "C2468135",
                "document_type": "passport",
                "expiry_date": "2022-07-30",
                "status": "EXPIRED",
                "note": "[SYNTHETIC/DEMO] Document expired in local registry.",
            }
        ],
    },
    {
        "full_name": "MIKHAIL VOLKOV",
        "date_of_birth": "1975-09-18",
        "nationality": "DEU",
        "documents": [
            {
                "document_number": "D1357902",
                "document_type": "passport",
                "expiry_date": "2032-09-18",
                "status": "SUSPICIOUS",
                "note": "[SYNTHETIC/DEMO] Flagged for manual secondary inspection.",
            }
        ],
        "watchlist": [
            {
                "document_number": "D1357902",
                "reason": "Flagged for manual secondary inspection — suspicious travel pattern.",
                "severity": "MEDIUM",
                "active": True,
            }
        ],
    },
    {
        "full_name": "RAJ PATEL",
        "date_of_birth": "1992-05-14",
        "nationality": "IND",
        "documents": [
            {
                "document_number": "E9876543",
                "document_type": "passport",
                "expiry_date": "2031-05-14",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Verified identity record.",
            }
        ],
    },
    {
        "full_name": "GENUINE PERSON NAME",
        "date_of_birth": "1995-01-01",
        "nationality": "GBR",
        "documents": [
            {
                "document_number": "M9999999",
                "document_type": "passport",
                "expiry_date": "2030-01-01",
                "status": "VALID",
                "note": "[SYNTHETIC/DEMO] Benchmark for detecting identity mismatch.",
            }
        ],
    },
]


def seed_if_empty() -> None:
    """Insert seed demo identities idempotently if they do not already exist."""
    db: SASession = SessionLocal()
    try:
        for identity in SEED_IDENTITIES:
            person = (
                db.query(Person)
                .filter(
                    Person.full_name == identity["full_name"],
                    Person.date_of_birth == identity.get("date_of_birth"),
                )
                .first()
            )
            if not person:
                person = Person(
                    full_name=identity["full_name"],
                    date_of_birth=identity.get("date_of_birth"),
                    nationality=identity.get("nationality"),
                )
                db.add(person)
                db.flush()

            for doc_data in identity.get("documents", []):
                doc_num = doc_data["document_number"]
                doc = db.query(Document).filter(Document.document_number == doc_num).first()
                if not doc:
                    doc = Document(
                        person_id=person.id,
                        document_number=doc_num,
                        document_type=doc_data.get("document_type", "passport"),
                        expiry_date=doc_data.get("expiry_date"),
                        status=doc_data.get("status", "VALID"),
                        note=doc_data.get("note"),
                    )
                    db.add(doc)

            for wl_data in identity.get("watchlist", []):
                wl_doc_num = wl_data.get("document_number")
                wl = (
                    db.query(Watchlist)
                    .filter(
                        Watchlist.document_number == wl_doc_num,
                        Watchlist.person_id == person.id,
                    )
                    .first()
                )
                if not wl:
                    wl = Watchlist(
                        person_id=person.id,
                        document_number=wl_doc_num,
                        reason=wl_data["reason"],
                        severity=wl_data.get("severity", "MEDIUM"),
                        active=wl_data.get("active", True),
                    )
                    db.add(wl)

        db.commit()
        logger.info("Seed check/insertion completed.")
    except Exception:
        db.rollback()
        logger.exception("Failed to seed database")
        raise
    finally:
        db.close()
