from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse


def _get_rate_limit_key(request: Request) -> str:
    """Extract rate limit key from the request.

    Uses the authenticated user_id if available (set by auth dependency),
    falls back to client IP for unauthenticated requests.
    """
    user = getattr(request.state, "user", None)
    if user and isinstance(user, dict) and "id" in user:
        return user["id"]
    # Behind a reverse proxy (Railway), request.client may be the proxy IP.
    # For production: configure Starlette's ProxyHeadersMiddleware to read
    # X-Forwarded-For, or switch to a trusted header-based key.
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_get_rate_limit_key)


def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Consistent JSON response for 429 Too Many Requests."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests. Please try again later.",
            "status_code": 429,
        },
    )
