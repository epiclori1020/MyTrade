"""Admin authorization dependency for privileged endpoints.

Fail-closed: empty ADMIN_USER_IDS = no admins = all admin operations blocked.
Automatic Kill-Switch triggers (evaluate) still work without admin role.
"""

from fastapi import HTTPException, Request

from src.config import get_settings


def require_admin(request: Request) -> None:
    """Verify the authenticated user is in the admin allowlist.

    Must be called AFTER authentication (request.state.user is set).
    Raises HTTPException(403) if user is not admin.
    """
    user_id = request.state.user["id"]
    settings = get_settings()

    if user_id not in settings.admin_user_id_list:
        raise HTTPException(
            status_code=403,
            detail="Admin access required",
        )
