"""Tests for shared route helpers (src/routes/helpers.py)."""

from src.routes.helpers import sanitize_error_message


class TestSanitizeErrorMessage:
    def test_none_returns_none(self):
        assert sanitize_error_message(None, "Analysis") is None

    def test_timeout_message(self):
        result = sanitize_error_message("API timeout after 60s", "Analysis")
        assert result == "Analysis timed out. Please try again."

    def test_api_error_message(self):
        result = sanitize_error_message(
            "API error (500): Internal server error", "Analysis"
        )
        assert result == "Analysis service error. Please try again later."

    def test_parse_error_message(self):
        result = sanitize_error_message("Parse failed: invalid JSON", "Analysis")
        assert result == "Analysis produced invalid output. Please try again."

    def test_schema_error_message(self):
        result = sanitize_error_message("Schema validation failed", "Claim extraction")
        assert result == "Claim extraction produced invalid output. Please try again."

    def test_extraction_failed_message(self):
        result = sanitize_error_message(
            "extraction_failed: all attempts", "Claim extraction"
        )
        assert result == "Claim extraction produced invalid output. Please try again."

    def test_db_error_message(self):
        result = sanitize_error_message("DB connection refused", "Claim extraction")
        assert result == "Failed to save results. Please try again."

    def test_database_error_message(self):
        result = sanitize_error_message("Database connection refused", "Analysis")
        assert result == "Failed to save results. Please try again."

    def test_unknown_error_falls_through(self):
        result = sanitize_error_message("Something unexpected happened", "Analysis")
        assert result == "Analysis failed. Please try again."

    def test_service_name_parameterized(self):
        """Different service names produce different messages."""
        analysis = sanitize_error_message("timeout", "Analysis")
        claims = sanitize_error_message("timeout", "Claim extraction")
        assert "Analysis" in analysis
        assert "Claim extraction" in claims

    def test_no_internal_details_leaked(self):
        """Sensitive details must not appear in sanitized output."""
        result = sanitize_error_message(
            "API error (500): Internal server error from anthropic SDK key=sk-ant-123",
            "Analysis",
        )
        assert "500" not in result
        assert "anthropic" not in result
        assert "SDK" not in result
        assert "sk-ant" not in result

    def test_case_insensitive_matching(self):
        assert "timed out" in sanitize_error_message("TIMEOUT", "X")
        assert "service error" in sanitize_error_message("API ERROR", "X")
