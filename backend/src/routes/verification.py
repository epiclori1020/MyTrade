"""Verification API endpoints."""

from uuid import UUID

from fastapi import Request

from src.dependencies.auth import authenticated_router
from src.dependencies.error_handler import handle_service_errors
from src.dependencies.rate_limit import limiter
from src.routes.helpers import sanitize_error_message
from src.services.verification import run_verification

router = authenticated_router(prefix="/api", tags=["verification"])


@router.post("/verify/{analysis_id}")
@limiter.limit("50/minute")
@handle_service_errors(service_name="Verification service")
def verify_claims(analysis_id: UUID, request: Request) -> dict:
    """Cross-check claims against a second data source (Alpha Vantage).

    Reads claims for the analysis, fetches AV data, and compares values.
    Writes verification_results rows for cross-checked claims.
    """
    user_id = request.state.user["id"]
    result = run_verification(str(analysis_id), user_id)

    return {
        "status": result.status,
        "analysis_id": result.analysis_id,
        "summary": result.summary,
        "results_count": result.results_count,
        "error_message": sanitize_error_message(result.error_message, "Verification"),
    }
