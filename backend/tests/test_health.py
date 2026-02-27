from unittest.mock import MagicMock, patch

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from slowapi.errors import RateLimitExceeded

from src.config import get_settings
from src.dependencies.auth import get_current_user
from src.dependencies.rate_limit import limiter
from src.main import app
from tests.helpers import make_test_settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client(db_healthy: bool = True) -> TestClient:
    """Create a test client with DB health mocked to the given value."""
    app.dependency_overrides[get_settings] = make_test_settings

    patcher_settings = patch("src.services.supabase.get_settings", return_value=make_test_settings())
    patcher_create = patch("src.services.supabase.create_client")
    # Patch where check_db_health is USED (health.py), not where it's defined
    patcher_health = patch("src.routes.health.check_db_health", return_value=db_healthy)

    patcher_settings.start()
    patcher_create.start()
    patcher_health.start()

    client = TestClient(app, raise_server_exceptions=False)

    # Attach patchers so we can clean up
    client._patchers = [patcher_settings, patcher_create, patcher_health]
    return client


def _cleanup_client(client: TestClient):
    for p in getattr(client, "_patchers", []):
        p.stop()
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Health — DB connected
# ---------------------------------------------------------------------------

def test_health_db_connected():
    client = _make_client(db_healthy=True)
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "timestamp" in data
    finally:
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 2. Health — DB disconnected
# ---------------------------------------------------------------------------

def test_health_db_disconnected():
    client = _make_client(db_healthy=False)
    try:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
        assert "timestamp" in data
    finally:
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 3. Health — no auth required
# ---------------------------------------------------------------------------

def test_health_no_auth_required():
    client = _make_client(db_healthy=True)
    try:
        # No Authorization header sent
        response = client.get("/health")
        assert response.status_code == 200
    finally:
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 4. 404 returns consistent JSON
# ---------------------------------------------------------------------------

def test_404_returns_consistent_json():
    client = _make_client()
    try:
        response = client.get("/nonexistent-route")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
    finally:
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 5. Error response has required fields
# ---------------------------------------------------------------------------

def test_error_response_has_required_fields():
    client = _make_client()
    try:
        response = client.get("/nonexistent-route")
        assert response.status_code == 404
        data = response.json()
        assert "status_code" in data
        assert "error" in data
        assert "detail" in data
    finally:
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 6. Protected endpoint requires auth
# ---------------------------------------------------------------------------

def test_protected_endpoint_requires_auth():
    """A protected route (using Depends(get_current_user)) should return 401/403
    when no Authorization header is provided."""

    # Register a temporary protected route for this test
    @app.get("/test-protected")
    def _protected_route(user: dict = Depends(get_current_user)):
        return {"user": user}

    client = _make_client()
    try:
        response = client.get("/test-protected")
        # HTTPBearer returns 401 or 403 depending on FastAPI version
        assert response.status_code in (401, 403)
    finally:
        # Remove the temporary route
        app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-protected"]
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 7. Rate limit returns 429
# ---------------------------------------------------------------------------

def test_rate_limit_returns_429():
    """A rate-limited route should eventually return 429."""

    # Register a temporary rate-limited route
    @app.get("/test-rate-limited")
    @limiter.limit("2/minute")
    def _rate_limited_route(request: Request):
        return {"ok": True}

    client = _make_client()
    try:
        # First 2 requests should succeed
        for _ in range(2):
            resp = client.get("/test-rate-limited")
            assert resp.status_code == 200

        # Third request should be rate-limited
        resp = client.get("/test-rate-limited")
        assert resp.status_code == 429
        data = resp.json()
        assert data["error"] == "rate_limit_exceeded"
        assert data["status_code"] == 429
    finally:
        app.routes[:] = [r for r in app.routes if getattr(r, "path", None) != "/test-rate-limited"]
        _cleanup_client(client)


# ---------------------------------------------------------------------------
# 8. CORS allows configured origin
# ---------------------------------------------------------------------------

def test_cors_allows_configured_origin():
    client = _make_client(db_healthy=True)
    try:
        # Preflight OPTIONS request
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    finally:
        _cleanup_client(client)
