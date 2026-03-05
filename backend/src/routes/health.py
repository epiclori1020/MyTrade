from datetime import datetime, timezone

from fastapi import APIRouter, Response

from src.services.supabase import check_db_health

router = APIRouter()


@router.get("/health")
def health_check(response: Response) -> dict:
    """Public health endpoint. No auth, no rate limit.

    Returns 200 if database is healthy, 503 if unreachable.
    """
    db_ok = check_db_health()
    if not db_ok:
        response.status_code = 503
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
