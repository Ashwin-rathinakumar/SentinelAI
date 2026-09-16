from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)

# PostgreSQL is selected by setting DATABASE_URL.  The SQLite fallback keeps the
# existing self-contained demo and test workflow working.
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'sentinelai.db'}")
UPLOADS_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
SESSIONS_DIR = BASE_DIR / "sessions"

APP_NAME = "SentinelAI API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "AI-Powered Fake Identity & Document Screening System"

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}

ALLOWED_MIME_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".pdf": {"application/pdf"},
}

DOCUMENT_TYPES = {
    "aadhaar",
    "unknown",
    "passport",
    "visa",
    "national_id",
    "driving_license",
    "permit",
}

OCR_LOW_CONFIDENCE_THRESHOLD = 55
OCR_MIN_TEXT_CHARS = 8
