"""Tests for request context propagation and structured logging."""

import logging

from src.dependencies.request_context import (
    RequestContextFilter,
    request_id_var,
    user_id_var,
)


class TestRequestContextFilter:
    def test_filter_injects_default_values(self):
        """Without middleware, request_id and user_id are '-'."""
        f = RequestContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        f.filter(record)
        assert record.request_id == "-"
        assert record.user_id == "-"

    def test_filter_injects_set_values(self):
        """When ContextVars are set, filter injects them."""
        token_rid = request_id_var.set("test-req-123")
        token_uid = user_id_var.set("user-456")
        try:
            f = RequestContextFilter()
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="hello", args=(), exc_info=None,
            )
            f.filter(record)
            assert record.request_id == "test-req-123"
            assert record.user_id == "user-456"
        finally:
            request_id_var.reset(token_rid)
            user_id_var.reset(token_uid)


class TestRequestContextMiddleware:
    def test_response_has_request_id_header(self, auth_client):
        """Middleware adds X-Request-ID to response."""
        resp = auth_client.get("/health")
        assert "x-request-id" in resp.headers

    def test_custom_request_id_forwarded(self, auth_client):
        """If X-Request-ID is sent, it's echoed back."""
        resp = auth_client.get(
            "/health", headers={"X-Request-ID": "my-custom-id"}
        )
        assert resp.headers.get("x-request-id") == "my-custom-id"

    def test_generated_request_id_is_hex(self, auth_client):
        """Auto-generated request IDs are 12-char hex strings."""
        resp = auth_client.get("/health")
        rid = resp.headers.get("x-request-id", "")
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_invalid_request_id_replaced(self, auth_client):
        """Malicious X-Request-ID is rejected and replaced with generated ID."""
        resp = auth_client.get(
            "/health", headers={"X-Request-ID": "x" * 100}
        )
        rid = resp.headers.get("x-request-id", "")
        # Too long — should be replaced with 12-char hex
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_request_id_with_special_chars_replaced(self, auth_client):
        """X-Request-ID with control characters is rejected."""
        resp = auth_client.get(
            "/health", headers={"X-Request-ID": "test\ninjection"}
        )
        rid = resp.headers.get("x-request-id", "")
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)
