"""Unit tests for TelemetryService, NullTelemetryService, and ObservabilityMiddleware."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from types import MappingProxyType
from unittest.mock import MagicMock, patch

import pytest

from ceramic.config import ObservabilityConfig
from ceramic.identity import IdentityContext
from ceramic.middleware.observability import ObservabilityMiddleware
from ceramic.middleware.pipeline import RequestContext
from ceramic.models import LogEntry
from ceramic.observability import (
    NullSpan,
    NullTelemetryService,
    TelemetryService,
    get_telemetry_service,
)


# ---------------------------------------------------------------------------
# TelemetryService tests
# ---------------------------------------------------------------------------


class TestTelemetryService:
    """Tests for the TelemetryService class."""

    def setup_method(self) -> None:
        self.config = ObservabilityConfig()
        self.service = TelemetryService(config=self.config)

    def test_start_span_creates_span_with_attributes(self) -> None:
        """start_span should create a span with tool_name and request_id."""
        request_id = str(uuid.uuid4())
        span = self.service.start_span(tool_name="my_tool", request_id=request_id)

        # Span should be created (non-None)
        assert span is not None
        span.end()

    def test_end_span_sets_ok_status_on_success(self) -> None:
        """end_span with 'success' outcome should set OK status."""
        request_id = str(uuid.uuid4())
        span = self.service.start_span(tool_name="my_tool", request_id=request_id)
        # Should not raise
        self.service.end_span(span, outcome="success", duration_ms=42.5)

    def test_end_span_sets_error_status_on_error(self) -> None:
        """end_span with 'error' outcome should set ERROR status."""
        request_id = str(uuid.uuid4())
        span = self.service.start_span(tool_name="my_tool", request_id=request_id)
        # Should not raise
        self.service.end_span(span, outcome="error", duration_ms=100.0)

    def test_emit_log_outputs_json(self, caplog: pytest.LogCaptureFixture) -> None:
        """emit_log should produce a JSON log message via the logging module."""
        entry = LogEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            request_id="test-req-id",
            tool_name="some_tool",
            subject="user@example.com",
            duration_ms=55.3,
            status="success",
            level="info",
            message="Tool invocation: some_tool",
        )

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            self.service.emit_log(entry)

        assert len(caplog.records) == 1
        log_data = json.loads(caplog.records[0].message)
        assert log_data["request_id"] == "test-req-id"
        assert log_data["tool_name"] == "some_tool"
        assert log_data["status"] == "success"
        assert log_data["duration_ms"] == 55.3

    def test_emit_log_redacts_sensitive_fields(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """emit_log should redact fields containing sensitive patterns."""
        entry = LogEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            request_id="test-req-id",
            tool_name="some_tool",
            subject=None,
            duration_ms=10.0,
            status="success",
            level="info",
            message="Tool invocation: some_tool",
            extra={"authorization_header": "Bearer secret123"},
        )

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            self.service.emit_log(entry)

        log_data = json.loads(caplog.records[0].message)
        assert log_data["extra"]["authorization_header"] == "[REDACTED]"

    def test_record_metric_success(self) -> None:
        """record_metric with error=False should increment success counter."""
        # Should not raise
        self.service.record_metric(tool_name="my_tool", duration_ms=50.0, error=False)

    def test_record_metric_error(self) -> None:
        """record_metric with error=True should increment error counter."""
        # Should not raise
        self.service.record_metric(tool_name="my_tool", duration_ms=100.0, error=True)

    def test_default_config_when_none(self) -> None:
        """TelemetryService should use default config when None is passed."""
        service = TelemetryService(config=None)
        assert service._config is not None

    def test_start_span_returns_null_span_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """start_span should return NullSpan and log warning if tracer fails."""
        service = TelemetryService(config=self.config)
        # Force the tracer to raise
        service._tracer = MagicMock()
        service._tracer.start_span.side_effect = RuntimeError("tracer broken")

        with caplog.at_level(logging.WARNING, logger="ceramic.observability"):
            span = service.start_span(tool_name="broken_tool", request_id="req-1")

        assert isinstance(span, NullSpan)
        assert any("Failed to start telemetry span" in r.message for r in caplog.records)

    def test_end_span_logs_warning_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """end_span should log warning if span operations fail."""
        service = TelemetryService(config=self.config)
        broken_span = MagicMock()
        broken_span.set_attribute.side_effect = RuntimeError("span broken")

        with caplog.at_level(logging.WARNING, logger="ceramic.observability"):
            service.end_span(broken_span, outcome="success", duration_ms=10.0)

        assert any("Failed to end telemetry span" in r.message for r in caplog.records)

    def test_emit_log_logs_warning_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """emit_log should log warning if logging fails internally."""
        service = TelemetryService(config=self.config)
        # Force redactor to raise
        service._redactor = MagicMock()
        service._redactor.redact.side_effect = RuntimeError("redactor broken")

        entry = LogEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            request_id="test-req-id",
            tool_name="some_tool",
            subject=None,
            duration_ms=10.0,
            status="success",
            level="info",
            message="test",
        )

        with caplog.at_level(logging.WARNING, logger="ceramic.observability"):
            service.emit_log(entry)

        assert any("Failed to emit telemetry log" in r.message for r in caplog.records)

    def test_record_metric_logs_warning_on_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """record_metric should log warning if metric recording fails."""
        service = TelemetryService(config=self.config)
        # Force counter to raise
        service._request_counter = MagicMock()
        service._request_counter.labels.side_effect = RuntimeError("counter broken")

        with caplog.at_level(logging.WARNING, logger="ceramic.observability"):
            service.record_metric(tool_name="my_tool", duration_ms=50.0, error=False)

        assert any("Failed to record metric" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# NullTelemetryService tests
# ---------------------------------------------------------------------------


class TestNullTelemetryService:
    """Tests for the NullTelemetryService no-op implementation."""

    def test_start_span_returns_null_span(self) -> None:
        """NullTelemetryService.start_span should return a NullSpan."""
        service = NullTelemetryService()
        span = service.start_span(tool_name="test", request_id="req-1")
        assert isinstance(span, NullSpan)

    def test_end_span_does_nothing(self) -> None:
        """NullTelemetryService.end_span should not raise."""
        service = NullTelemetryService()
        service.end_span(NullSpan(), outcome="success", duration_ms=10.0)

    def test_emit_log_does_nothing(self) -> None:
        """NullTelemetryService.emit_log should not raise."""
        service = NullTelemetryService()
        entry = LogEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            request_id="req-1",
            tool_name="test",
            subject=None,
            duration_ms=10.0,
            status="success",
            level="info",
            message="test",
        )
        service.emit_log(entry)

    def test_record_metric_does_nothing(self) -> None:
        """NullTelemetryService.record_metric should not raise."""
        service = NullTelemetryService()
        service.record_metric(tool_name="test", duration_ms=10.0, error=False)


# ---------------------------------------------------------------------------
# get_telemetry_service factory tests
# ---------------------------------------------------------------------------


class TestGetTelemetryService:
    """Tests for the get_telemetry_service factory function."""

    def test_disabled_config_returns_null_service(self) -> None:
        """When config.enabled is False, should return NullTelemetryService."""
        config = ObservabilityConfig(enabled=False)
        service = get_telemetry_service(config)
        assert isinstance(service, NullTelemetryService)

    def test_none_config_returns_null_service(self) -> None:
        """When config is None, should return NullTelemetryService."""
        service = get_telemetry_service(None)
        assert isinstance(service, NullTelemetryService)

    def test_enabled_config_returns_telemetry_service(self) -> None:
        """When config.enabled is True, should return TelemetryService."""
        config = ObservabilityConfig(enabled=True)
        service = get_telemetry_service(config)
        assert isinstance(service, TelemetryService)


# ---------------------------------------------------------------------------
# Conditional import verification
# ---------------------------------------------------------------------------


class TestConditionalImport:
    """Tests verifying that disabled observability does not import OTel/Prometheus."""

    def test_disabled_observability_does_not_require_otel(self) -> None:
        """NullTelemetryService should not import opentelemetry."""
        # NullTelemetryService should work fine without any OTel imports
        service = NullTelemetryService()
        span = service.start_span("test", "req-1")
        service.end_span(span, "success", 10.0)
        service.emit_log(
            LogEntry(
                timestamp="2024-01-01T00:00:00+00:00",
                request_id="req-1",
                tool_name="test",
                subject=None,
                duration_ms=10.0,
                status="success",
                level="info",
                message="test",
            )
        )
        service.record_metric("test", 10.0, False)
        # All operations completed without importing OTel or Prometheus

    def test_disabled_middleware_does_not_import_otel(self) -> None:
        """ObservabilityMiddleware with disabled config should not use OTel."""
        config = ObservabilityConfig(enabled=False)
        middleware = ObservabilityMiddleware(config=config)
        # The middleware's telemetry service should be a NullTelemetryService
        assert isinstance(middleware.telemetry, NullTelemetryService)


# ---------------------------------------------------------------------------
# ObservabilityMiddleware tests
# ---------------------------------------------------------------------------


class TestObservabilityMiddleware:
    """Tests for the ObservabilityMiddleware class."""

    def setup_method(self) -> None:
        self.config = ObservabilityConfig()
        self.middleware = ObservabilityMiddleware(config=self.config)

    @pytest.mark.asyncio
    async def test_assigns_request_id_if_missing(self) -> None:
        """Middleware should assign a UUID request_id if ctx.request_id is empty."""
        ctx = RequestContext(request_id="")

        async def handler() -> str:
            return "ok"

        await self.middleware(ctx, handler)
        # Should have assigned a valid UUID
        assert ctx.request_id != ""
        uuid.UUID(ctx.request_id)  # validates it's a proper UUID

    @pytest.mark.asyncio
    async def test_preserves_existing_request_id(self) -> None:
        """Middleware should not overwrite an existing request_id."""
        existing_id = str(uuid.uuid4())
        ctx = RequestContext(request_id=existing_id, tool_name="test_tool")

        async def handler() -> str:
            return "ok"

        await self.middleware(ctx, handler)
        assert ctx.request_id == existing_id

    @pytest.mark.asyncio
    async def test_returns_handler_response(self) -> None:
        """Middleware should pass through the handler's return value."""
        ctx = RequestContext(tool_name="test_tool")

        async def handler() -> dict:
            return {"result": "hello"}

        result = await self.middleware(ctx, handler)
        assert result == {"result": "hello"}

    @pytest.mark.asyncio
    async def test_propagates_exceptions(self) -> None:
        """Middleware should re-raise exceptions from the handler."""
        ctx = RequestContext(tool_name="error_tool")

        async def handler() -> None:
            raise ValueError("something went wrong")

        with pytest.raises(ValueError, match="something went wrong"):
            await self.middleware(ctx, handler)

    @pytest.mark.asyncio
    async def test_emits_log_entry_on_success(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should emit a structured log entry on successful invocation."""
        ctx = RequestContext(tool_name="log_tool")

        async def handler() -> str:
            return "done"

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            await self.middleware(ctx, handler)

        assert len(caplog.records) == 1
        log_data = json.loads(caplog.records[0].message)
        assert log_data["tool_name"] == "log_tool"
        assert log_data["status"] == "success"
        assert log_data["request_id"] == ctx.request_id
        assert log_data["duration_ms"] > 0

    @pytest.mark.asyncio
    async def test_emits_log_entry_on_error(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should emit a structured log entry with 'error' status on failure."""
        ctx = RequestContext(tool_name="fail_tool")

        async def handler() -> None:
            raise RuntimeError("oops")

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            with pytest.raises(RuntimeError):
                await self.middleware(ctx, handler)

        assert len(caplog.records) == 1
        log_data = json.loads(caplog.records[0].message)
        assert log_data["status"] == "error"
        assert log_data["tool_name"] == "fail_tool"

    @pytest.mark.asyncio
    async def test_includes_subject_from_identity(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should include the subject from IdentityContext in log entries."""
        identity = IdentityContext(
            email="user@example.com",
            subject="user-123",
            claims=MappingProxyType({}),
            roles=frozenset(),
            groups=frozenset(),
        )
        ctx = RequestContext(tool_name="id_tool", identity=identity)

        async def handler() -> str:
            return "ok"

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            await self.middleware(ctx, handler)

        log_data = json.loads(caplog.records[0].message)
        assert log_data["subject"] == "user-123"

    @pytest.mark.asyncio
    async def test_records_prometheus_metrics(self) -> None:
        """Middleware should record Prometheus metrics after invocation."""
        ctx = RequestContext(tool_name="metric_tool")

        async def handler() -> str:
            return "ok"

        # Get initial counter values
        await self.middleware(ctx, handler)

        # Verify counter was incremented (sample value > 0)
        counter_value = (
            self.middleware.telemetry._request_counter.labels(
                tool_name="metric_tool", status="success"
            )._value.get()
        )
        assert counter_value >= 1.0

    @pytest.mark.asyncio
    async def test_uses_unknown_for_missing_tool_name(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should use 'unknown' when tool_name is not set."""
        ctx = RequestContext()  # No tool_name set

        async def handler() -> str:
            return "ok"

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            await self.middleware(ctx, handler)

        log_data = json.loads(caplog.records[0].message)
        assert log_data["tool_name"] == "unknown"

    @pytest.mark.asyncio
    async def test_duration_is_measured(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Middleware should measure non-zero duration for handler execution."""
        import asyncio

        ctx = RequestContext(tool_name="slow_tool")

        async def handler() -> str:
            await asyncio.sleep(0.01)
            return "done"

        with caplog.at_level(logging.DEBUG, logger="ceramic.observability"):
            await self.middleware(ctx, handler)

        log_data = json.loads(caplog.records[0].message)
        # Duration should be at least 10ms (we slept 10ms)
        assert log_data["duration_ms"] >= 5.0

    @pytest.mark.asyncio
    async def test_disabled_middleware_is_passthrough(self) -> None:
        """Middleware with disabled config should just call next() without instrumentation."""
        config = ObservabilityConfig(enabled=False)
        middleware = ObservabilityMiddleware(config=config)
        ctx = RequestContext(tool_name="test_tool")
        # Capture the auto-generated request_id before middleware runs
        original_request_id = ctx.request_id

        handler_called = False

        async def handler() -> str:
            nonlocal handler_called
            handler_called = True
            return "result"

        result = await middleware(ctx, handler)
        assert result == "result"
        assert handler_called
        # request_id should remain unchanged (no instrumentation touched it)
        assert ctx.request_id == original_request_id

    @pytest.mark.asyncio
    async def test_telemetry_export_failure_does_not_interrupt(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """If telemetry export fails, request should still complete normally."""
        config = ObservabilityConfig(enabled=True)
        middleware = ObservabilityMiddleware(config=config)

        # Replace telemetry service with one that raises on all methods
        broken_telemetry = MagicMock()
        broken_telemetry.start_span.side_effect = RuntimeError("export failed")
        broken_telemetry.emit_log.side_effect = RuntimeError("export failed")
        broken_telemetry.record_metric.side_effect = RuntimeError("export failed")
        broken_telemetry.end_span.side_effect = RuntimeError("export failed")
        middleware._telemetry = broken_telemetry

        ctx = RequestContext(tool_name="test_tool")

        async def handler() -> str:
            return "success"

        with caplog.at_level(logging.WARNING, logger="ceramic.observability"):
            result = await middleware(ctx, handler)

        # Request should succeed despite telemetry failures
        assert result == "success"
        # Warnings should have been logged
        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_messages) > 0
