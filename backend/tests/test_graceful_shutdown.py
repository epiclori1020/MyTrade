"""Tests for graceful shutdown cleanup."""

from unittest.mock import MagicMock, patch

from src.main import _shutdown_cleanup


class TestShutdownCleanup:
    def test_flushes_retry_queue(self):
        """flush_queue is called when items are pending."""
        with (
            patch("src.services.supabase_retry.get_queue_size", return_value=3),
            patch("src.services.supabase_retry.flush_queue", return_value=2) as mock_flush,
        ):
            _shutdown_cleanup()
            mock_flush.assert_called_once()

    def test_skips_flush_when_queue_empty(self):
        """flush_queue is NOT called when queue is empty."""
        with (
            patch("src.services.supabase_retry.get_queue_size", return_value=0),
            patch("src.services.supabase_retry.flush_queue") as mock_flush,
        ):
            _shutdown_cleanup()
            mock_flush.assert_not_called()

    def test_survives_flush_error(self):
        """Shutdown must not crash if flush fails."""
        with patch(
            "src.services.supabase_retry.get_queue_size",
            side_effect=Exception("boom"),
        ):
            _shutdown_cleanup()  # Should not raise

    def test_resets_supabase_globals(self):
        """Supabase client globals are set to None after cleanup."""
        import src.services.supabase as sb_mod

        sb_mod._supabase_client = MagicMock()
        sb_mod._supabase_admin = MagicMock()
        with patch("src.services.supabase_retry.get_queue_size", return_value=0):
            _shutdown_cleanup()
        assert sb_mod._supabase_client is None
        assert sb_mod._supabase_admin is None
