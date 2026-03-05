"""Tests for the admin authorization dependency (src/dependencies/admin.py).

Covers:
- Admin user passes
- Non-admin user is rejected (403)
- Empty ADMIN_USER_IDS = fail-closed (no one is admin)
- Multiple admin IDs with whitespace
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.dependencies.admin import require_admin


def _make_request(user_id: str) -> MagicMock:
    """Create a mock Request with request.state.user set."""
    request = MagicMock()
    request.state.user = {"id": user_id}
    return request


def _make_settings(admin_user_ids: str) -> MagicMock:
    """Create a mock Settings with admin_user_id_list computed from the string."""
    settings = MagicMock()
    settings.admin_user_id_list = [
        uid.strip() for uid in admin_user_ids.split(",") if uid.strip()
    ]
    return settings


class TestRequireAdmin:
    @patch("src.dependencies.admin.get_settings")
    def test_admin_user_passes(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings("user-abc,user-def")
        request = _make_request("user-abc")

        # Should not raise
        require_admin(request)

    @patch("src.dependencies.admin.get_settings")
    def test_non_admin_user_gets_403(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings("user-abc,user-def")
        request = _make_request("user-intruder")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(request)

        assert exc_info.value.status_code == 403
        assert "Admin access required" in exc_info.value.detail

    @patch("src.dependencies.admin.get_settings")
    def test_empty_admin_ids_blocks_everyone(self, mock_get_settings):
        """Fail-closed: empty ADMIN_USER_IDS means no one is admin."""
        mock_get_settings.return_value = _make_settings("")
        request = _make_request("any-user-id")

        with pytest.raises(HTTPException) as exc_info:
            require_admin(request)

        assert exc_info.value.status_code == 403

    @patch("src.dependencies.admin.get_settings")
    def test_whitespace_in_admin_ids_is_trimmed(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings("  user-abc , user-def  ")
        request = _make_request("user-def")

        # Should not raise — whitespace is stripped
        require_admin(request)

    @patch("src.dependencies.admin.get_settings")
    def test_single_admin_id_works(self, mock_get_settings):
        mock_get_settings.return_value = _make_settings("only-admin")
        request = _make_request("only-admin")

        # Should not raise
        require_admin(request)
