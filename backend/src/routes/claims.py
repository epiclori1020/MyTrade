"""Claims API endpoints."""

import logging
from uuid import UUID

from fastapi import HTTPException, Request

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.services.claim_extraction import run_claim_extraction
from src.services.exceptions import ConfigurationError, PreconditionError

logger = logging.getLogger(__name__)

router = authenticated_router(prefix="/api", tags=["claims"])


@router.post("/extract-claims/{analysis_id}")
@limiter.limit("50/minute")
def extract_claims(analysis_id: UUID, request: Request) -> dict:
    """Extract verifiable claims from a completed analysis.

    Reads fundamental_out from the analysis run, extracts claims via
    Haiku LLM, and stores them in the claims table.

    Returns 200 with status="completed" or status="failed" (agent errors).
    Returns 400 for invalid analysis_id or missing data.
    Returns 422 for invalid UUID format (automatic via FastAPI).
    Returns 503 for server misconfiguration.
    """
    user_id = request.state.user["id"]

    try:
        result = run_claim_extraction(str(analysis_id), user_id)
    except PreconditionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConfigurationError as exc:
        logger.error("Configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Claim extraction service temporarily unavailable",
        )
    except Exception as exc:
        logger.error(
            "Unexpected error extracting claims for %s: %s",
            analysis_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Claim extraction service temporarily unavailable",
        )

    return {
        "status": result.status,
        "analysis_id": result.analysis_id,
        "claims_count": result.claims_count,
        "claims": result.claims,
        "tokens_used": result.tokens_used,
        "cost_usd": result.cost_usd,
        "error_message": _sanitize_error(result.error_message),
    }


def _sanitize_error(error_message: str | None) -> str | None:
    """Return a client-safe error message without internal details."""
    if error_message is None:
        return None
    lower = error_message.lower()
    if "timeout" in lower:
        return "Claim extraction timed out. Please try again."
    if "api error" in lower:
        return "Claim extraction service error. Please try again later."
    if "parse" in lower or "schema" in lower or "extraction_failed" in lower:
        return "Claim extraction produced invalid output. Please try again."
    if "db" in lower or "database" in lower:
        return "Failed to save claims. Please try again."
    return "Claim extraction failed. Please try again."
