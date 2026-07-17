"""Observability service: OpenTelemetry spans, Prometheus metrics, and structured logging.

Supports conditional loading: if observability is disabled, OpenTelemetry and
Prometheus libraries are NOT imported or initialized. Use the factory function
``get_telemetry_service(config)`` to obtain the appropriate implementation.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from fastauthmcp.config import ObservabilityConfig
from fastauthmcp.models import LogEntry
from fastauthmcp.security import LogRedactor

logger = logging.getLogger("fastauthmcp.observability")


class TelemetryServiceProtocol(Protocol):
    """Protocol for telemetry service implementations."""

    def start_span(self, tool_name: str, request_id: str) -> Any: ...
    def end_span(self, span: Any, outcome: str, duration_ms: float) -> None: ...
    def emit_log(self, entry: LogEntry) -> None: ...
    def record_metric(self, tool_name: str, duration_ms: float, error: bool) -> None: ...


class NullSpan:
    """A no-op span used when observability is disabled or on failure."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def end(self) -> None:
        pass


class NullTelemetryService:
    """No-op telemetry service used when observability is disabled.

    Does not import or initialize OpenTelemetry or Prometheus libraries.
    All methods are safe no-ops that return immediately.
    """

    def __init__(self) -> None:
        self._redactor = LogRedactor()

    def start_span(self, tool_name: str, request_id: str) -> NullSpan:
        """Return a no-op span."""
        return NullSpan()

    def end_span(self, span: Any, outcome: str, duration_ms: float) -> None:
        """No-op: do nothing."""
        pass

    def emit_log(self, entry: LogEntry) -> None:
        """No-op: do nothing."""
        pass

    def record_metric(self, tool_name: str, duration_ms: float, error: bool) -> None:
        """No-op: do nothing."""
        pass


class TelemetryService:
    """Manages OpenTelemetry spans, Prometheus metrics, and structured logging.

    This service is the single point of integration for all observability
    concerns. It wraps the OpenTelemetry tracer, Prometheus metrics, and
    Python's logging module behind a consistent interface.

    OpenTelemetry and Prometheus libraries are imported lazily inside __init__
    to support conditional loading (requirement 6.5). All telemetry operations

    are wrapped in try/except to ensure export failures never interrupt request
    processing (requirement 6.6).
    """

    _shared_registry: Any
    _shared_request_counter: Any
    _shared_error_counter: Any
    _shared_latency_histogram: Any

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self._config = config or ObservabilityConfig()
        self._redactor = LogRedactor()

        # Lazy import: OpenTelemetry
        from opentelemetry import trace
        from opentelemetry.trace import Tracer

        self._trace_module = trace
        self._tracer: Tracer = trace.get_tracer("fastauthmcp")

        # Lazy import: Prometheus
        from prometheus_client import CollectorRegistry, Counter, Histogram

        # Use a module-level registry cached on the class to avoid duplicate
        # registration across multiple TelemetryService instances.
        if not hasattr(TelemetryService, "_shared_registry"):
            TelemetryService._shared_registry = CollectorRegistry()
            TelemetryService._shared_request_counter = Counter(
                "fastauthmcp_tool_requests_total",
                "Total number of MCP tool invocations",
                ["tool_name", "status"],
                registry=TelemetryService._shared_registry,
            )
            TelemetryService._shared_error_counter = Counter(
                "fastauthmcp_tool_errors_total",
                "Total number of MCP tool errors",
                ["tool_name"],
                registry=TelemetryService._shared_registry,
            )
            TelemetryService._shared_latency_histogram = Histogram(
                "fastauthmcp_tool_duration_milliseconds",
                "Latency of MCP tool invocations in milliseconds",
                ["tool_name"],
                buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
                registry=TelemetryService._shared_registry,
            )

        self._request_counter = TelemetryService._shared_request_counter
        self._error_counter = TelemetryService._shared_error_counter
        self._latency_histogram = TelemetryService._shared_latency_histogram

    @property
    def tracer(self) -> Any:
        """Return the underlying OpenTelemetry tracer."""
        return self._tracer

    def start_span(self, tool_name: str, request_id: str) -> Any:
        """Start a new OpenTelemetry span for a tool invocation.

        Args:
            tool_name: The name of the MCP tool being invoked.
            request_id: The UUID request ID for this request.

        Returns:
            The started span, or a NullSpan if span creation fails.
        """
        try:
            span = self._tracer.start_span(
                name=f"fastauthmcp.tool.{tool_name}",
                attributes=self._redactor.redact(
                    {
                        "fastauthmcp.tool_name": tool_name,
                        "fastauthmcp.request_id": request_id,
                    }
                ),
            )
            return span
        except Exception as exc:
            logger.warning("Failed to start telemetry span for tool '%s': %s", tool_name, exc)
            return NullSpan()

    def end_span(self, span: Any, outcome: str, duration_ms: float) -> None:
        """End an OpenTelemetry span with outcome attributes.

        Args:
            span: The span to end.
            outcome: The outcome string ("success" or "error").
            duration_ms: The duration of the tool invocation in milliseconds.
        """
        try:
            from opentelemetry.trace import StatusCode

            attributes = self._redactor.redact(
                {
                    "fastauthmcp.outcome": outcome,
                    "fastauthmcp.duration_ms": duration_ms,
                }
            )
            for key, value in attributes.items():
                span.set_attribute(key, value)

            if outcome == "error":
                span.set_status(StatusCode.ERROR, "Tool invocation failed")
            else:
                span.set_status(StatusCode.OK)

            span.end()
        except Exception as exc:
            logger.warning("Failed to end telemetry span: %s", exc)

    def emit_log(self, entry: LogEntry) -> None:
        """Emit a structured JSON log entry via Python's logging module.

        The log entry is redacted of sensitive fields before being emitted.
        If logging fails, the failure is silently logged and request processing
        continues.

        Args:
            entry: The structured log entry to emit.
        """
        try:
            log_data: dict[str, Any] = {
                "timestamp": entry.timestamp,
                "request_id": entry.request_id,
                "tool_name": entry.tool_name,
                "subject": entry.subject,
                "duration_ms": entry.duration_ms,
                "status": entry.status,
                "level": entry.level,
                "message": entry.message,
            }
            if entry.extra:
                log_data["extra"] = entry.extra

            # Redact sensitive fields
            redacted = self._redactor.redact(log_data)

            # Determine log level
            level = getattr(logging, entry.level.upper(), logging.INFO)
            logger.log(level, json.dumps(redacted))
        except Exception as exc:
            logger.warning("Failed to emit telemetry log entry: %s", exc)

    def record_metric(self, tool_name: str, duration_ms: float, error: bool) -> None:
        """Record Prometheus metrics for a tool invocation.

        Records request count (by tool name and status), error count,
        and latency histogram. If metric recording fails, logs a warning
        and continues.

        Args:
            tool_name: The name of the MCP tool.
            duration_ms: The duration of the invocation in milliseconds.
            error: Whether the invocation resulted in an error.
        """
        try:
            status = "error" if error else "success"
            self._request_counter.labels(tool_name=tool_name, status=status).inc()
            if error:
                self._error_counter.labels(tool_name=tool_name).inc()
            self._latency_histogram.labels(tool_name=tool_name).observe(duration_ms)
        except Exception as exc:
            logger.warning("Failed to record metric for tool '%s': %s", tool_name, exc)


def get_telemetry_service(
    config: ObservabilityConfig | None = None,
) -> TelemetryServiceProtocol:
    """Factory function: return the appropriate telemetry service.

    If config is None or config.enabled is False, returns a NullTelemetryService
    that does not import or initialize any telemetry libraries.

    If config.enabled is True, returns a full TelemetryService with OTel and
    Prometheus support.

    Args:
        config: The observability configuration section, or None.

    Returns:
        Either a TelemetryService (enabled) or NullTelemetryService (disabled).
    """
    if config is None or not config.enabled:
        return NullTelemetryService()
    return TelemetryService(config=config)


def get_registry() -> Any:
    """Return the shared Prometheus CollectorRegistry, or None if not initialized.

    This replaces the old module-level ``_registry`` export. It returns the
    registry only if TelemetryService has been instantiated (i.e., observability
    is enabled). Otherwise returns None.
    """
    return getattr(TelemetryService, "_shared_registry", None)
