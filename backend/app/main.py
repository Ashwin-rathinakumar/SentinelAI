from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from app.config import APP_DESCRIPTION, APP_NAME, APP_VERSION, CORS_ORIGINS
from app.routers.upload import router as upload_router
from app.routers.screening import router as screening_router
from app.services.file_service import ensure_uploads_directory

app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router)
app.include_router(screening_router)


@app.on_event("startup")
def on_startup() -> None:
    ensure_uploads_directory()


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
