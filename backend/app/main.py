import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import APP_DESCRIPTION, APP_NAME, APP_VERSION, CORS_ORIGINS
from app.routers.upload import router as upload_router
from app.routers.screening import router as screening_router
from app.routers.blockchain import router as blockchain_router
from app.routers.cases import router as cases_router
from app.services.file_service import ensure_uploads_directory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle."""
    # --- Startup ---
    ensure_uploads_directory()
    # Initialize SQLite database and seed demo data on first run
    from app.database import init_db
    init_db(seed=True)
    logger.info("SentinelAI backend started successfully.")
    yield
    # --- Shutdown ---
    logger.info("SentinelAI backend shutting down.")


app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(cases_router)
app.include_router(screening_router)
app.include_router(blockchain_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "Validation error.",
            "detail": exc.errors()[0].get("msg", "Invalid request."),
        },
    )


@app.get("/")
def home() -> dict:
    return {
        "message": "SentinelAI Backend is Running",
        "service": APP_NAME,
        "version": APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
def health_check() -> dict:
    return {
        "status": "healthy",
        "service": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
