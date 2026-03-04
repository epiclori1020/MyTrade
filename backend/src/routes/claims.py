"""Claims API endpoints."""

import logging
from uuid import UUID

from fastapi import HTTPException, Request

from src.dependencies.auth import authenticated_router
from src.dependencies.rate_limit import limiter
from src.routes.helpers import sanitize_error_message
from src.services.claim_extraction import run_claim_extraction
from src.services.exceptions import BudgetExhaustedError, ConfigurationError, PreconditionError
from src.services.supabase import get_supabase_admin

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
    except BudgetExhaustedError:
        raise HTTPException(
            status_code=503,
            detail="Monthly API budget exhausted. Try again next month.",
        )
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
        "error_message": sanitize_error_message(result.error_message, "Claim extraction"),
    }


@router.get("/claims/{analysis_id}")
@limiter.limit("50/minute")
def get_claims(analysis_id: UUID, request: Request) -> dict:
    """Get claims with verification results for a completed analysis.

    Uses service_role (Option B RLS) with explicit ownership check
    via analysis_runs.user_id.

    Returns 404 if analysis not found or belongs to another user.
    Returns 503 for server errors.
    """
    user_id = request.state.user["id"]

    try:
        admin = get_supabase_admin()

        # Verify ownership via analysis_runs
        run_resp = (
            admin.table("analysis_runs")
            .select("id")
            .eq("id", str(analysis_id))
            .eq("user_id", user_id)
            .execute()
        )
        if not run_resp.data:
            raise HTTPException(status_code=404, detail="Analysis not found")

        # Fetch claims
        claims_resp = (
            admin.table("claims")
            .select("*")
            .eq("analysis_id", str(analysis_id))
            .execute()
        )

        # Fetch verification results for all claims
        claim_ids = [c["id"] for c in (claims_resp.data or [])]
        verifications: dict = {}
        if claim_ids:
            vr_resp = (
                admin.table("verification_results")
                .select("*")
                .in_("claim_id", claim_ids)
                .execute()
            )
            for v in (vr_resp.data or []):
                verifications[v["claim_id"]] = v

        # Merge claims with verification results
        result = []
        for c in (claims_resp.data or []):
            result.append({**c, "verification": verifications.get(c["id"])})

    except HTTPException:
        raise
    except ConfigurationError as exc:
        logger.error("Configuration error getting claims: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Claims service temporarily unavailable",
        )
    except Exception as exc:
        logger.error(
            "Unexpected error getting claims for %s: %s",
            analysis_id, exc, exc_info=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Claims service temporarily unavailable",
        )

    return {"claims": result}
