from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import app
from tests.helpers import make_test_settings


@pytest.fixture
def client():
    """FastAPI test client with mocked settings and Supabase clients.

    Patches get_settings globally so no real .env is needed,
    and patches Supabase client creation so no real connection is attempted.
    """
    app.dependency_overrides[get_settings] = make_test_settings

    with (
        patch("src.config.get_settings", return_value=make_test_settings()),
        patch("src.services.supabase.get_settings", return_value=make_test_settings()),
        patch("src.services.supabase.create_client") as mock_create,
    ):
        mock_create.return_value = None
        yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()
