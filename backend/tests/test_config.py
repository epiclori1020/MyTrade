"""Tests for application configuration (src/config.py)."""

import pytest

from src.config import Settings


class TestCorsOriginList:
    """T-034: CORS wildcard guard — allow_credentials=True requires explicit origins."""

    _REQUIRED = {
        "supabase_url": "https://x.supabase.co",
        "supabase_anon_key": "anon-key",
        "supabase_service_role_key": "service-key",
    }

    def test_wildcard_rejected(self):
        s = Settings(cors_origins="*", **self._REQUIRED)
        with pytest.raises(ValueError, match="wildcard"):
            s.cors_origin_list

    def test_wildcard_pattern_rejected(self):
        s = Settings(cors_origins="*.example.com", **self._REQUIRED)
        with pytest.raises(ValueError, match="wildcard"):
            s.cors_origin_list

    def test_wildcard_in_url_rejected(self):
        s = Settings(cors_origins="http://*.example.com", **self._REQUIRED)
        with pytest.raises(ValueError, match="wildcard"):
            s.cors_origin_list

    def test_explicit_origins_accepted(self):
        s = Settings(
            cors_origins="http://localhost:3000,https://mytrade.vercel.app",
            **self._REQUIRED,
        )
        result = s.cors_origin_list
        assert result == ["http://localhost:3000", "https://mytrade.vercel.app"]

    def test_single_origin_accepted(self):
        s = Settings(cors_origins="http://localhost:3000", **self._REQUIRED)
        assert s.cors_origin_list == ["http://localhost:3000"]

    def test_empty_entries_filtered(self):
        s = Settings(cors_origins="http://localhost:3000,,  ,", **self._REQUIRED)
        assert s.cors_origin_list == ["http://localhost:3000"]
