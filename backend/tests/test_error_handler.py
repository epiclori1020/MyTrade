"""Tests for the error-handler decorator (src/dependencies/error_handler.py)."""

import pytest
from fastapi import HTTPException

from src.dependencies.error_handler import handle_service_errors
from src.services.exceptions import (
    BrokerError,
    BudgetExhaustedError,
    CircuitBreakerOpenError,
    ConfigurationError,
    PreconditionError,
)


class TestHandleServiceErrors:
    def test_success_passes_through(self):
        @handle_service_errors(service_name="Test")
        def fn():
            return {"ok": True}

        assert fn() == {"ok": True}

    def test_http_exception_passes_through(self):
        @handle_service_errors(service_name="Test")
        def fn():
            raise HTTPException(status_code=403, detail="forbidden")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "forbidden"

    def test_precondition_error_default_400(self):
        @handle_service_errors(service_name="Test")
        def fn():
            raise PreconditionError("missing data")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 400
        assert "missing data" in exc_info.value.detail

    def test_precondition_error_custom_404(self):
        @handle_service_errors(service_name="Trade", precondition_status=404)
        def fn():
            raise PreconditionError("trade not found")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 404

    def test_budget_exhausted_503(self):
        @handle_service_errors(service_name="Test")
        def fn():
            raise BudgetExhaustedError()

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 503
        assert "budget" in exc_info.value.detail.lower()

    def test_circuit_breaker_503(self):
        @handle_service_errors(service_name="Test")
        def fn():
            raise CircuitBreakerOpenError("alpaca")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 503
        assert "circuit breaker" in exc_info.value.detail.lower()

    def test_broker_error_502(self):
        @handle_service_errors(service_name="Test")
        def fn():
            raise BrokerError("alpaca", "Connection failed")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 502

    def test_configuration_error_503(self):
        @handle_service_errors(service_name="Analysis service")
        def fn():
            raise ConfigurationError("missing API key")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 503
        assert "not configured" in exc_info.value.detail

    def test_generic_exception_503_no_leak(self):
        @handle_service_errors(service_name="Analysis service")
        def fn():
            raise RuntimeError("internal secret error")

        with pytest.raises(HTTPException) as exc_info:
            fn()
        assert exc_info.value.status_code == 503
        assert "temporarily unavailable" in exc_info.value.detail
        assert "internal secret" not in exc_info.value.detail

    def test_preserves_function_name(self):
        @handle_service_errors(service_name="Test")
        def my_endpoint():
            pass

        assert my_endpoint.__name__ == "my_endpoint"

    def test_passes_args_and_kwargs(self):
        @handle_service_errors(service_name="Test")
        def fn(a, b, c=3):
            return a + b + c

        assert fn(1, 2, c=10) == 13
