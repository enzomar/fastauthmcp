"""Observability middleware: spans, metrics, structured logging, and redaction.

Supports conditional loading: if observability is disabled, the middleware
acts as a passthrough (just calls next()) without importing telemetry libraries.
If telemetry export fails at runtime, the middleware logs a warning and continues
processing the request without interruption.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from fastauthmcp.config import ObservabilityConfig
from fastauthmcp.middleware.pipeline import RequestContext
from fastauthmcp.models import LogEntry
from fastauthmcp.observability import get_telemetry_service
from fastauthmcp.security import LogRedactor

logger = logging.getLogger("fastauthmcp.observability")


class ObservabilityMiddleware:
    """Middleware that instruments tool invocations with tracing, metrics, and logging.

    Behavior:
    - If observability is disabled (config.enabled is False), acts as a passthrough.
    - Before: Ensures request_id is set on ctx, starts an OTel span.
    - After: Records duration and outcome, emits a structured JSON log,
      records Prometheus metrics, and ends the span.
    - Uses LogRedactor to prevent sensitive values from appearing in spans/logs.
    - If any telemetry operation fails, logs a warning and continues processing.
    """

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self._config = config or ObservabilityConfig()
        self._enabled = self._config.enabled
        self._telemetry = get_telemetry_service(self._config)
        self._redactor = LogRedactor()

    @property
    def telemetry(self) -> Any:
        """Expose the underlying TelemetryService for testing/inspection."""
        return self._telemetry

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Execute the observability middleware.

        If observability is disabled, simply calls next() without any
        instrumentation overhead.

        If enabled:
        1. Ensure request_id is present on the context.
        2. Start an OpenTelemetry span with the tool name.
        3. Invoke the next middleware/handler and measure duration.
        4. Record duration, outcome, emit structured log, record metric.
        5. End the span with outcome attributes.

        All telemetry operations are wrapped in try/except to ensure that
        export failures never interrupt request processing.
        """
        # If observability is disabled, passthrough immediately
        if not self._enabled:
            return await next()

        # 1. Ensure request_id is assigned
        if not ctx.request_id:
            ctx.request_id = str(uuid.uuid4())

        tool_name = ctx.tool_name or "unknown"

        # 2. Start span (safe — returns NullSpan on failure)
        from fastauthmcp.observability import NullSpan

        try:
            span = self._telemetry.start_span(
                tool_name=tool_name, request_id=ctx.request_id
            )
        except Exception as exc:
            logger.warning("Failed to start observability span: %s", exc)
            span = NullSpan()

        # 3. Execute handler and measure duration
        start_time = time.perf_counter()
        outcome = "success"
        error_occurred = False
        response: Any = None

        try:
            response = await next()
        except Exception:
            outcome = "error"
            error_occurred = True
            raise
        finally:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000.0

            # Determine subject from identity if available
            subject: str | None = None
            if ctx.identity is not None:
                subject = ctx.identity.subject

            # 4. Emit structured JSON log entry (safe — catches exceptions internally)
            try:
                log_entry = LogEntry(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    request_id=ctx.request_id,
                    tool_name=tool_name,
                    subject=subject,
                    duration_ms=duration_ms,
                    status=outcome,  # type: ignore[arg-type]
                    level="error" if error_occurred else "info",
                    message=f"Tool invocation: {tool_name}",
                )
                self._telemetry.emit_log(log_entry)
            except Exception as exc:
                logger.warning("Failed to emit observability log: %s", exc)

            # 5. Record Prometheus metric (safe — catches exceptions internally)
            try:
                self._telemetry.record_metric(
                    tool_name=tool_name,
                    duration_ms=duration_ms,
                    error=error_occurred,
                )
            except Exception as exc:
                logger.warning("Failed to record observability metric: %s", exc)

            # 6. End the OTel span (safe — catches exceptions internally)
            try:
                self._telemetry.end_span(
                    span=span,
                    outcome=outcome,
                    duration_ms=duration_ms,
                )
            except Exception as exc:
                logger.warning("Failed to end observability span: %s", exc)

        return response
