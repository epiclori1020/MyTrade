"""Supabase write retry with in-memory fallback queue.

When a Supabase write fails after 3 retries, the operation is queued
in memory. A background flush attempts to write queued items on the
next successful write.

MVP limitation: The in-memory queue is lost on server restart.
"""

import logging
import threading
import time
from collections import deque
from collections.abc import Callable

from src.services.error_logger import log_error

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0  # 1s, 2s, 4s (shorter than retry.py's 2s/4s/8s for DB writes)
MAX_QUEUE_SIZE = 100

_write_queue: deque[Callable] = deque()
_queue_lock = threading.Lock()


def supabase_write_with_retry(
    write_fn: Callable, description: str
) -> bool:
    """Execute write_fn with up to 3 retries, queue on failure.

    Args:
        write_fn: Zero-argument callable that performs the DB write.
        description: Human-readable description for logging.

    Returns:
        True if write succeeded (possibly after retries), False if queued.
    """
    last_error: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            write_fn()
            # Success — try to flush queued items
            _flush_queue()
            return True
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Supabase write retry %d/%d for %s: %s — retrying in %.1fs",
                    attempt, MAX_RETRIES, description, exc, delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "Supabase write failed after %d retries for %s: %s",
                    MAX_RETRIES, description, exc,
                )

    # All retries exhausted — queue the write
    _enqueue(write_fn, description)
    log_error(
        "supabase_queue",
        "write_retry_failed",
        f"Write failed after {MAX_RETRIES} retries: {description}",
    )
    return False


def _enqueue(write_fn: Callable, description: str) -> None:
    """Add a failed write to the in-memory queue."""
    with _queue_lock:
        if len(_write_queue) >= MAX_QUEUE_SIZE:
            _write_queue.popleft()  # Drop oldest
            logger.error("Supabase write queue overflow — dropped oldest item")
            log_error(
                "supabase_queue",
                "queue_overflow",
                f"Queue full ({MAX_QUEUE_SIZE}), dropped oldest. New item: {description}",
            )
        _write_queue.append(write_fn)
        logger.info("Queued failed write: %s (queue size: %d)", description, len(_write_queue))


def _flush_queue() -> int:
    """Try to flush queued writes. Returns count of successfully flushed items."""
    flushed = 0
    with _queue_lock:
        remaining: deque[Callable] = deque()
        while _write_queue:
            fn = _write_queue.popleft()
            try:
                fn()
                flushed += 1
            except Exception:
                remaining.append(fn)
        _write_queue.extend(remaining)

    if flushed > 0:
        logger.info("Flushed %d queued writes (%d remaining)", flushed, len(remaining))
    return flushed


def flush_queue() -> int:
    """Public interface for flushing the queue. Returns count of flushed items."""
    return _flush_queue()


def get_queue_size() -> int:
    """Return current queue size. For monitoring/testing."""
    with _queue_lock:
        return len(_write_queue)


def clear_queue() -> None:
    """Clear the queue. For test teardown."""
    with _queue_lock:
        _write_queue.clear()
