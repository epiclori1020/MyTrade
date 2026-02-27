from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.config import Settings, get_settings
from src.main import app


def _test_settings() -> Settings:
    """Settings override for tests. No real env vars needed."""
    return Settings(
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test-anon-key",
        supabase_service_role_key="test-service-role-key",
        cors_origins="http://localhost:3000",
    )


@pytest.fixture
def client():
    """FastAPI test client with mocked settings and Supabase clients.

    Patches get_settings globally so no real .env is needed,
    and patches Supabase client creation so no real connection is attempted.
    """
    app.dependency_overrides[get_settings] = _test_settings

    with (
        patch("src.config.get_settings", return_value=_test_settings()),
        patch("src.services.supabase.get_settings", return_value=_test_settings()),
        patch("src.services.supabase.create_client") as mock_create,
    ):
        mock_create.return_value = None
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
