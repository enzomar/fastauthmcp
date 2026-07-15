"""Trimmed observability tests (10 tests).

Verifies: request ID assigned, span created, metrics recorded,
log format correct, disabled mode passthrough.
"""

from __future__ import annotations

import json
import logging
import uuid
from unittest.mock import MagicMock

import pytest

from fastauthmcp.config import ObservabilityConfig
from fastauthmcp.middleware.observability import ObservabilityMiddleware
from fastauthmcp.middleware.pipeline import RequestContext
from fastauthmcp.models import LogEntry
from fastauthmcp.observability import (
    NullSpan,
    NullTelemetryService,
    TelemetryService,
    get_telemetry_service,
)


# ---------------------------------------------------------------------------
# TelemetryService core
# ---------------------------------------------------------------------------


class TestTelemetryService:
    def setup_method(self):
        self.service = TelemetryService(config=ObservabilityConfig())

    def test_start_span_creates_span(self):
        """start_span returns a non-None span."""
        span = self.service.start_span(
            tool_name="my_tool", request_id=str(uuid.uuid4())
        )
        assert span is not None
        span.end()

    def test_record_metric_success(self):
        """record_metric with error=False does not raise."""
        self.service.record_metric(tool_name="my_tool", duration_ms=50.0, error=False)

    def test_emit_log_json_format(self, caplog):
        """emit_log produces valid JSON with expected fields."""
        entry = LogEntry(
            timestamp="2024-01-01T00:00:00+00:00",
            request_id="req-123",
            tool_name="some_tool",
            subject="user@example.com",
            duration_ms=55.3,
            status="success",
            level="info",
            message="Tool invocation: some_tool",
        )
        with caplog.at_level(logging.DEBUG, logger="fastauthmcp.observability"):
            self.service.emit_log(entry)

        log_data = json.loads(caplog.records[0].message)
        assert log_data["request_id"] == "req-123"
        assert log_data["tool_name"] == "some_tool"
        assert log_data["status"] == "success"
        assert log_data["duration_ms"] == 55.3


# ---------------------------------------------------------------------------
# NullTelemetryService / factory
# ---------------------------------------------------------------------------


class TestDisabledMode:
    def test_disabled_config_returns_null_service(self):
        """Disabled config gives NullTelemetryService."""
        service = get_telemetry_service(ObservabilityConfig(enabled=False))
        assert isinstance(service, NullTelemetryService)

    def test_null_service_start_span_returns_null_span(self):
        """NullTelemetryService.start_span returns NullSpan."""
        service = NullTelemetryService()
        assert isinstance(service.start_span("test", "req-1"), NullSpan)


# ---------------------------------------------------------------------------
# ObservabilityMiddleware
# ---------------------------------------------------------------------------


class TestObservabilityMiddleware:
    def setup_method(self):
        self.middleware = ObservabilityMiddleware(config=ObservabilityConfig())

    @pytest.mark.asyncio
    async def test_assigns_request_id(self):
        """Middleware assigns a UUID request_id when missing."""
        ctx = RequestContext(request_id="")

        async def handler():
            return "ok"

        await self.middleware(ctx, handler)
        assert ctx.request_id != ""
        uuid.UUID(ctx.request_id)  # validates UUID format

    @pytest.mark.asyncio
    async def test_emits_log_on_success(self, caplog):
        """Structured JSON log emitted with tool_name and status=success."""
        ctx = RequestContext(tool_name="log_tool")

        async def handler():
            return "done"

        with caplog.at_level(logging.DEBUG, logger="fastauthmcp.observability"):
            await self.middleware(ctx, handler)

        log_data = json.loads(caplog.records[0].message)
        assert log_data["tool_name"] == "log_tool"
        assert log_data["status"] == "success"

    @pytest.mark.asyncio
    async def test_records_prometheus_metrics(self):
        """Prometheus counter is incremented after invocation."""
        ctx = RequestContext(tool_name="metric_tool")

        async def handler():
            return "ok"

        await self.middleware(ctx, handler)

        counter_value = self.middleware.telemetry._request_counter.labels(
            tool_name="metric_tool", status="success"
        )._value.get()
        assert counter_value >= 1.0

    @pytest.mark.asyncio
    async def test_disabled_middleware_passthrough(self):
        """Disabled middleware just calls next() without instrumentation."""
        middleware = ObservabilityMiddleware(config=ObservabilityConfig(enabled=False))
        ctx = RequestContext(tool_name="test_tool")
        original_id = ctx.request_id

        called = False

        async def handler():
            nonlocal called
            called = True
            return "result"

        result = await middleware(ctx, handler)
        assert result == "result"
        assert called
        assert ctx.request_id == original_id

    @pytest.mark.asyncio
    async def test_telemetry_failure_does_not_interrupt_request(self, caplog):
        """Broken telemetry doesn't prevent request completion."""
        middleware = ObservabilityMiddleware(config=ObservabilityConfig(enabled=True))
        broken = MagicMock()
        broken.start_span.side_effect = RuntimeError("export failed")
        broken.emit_log.side_effect = RuntimeError("export failed")
        broken.record_metric.side_effect = RuntimeError("export failed")
        broken.end_span.side_effect = RuntimeError("export failed")
        middleware._telemetry = broken

        ctx = RequestContext(tool_name="test_tool")

        async def handler():
            return "success"

        with caplog.at_level(logging.WARNING, logger="fastauthmcp.observability"):
            result = await middleware(ctx, handler)

        assert result == "success"
