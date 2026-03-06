import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pythonjsonlogger.json import JsonFormatter
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings
from src.dependencies.rate_limit import limiter, rate_limit_exceeded_handler
from src.dependencies.request_context import (
    RequestContextFilter,
    request_context_dispatch,
    request_id_var,
)
from src.routes import analysis, claims, data, health, policy, system, trades, verification

logger = logging.getLogger(__name__)

# Fail-fast: validates required env vars on import. Reused for CORS + lifespan.
settings = get_settings()


def _configure_logging() -> None:
    """Set up JSON logging with request context injection."""
    formatter = JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(user_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level", "name": "logger"},
    )

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    # Replace default handler(s) with JSON handler
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Add context filter to root logger — all children inherit
    # Remove existing context filters first (prevents accumulation on lifespan re-entry)
    for f in root.filters[:]:
        if isinstance(f, RequestContextFilter):
            root.removeFilter(f)
    root.addFilter(RequestContextFilter())

    # Silence noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _shutdown_cleanup() -> None:
    """Best-effort resource cleanup on shutdown."""
    # 1. Flush pending DB writes (supabase_retry queue)
    try:
        from src.services.supabase_retry import flush_queue, get_queue_size

        pending = get_queue_size()
        if pending > 0:
            flushed = flush_queue()
            logger.info(
                "Flushed retry queue: %d/%d items written", flushed, pending
            )
    except Exception:
        logger.warning("Failed to flush retry queue", exc_info=True)

    # 2. Close Anthropic SDK clients (release httpx connection pools)
    for module_path in (
        "src.agents.fundamental",
        "src.agents.claim_extractor",
    ):
        try:
            mod = importlib.import_module(module_path)
            client_fn = getattr(mod, "_get_client", None)
            if client_fn and hasattr(client_fn, "cache_info"):
                # Only close if client was actually created
                if client_fn.cache_info().currsize > 0:
                    client_fn().close()
                    client_fn.cache_clear()
        except Exception:
            pass  # Best-effort — don't block shutdown

    # 3. Reset Supabase client globals (help GC)
    try:
        import src.services.supabase as sb_mod

        sb_mod._supabase_client = None
        sb_mod._supabase_admin = None
    except Exception:
        pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup/shutdown lifecycle."""
    _configure_logging()
    logger.info("MyTrade API starting", extra={"environment": settings.environment})

    # Restore circuit breaker state from DB (best-effort)
    try:
        from src.services.circuit_breaker import restore_alpaca_cb
        restore_alpaca_cb()
    except Exception:
        logger.warning("Failed to restore circuit breaker state", exc_info=True)

    yield
    # --- Graceful Shutdown ---
    logger.info("MyTrade API shutting down — cleaning up resources")
    _shutdown_cleanup()
    logger.info("MyTrade API shutdown complete")


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

# --- Request Context Middleware ---
# Registered AFTER CORS (LIFO: executes FIRST, sets request_id before handlers)
app.add_middleware(BaseHTTPMiddleware, dispatch=request_context_dispatch)


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
            "request_id": request_id_var.get(),
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
            "request_id": request_id_var.get(),
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
            "request_id": request_id_var.get(),
        },
    )


# --- Routes ---
app.include_router(health.router)
app.include_router(data.router)
app.include_router(analysis.router)
app.include_router(claims.router)
app.include_router(verification.router)
app.include_router(policy.router)
app.include_router(trades.router)
app.include_router(system.router)
