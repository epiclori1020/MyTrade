import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.config import get_settings
from src.dependencies.rate_limit import limiter, rate_limit_exceeded_handler
from src.routes import health

logger = logging.getLogger(__name__)

# Fail-fast: validates required env vars on import. Reused for CORS + lifespan.
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown lifecycle."""
    logging.basicConfig(level=settings.log_level)
    logger.info("MyTrade API starting (environment=%s)", settings.environment)
    yield
    logger.info("MyTrade API shutting down")


app = FastAPI(
    title="MyTrade API",
    version="0.1.0",
    description="AI-powered investment analysis backend for MyTrade.",
    lifespan=lifespan,
)

# --- Rate Limiter (slowapi) ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Exception Handlers ---


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Consistent JSON format for all HTTP errors (including routing 404s)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail if isinstance(exc.detail, str) else "error",
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Consistent JSON format for validation errors."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": exc.errors(),
            "status_code": 422,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(_request: Request, _exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Never leaks stack traces."""
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
            "status_code": 500,
        },
    )


# --- Routes ---
app.include_router(health.router)
