"""Sliding window rate limiter for external API providers.

Uses threading.Lock for thread safety. Callers block until a slot
is available — safe because FastAPI runs sync handlers in a threadpool.
"""

import threading
import time
from collections import deque

from src.services.exceptions import RateLimitError


class ProviderRateLimiter:
    """Sliding window rate limiter.

    Tracks timestamps of recent calls in a deque. When the window is full,
    .acquire() blocks until the oldest call slides out of the window,
    up to max_wait_seconds. Raises RateLimitError if the wait would exceed
    the timeout (prevents threadpool exhaustion).
    """

    def __init__(self, max_calls: int, window_seconds: float, max_wait_seconds: float = 30.0):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.max_wait_seconds = max_wait_seconds
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a rate limit slot is available, then record the call.

        Raises RateLimitError if waiting would exceed max_wait_seconds.
        """
        deadline = time.monotonic() + self.max_wait_seconds

        while True:
            with self._lock:
                now = time.monotonic()
                # Evict expired timestamps
                while self._timestamps and (now - self._timestamps[0]) >= self.window_seconds:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.max_calls:
                    self._timestamps.append(now)
                    return
                # Calculate wait time until the oldest slot expires
                wait = self.window_seconds - (now - self._timestamps[0])

            if time.monotonic() + wait > deadline:
                raise RateLimitError("internal", "Rate limit wait timeout exceeded")

            # Sleep outside the lock to avoid blocking other threads
            time.sleep(max(wait, 0.01))


# Module-level singletons — one per provider
# Finnhub free tier: 60 calls/min, we use 55 for safety margin
finnhub_limiter = ProviderRateLimiter(max_calls=55, window_seconds=60.0, max_wait_seconds=30.0)

# Alpha Vantage free tier: 25 calls/day — short timeout since we don't want to block threads
alpha_vantage_limiter = ProviderRateLimiter(max_calls=25, window_seconds=86400.0, max_wait_seconds=5.0)
