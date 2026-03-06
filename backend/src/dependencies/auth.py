from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.dependencies.request_context import user_id_var
from src.services.supabase import get_supabase_client

security = HTTPBearer()


def authenticated_router(**kwargs) -> APIRouter:
    """APIRouter with get_current_user applied to all routes.

    Use this for all authenticated endpoints (Step 4+).
    Public endpoints (like /health) should use plain APIRouter().
    """
    deps = list(kwargs.pop("dependencies", []))
    deps.append(Depends(get_current_user))
    return APIRouter(dependencies=deps, **kwargs)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Validate JWT token via Supabase Auth and return the authenticated user.

    Uses supabase.auth.get_user(token) which verifies the JWT against
    Supabase's auth server. This is the simplest approach for MVP (1 user).
    Can be swapped for PyJWT/JWKS validation later without changing route signatures.

    Returns:
        {"id": "<user-uuid>", "email": "<user-email>"}

    Raises:
        HTTPException(401) if the token is invalid, expired, or missing.
    """
    try:
        client = get_supabase_client()
        response = client.auth.get_user(credentials.credentials)
        user = response.user

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token",
            )

        if not user.email:
            raise HTTPException(
                status_code=401,
                detail="User email required",
            )

        user_data = {"id": str(user.id), "email": user.email}
        request.state.user = user_data
        user_id_var.set(user_data["id"])
        return user_data

    except HTTPException:
        raise
    except Exception:  # Broad catch: any auth failure = 401
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )
