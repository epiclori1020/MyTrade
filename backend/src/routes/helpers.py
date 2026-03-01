"""Shared helpers for route handlers."""


def sanitize_error_message(error_message: str | None, service_name: str) -> str | None:
    """Return a client-safe error message without internal details.

    Maps internal error strings to user-friendly messages parameterized
    by service_name (e.g. "Analysis", "Claim extraction").

    Used by route handlers to prevent leaking implementation details
    like API keys, SDK errors, or stack traces.
    """
    if error_message is None:
        return None
    lower = error_message.lower()
    if "timeout" in lower:
        return f"{service_name} timed out. Please try again."
    if "api error" in lower:
        return f"{service_name} service error. Please try again later."
    if any(kw in lower for kw in ("parse", "schema", "extraction_failed")):
        return f"{service_name} produced invalid output. Please try again."
    if any(kw in lower for kw in ("db", "database")):
        return f"Failed to save results. Please try again."
    return f"{service_name} failed. Please try again."
