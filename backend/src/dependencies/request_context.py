"""Request context propagation via ContextVar.

Provides request_id and user_id to all log records without explicit passing.
The RequestContextMiddleware sets values per request. The RequestContextFilter
injects them into every log record automatically.

Usage in main.py:
    app.add_middleware(BaseHTTPMiddleware, dispatch=request_context_dispatch)
"""

import logging
import re
import uuid
from contextvars import ContextVar

from starlette.requests import Request
from starlette.responses import Response

# ContextVars — set per request, read by logging filter
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
user_id_var: ContextVar[str] = ContextVar("user_id", default="-")


class RequestContextFilter(logging.Filter):
    """Logging filter that injects request_id and user_id into every record.

    Attach to root logger — all child loggers inherit the filter.
    Works with any formatter (plain text or JSON).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()  # type: ignore[attr-defined]
        record.user_id = user_id_var.get()  # type: ignore[attr-defined]
        return True


async def request_context_dispatch(request: Request, call_next) -> Response:
    """Middleware dispatch that sets request_id and user_id ContextVars.

    Must be added via: app.add_middleware(BaseHTTPMiddleware, dispatch=request_context_dispatch)

    Reads X-Request-ID header if present (for distributed tracing),
    otherwise generates a new UUID.
    """
    rid_header = request.headers.get("x-request-id")
    if rid_header and re.fullmatch(r"[\w\-]{1,64}", rid_header):
        rid = rid_header
    else:
        rid = uuid.uuid4().hex[:12]
    request_id_var.set(rid)

    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response
