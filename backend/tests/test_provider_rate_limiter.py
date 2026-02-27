"""Tests for ProviderRateLimiter sliding window."""

import time
from unittest.mock import patch

from src.services.provider_rate_limiter import ProviderRateLimiter


class TestProviderRateLimiter:
    def test_within_limit_does_not_block(self):
        """Calls within the limit should return immediately."""
        limiter = ProviderRateLimiter(max_calls=5, window_seconds=60.0)
        start = time.monotonic()
        for _ in range(5):
            limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # Should be near-instant

    def test_blocks_when_limit_reached(self):
        """Should block when max_calls is reached until window slides."""
        limiter = ProviderRateLimiter(max_calls=2, window_seconds=0.2)
        limiter.acquire()
        limiter.acquire()
        # Third call should block until first slot expires (~0.2s)
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.15  # Should have waited close to 0.2s

    def test_window_expiry_releases_slots(self):
        """After the window expires, all slots should be available again."""
        limiter = ProviderRateLimiter(max_calls=2, window_seconds=0.1)
        limiter.acquire()
        limiter.acquire()
        time.sleep(0.15)  # Wait for window to expire
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05  # Should be immediate
