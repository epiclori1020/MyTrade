"""Tests for the Supabase write retry module (src/services/supabase_retry.py).

Structure:
- Success path tests (3)           — 1st, 2nd, 3rd attempt success
- Failure / queue tests (4)        — all retries fail, queue on failure, queue flush, partial flush
- Queue management tests (4)       — overflow, get_queue_size, clear_queue, flush_queue public API
- Backoff / logging tests (4)      — sleep delays, log_error on failure, overflow, flush
- Thread safety test (1)           — concurrent writes don't corrupt queue state
"""

import threading
from unittest.mock import MagicMock, call, patch

import pytest

from src.services.supabase_retry import (
    clear_queue,
    flush_queue,
    get_queue_size,
    supabase_write_with_retry,
)


# ---------------------------------------------------------------------------
# Autouse fixture — guarantees a clean queue for every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_queue():
    """Clear the in-memory write queue before and after every test."""
    clear_queue()
    yield
    clear_queue()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _always_succeed():
    """A write_fn that never raises."""


def _always_fail():
    """A write_fn that always raises."""
    raise RuntimeError("DB unavailable")


# ---------------------------------------------------------------------------
# 1. Success path tests
# ---------------------------------------------------------------------------


class TestSuccessPath:
    @patch("src.services.supabase_retry.time.sleep")
    def test_success_on_first_attempt(self, mock_sleep):
        """write_fn succeeds immediately — returns True, no sleep."""
        write_fn = MagicMock()

        result = supabase_write_with_retry(write_fn, description="test write")

        assert result is True
        write_fn.assert_called_once()
        mock_sleep.assert_not_called()

    @patch("src.services.supabase_retry.time.sleep")
    def test_success_on_second_attempt(self, mock_sleep):
        """write_fn fails once then succeeds — returns True, one sleep."""
        write_fn = MagicMock(side_effect=[RuntimeError("transient"), None])

        result = supabase_write_with_retry(write_fn, description="test write")

        assert result is True
        assert write_fn.call_count == 2
        # One sleep between attempt 1 and attempt 2 (BASE_DELAY * 2^0 = 1s)
        mock_sleep.assert_called_once_with(1.0)

    @patch("src.services.supabase_retry.time.sleep")
    def test_success_on_third_attempt(self, mock_sleep):
        """write_fn fails twice then succeeds — returns True, two sleeps."""
        write_fn = MagicMock(
            side_effect=[RuntimeError("err1"), RuntimeError("err2"), None]
        )

        result = supabase_write_with_retry(write_fn, description="test write")

        assert result is True
        assert write_fn.call_count == 3
        # Two sleeps: 1s (2^0) then 2s (2^1)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


# ---------------------------------------------------------------------------
# 2. Failure / queue tests
# ---------------------------------------------------------------------------


class TestFailureAndQueue:
    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_all_retries_fail_returns_false(self, mock_sleep, mock_log_error):
        """write_fn fails 3 times — returns False and item is queued."""
        write_fn = MagicMock(side_effect=RuntimeError("DB down"))

        result = supabase_write_with_retry(write_fn, description="failing write")

        assert result is False
        assert write_fn.call_count == 3

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_all_retries_fail_queues_item(self, mock_sleep, mock_log_error):
        """write_fn fails 3 times — item is placed in the queue."""
        write_fn = MagicMock(side_effect=RuntimeError("DB down"))

        assert get_queue_size() == 0
        supabase_write_with_retry(write_fn, description="failing write")

        assert get_queue_size() == 1

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_queue_flushed_on_next_success(self, mock_sleep, mock_log_error):
        """After queuing a failed write, the next successful write flushes it."""
        fail_fn = MagicMock(side_effect=RuntimeError("DB down"))
        succeed_fn = MagicMock()

        # First call: fail all retries — item is queued
        supabase_write_with_retry(fail_fn, description="queued write")
        assert get_queue_size() == 1

        # Allow the queued fn to succeed during flush
        fail_fn.side_effect = None

        # Second call: succeeds — triggers internal _flush_queue()
        result = supabase_write_with_retry(succeed_fn, description="flushing write")

        assert result is True
        assert get_queue_size() == 0
        # The queued fn should have been called during flush (3 retries + 1 flush)
        assert fail_fn.call_count == 4

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_queue_flush_partial(self, mock_sleep, mock_log_error):
        """Flush removes only items that succeed; failing items remain queued."""
        always_fail_fn = MagicMock(side_effect=RuntimeError("still down"))
        will_succeed_fn = MagicMock()

        # Queue two items: one will fail during flush, one will succeed
        for fn in (always_fail_fn, will_succeed_fn):
            fn.side_effect = [RuntimeError("DB down")] * 3
            supabase_write_with_retry(fn, description="queued item")

        assert get_queue_size() == 2

        # Reset side_effects for flush:
        # always_fail_fn continues to fail; will_succeed_fn now succeeds
        always_fail_fn.side_effect = RuntimeError("still down")
        will_succeed_fn.side_effect = None

        # Trigger flush via a fresh successful write
        trigger_fn = MagicMock()
        supabase_write_with_retry(trigger_fn, description="trigger flush")

        # One item flushed successfully, one remains
        assert get_queue_size() == 1


# ---------------------------------------------------------------------------
# 3. Queue management tests
# ---------------------------------------------------------------------------


class TestQueueManagement:
    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_queue_overflow_drops_oldest(self, mock_sleep, mock_log_error):
        """Exceeding MAX_QUEUE_SIZE (100) drops the oldest item."""
        from src.services.supabase_retry import MAX_QUEUE_SIZE

        # Fill the queue to capacity using a sentinel to track the oldest item
        sentinel_fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
        supabase_write_with_retry(sentinel_fn, description="sentinel (oldest)")

        for i in range(MAX_QUEUE_SIZE - 1):
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            supabase_write_with_retry(fn, description=f"item {i}")

        assert get_queue_size() == MAX_QUEUE_SIZE

        # Add one more — should trigger overflow, dropping the oldest (sentinel)
        overflow_fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
        supabase_write_with_retry(overflow_fn, description="overflow item")

        # Queue stays at MAX_QUEUE_SIZE (oldest dropped, new item added)
        assert get_queue_size() == MAX_QUEUE_SIZE

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_get_queue_size_returns_correct_count(self, mock_sleep, mock_log_error):
        """get_queue_size() accurately reflects the number of queued items."""
        assert get_queue_size() == 0

        for i in range(3):
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            supabase_write_with_retry(fn, description=f"item {i}")

        assert get_queue_size() == 3

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_clear_queue_empties_queue(self, mock_sleep, mock_log_error):
        """clear_queue() removes all items from the queue."""
        for i in range(5):
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            supabase_write_with_retry(fn, description=f"item {i}")

        assert get_queue_size() == 5
        clear_queue()
        assert get_queue_size() == 0

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_flush_queue_public_api_returns_flushed_count(
        self, mock_sleep, mock_log_error
    ):
        """flush_queue() returns the count of successfully flushed items."""
        # Queue 3 items
        fns = []
        for i in range(3):
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            supabase_write_with_retry(fn, description=f"item {i}")
            fns.append(fn)

        assert get_queue_size() == 3

        # Reset side_effects so all 3 succeed during flush
        for fn in fns:
            fn.side_effect = None

        count = flush_queue()

        assert count == 3
        assert get_queue_size() == 0


# ---------------------------------------------------------------------------
# 4. Backoff and logging tests
# ---------------------------------------------------------------------------


class TestBackoffAndLogging:
    @patch("src.services.supabase_retry.time.sleep")
    def test_backoff_delays_are_correct(self, mock_sleep):
        """sleep is called with 1s then 2s between the three attempts."""
        write_fn = MagicMock(side_effect=RuntimeError("DB down"))

        with patch("src.services.supabase_retry.log_error"):
            supabase_write_with_retry(write_fn, description="test")

        # Two sleeps: between attempt 1→2 and attempt 2→3 (no sleep after final failure)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)  # BASE_DELAY * 2^0
        mock_sleep.assert_any_call(2.0)  # BASE_DELAY * 2^1

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_log_error_called_on_total_failure(self, mock_sleep, mock_log_error):
        """log_error is called with write_retry_failed when all retries are exhausted."""
        write_fn = MagicMock(side_effect=RuntimeError("DB down"))

        supabase_write_with_retry(write_fn, description="critical write")

        mock_log_error.assert_any_call(
            "supabase_queue",
            "write_retry_failed",
            "Write failed after 3 retries: critical write",
        )

    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_log_error_called_on_queue_overflow(self, mock_sleep, mock_log_error):
        """log_error is called with queue_overflow when the queue exceeds MAX_QUEUE_SIZE."""
        from src.services.supabase_retry import MAX_QUEUE_SIZE

        # Fill the queue to capacity
        for _ in range(MAX_QUEUE_SIZE):
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            supabase_write_with_retry(fn, description="filler")

        mock_log_error.reset_mock()

        # One more item triggers overflow
        overflow_fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
        supabase_write_with_retry(overflow_fn, description="overflow item")

        overflow_calls = [
            c for c in mock_log_error.call_args_list if c.args[1] == "queue_overflow"
        ]
        assert len(overflow_calls) == 1

    @patch("src.services.supabase_retry.logger")
    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_logger_info_called_on_successful_flush(self, mock_sleep, mock_log_error, mock_logger):
        """logger.info is called on successful flush; log_error is NOT called with queue_flushed."""
        # Queue one item
        fail_fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
        supabase_write_with_retry(fail_fn, description="queued item")

        # Reset so it succeeds during flush
        fail_fn.side_effect = None

        # Trigger flush via a new successful write
        trigger_fn = MagicMock()
        mock_log_error.reset_mock()
        mock_logger.reset_mock()
        supabase_write_with_retry(trigger_fn, description="trigger")

        # logger.info must be called with flush message
        info_calls = [
            c for c in mock_logger.info.call_args_list
            if "Flushed" in str(c)
        ]
        assert len(info_calls) >= 1

        # log_error must NOT be called with "queue_flushed"
        flush_error_calls = [
            c for c in mock_log_error.call_args_list if len(c.args) > 1 and c.args[1] == "queue_flushed"
        ]
        assert len(flush_error_calls) == 0


# ---------------------------------------------------------------------------
# 5. Thread safety test
# ---------------------------------------------------------------------------


class TestThreadSafety:
    @patch("src.services.supabase_retry.log_error")
    @patch("src.services.supabase_retry.time.sleep")
    def test_concurrent_writes_do_not_corrupt_queue(self, mock_sleep, mock_log_error):
        """Concurrent failing writes from multiple threads each queue exactly one item.

        This validates that the threading.Lock in _enqueue and _flush_queue
        prevents race conditions from corrupting the deque.
        """
        num_threads = 20
        results: list[bool] = []
        lock = threading.Lock()

        def failing_write():
            fn = MagicMock(side_effect=[RuntimeError("DB down")] * 3)
            result = supabase_write_with_retry(fn, description="concurrent write")
            with lock:
                results.append(result)

        threads = [threading.Thread(target=failing_write) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Every write should have returned False (all failed)
        assert len(results) == num_threads
        assert all(r is False for r in results)

        # Each thread queued exactly one item, so queue size == num_threads
        assert get_queue_size() == num_threads
