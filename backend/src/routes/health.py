from datetime import datetime, timezone

from fastapi import APIRouter

from src.services.supabase import check_db_health

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """Public health endpoint. No auth, no rate limit.

    Always returns HTTP 200 so Railway does not restart the container
    during a Supabase outage. The body indicates actual health status.
    """
    db_ok = check_db_health()

    return {
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
