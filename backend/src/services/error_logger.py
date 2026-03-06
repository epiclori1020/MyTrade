"""Best-effort error logging to the error_log table.

If the DB write fails, falls back to Python logger — never masks
the original error that triggered the logging.
"""

import logging

from src.services.supabase import get_supabase_admin

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 2000


def log_error(
    component: str,
    error_type: str,
    message: str,
    retry_count: int = 0,
    analysis_id: str | None = None,
) -> None:
    """Write an error entry to the error_log table.

    Best-effort: if DB write fails, logs to Python logger instead.
    """
    truncated = message[:MAX_MESSAGE_LENGTH] if len(message) > MAX_MESSAGE_LENGTH else message

    row = {
        "component": component,
        "error_type": error_type,
        "message": truncated,
        "retry_count": retry_count,
        "resolved": False,
    }
    if analysis_id:
        row["analysis_id"] = analysis_id

    try:
        admin = get_supabase_admin()
        admin.table("error_log").insert(row).execute()
    except Exception:  # Broad catch: error logger must never raise
        logger.error(
            "Failed to write to error_log (component=%s, type=%s): %s",
            component, error_type, truncated,
            exc_info=True,
        )
