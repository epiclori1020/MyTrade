from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.services.supabase import get_supabase_client

security = HTTPBearer()


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

        user_data = {"id": str(user.id), "email": user.email}
        request.state.user = user_data
        return user_data

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )
