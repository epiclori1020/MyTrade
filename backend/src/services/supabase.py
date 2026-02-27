import logging

from supabase import Client, create_client

from src.config import get_settings

logger = logging.getLogger(__name__)

# Module-level clients: lazy-initialized on first access
_supabase_client: Client | None = None
_supabase_admin: Client | None = None


def get_supabase_client() -> Client:
    """Supabase client with anon key. Uses RLS — pass user JWT for row-level access."""
    global _supabase_client
    if _supabase_client is None:
        settings = get_settings()
        _supabase_client = create_client(settings.supabase_url, settings.supabase_anon_key)
    return _supabase_client


def get_supabase_admin() -> Client:
    """Supabase client with service_role key. Bypasses RLS entirely.

    Use ONLY in backend services with explicit user_id validation.
    Never expose this client or its key in responses.
    """
    global _supabase_admin
    if _supabase_admin is None:
        settings = get_settings()
        _supabase_admin = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_admin


def check_db_health() -> bool:
    """Check database connectivity by querying a known table.

    This is a regular (sync) function — NOT async.
    supabase-py's REST client is synchronous. FastAPI automatically
    runs sync route handlers in a threadpool, so this won't block
    the event loop.

    Returns True if the DB is reachable, False otherwise.
    """
    try:
        admin = get_supabase_admin()
        admin.table("user_policy").select("id").limit(1).execute()
        return True
    except Exception:
        logger.warning("DB health check failed", exc_info=True)
        return False
