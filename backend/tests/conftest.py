# Shared test fixtures.
# Shared helpers (e.g. make_test_settings) live in tests/helpers.py.

from unittest.mock import patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from src.config import get_settings
from src.dependencies.auth import get_current_user
from src.dependencies.rate_limit import limiter
from src.main import app
from tests.helpers import make_test_settings

FAKE_USER = {"id": "test-user-id-123", "email": "test@example.com"}


def _fake_get_current_user(request: Request) -> dict:
    """Override for get_current_user that also sets request.state.user.

    The rate limiter reads request.state.user for per-user limiting.
    A simple lambda would skip this, causing rate limiting to fall back
    to IP-based instead of user-based (wrong behavior in tests).
    """
    request.state.user = FAKE_USER
    return FAKE_USER


@pytest.fixture
def auth_client():
    """Authenticated test client with mocked Supabase and auth.

    Use this for all route tests that require authentication.
    """
    app.dependency_overrides[get_current_user] = _fake_get_current_user
    app.dependency_overrides[get_settings] = make_test_settings

    patcher_supabase = patch("src.services.supabase.create_client")
    patcher_supabase.start()

    # Patch get_settings at the admin dependency import location so that
    # require_admin() (a plain function call, not FastAPI DI) gets test settings.
    patcher_admin_settings = patch(
        "src.dependencies.admin.get_settings", return_value=make_test_settings()
    )
    patcher_admin_settings.start()

    # Default: Kill-Switch is inactive in all route tests.
    # Individual tests that need it active must apply their own
    # @patch("src.routes.<module>.is_kill_switch_active", return_value=True).
    patcher_kill_switch = patch(
        "src.routes.trades.is_kill_switch_active", return_value=False
    )
    patcher_kill_switch.start()

    # Reset rate limiter storage so tests don't share counters
    limiter.reset()

    client = TestClient(app, raise_server_exceptions=False)
    yield client

    patcher_kill_switch.stop()
    patcher_admin_settings.stop()
    patcher_supabase.stop()
    app.dependency_overrides.clear()
