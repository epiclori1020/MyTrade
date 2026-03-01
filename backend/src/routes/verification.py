"""Verification API endpoints."""

import logging
from uuid import UUID

from fastapi import HTTPException, Request

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.routes.helpers import sanitize_error_message
from src.services.exceptions import ConfigurationError, PreconditionError
from src.services.verification import run_verification

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api", tags=["verification"])


@router.post("/verify/{analysis_id}")
@limiter.limit("50/minute")
def verify_claims(analysis_id: UUID, request: Request) -> dict:
    """Cross-check claims against a second data source (Alpha Vantage).

    Reads claims for the analysis, fetches AV data, and compares values.
    Writes verification_results rows for cross-checked claims.

    Returns 200 with status="completed" or status="failed" (DB errors).
    Returns 400 for invalid analysis_id, missing claims, or duplicate verification.
    Returns 422 for invalid UUID format (automatic via FastAPI).
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        result = run_verification(str(analysis_id), user_id)
    except PreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Verification service temporarily unavailable",
        )
    except Exception as exc:
        logger.error(
            "Unexpected error verifying claims for %s: %s",
            analysis_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Verification service temporarily unavailable",
        )

    return {
        "status": result.status,
        "analysis_id": result.analysis_id,
        "summary": result.summary,
        "results_count": result.results_count,
        "error_message": sanitize_error_message(result.error_message, "Verification"),
    }
