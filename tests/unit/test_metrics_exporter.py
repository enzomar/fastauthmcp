"""Unit tests for the Prometheus MetricsExporter ASGI app."""

from __future__ import annotations

import pytest

from ceramic.config import ObservabilityConfig
from ceramic.metrics import MetricsExporter
from ceramic.observability import TelemetryService, get_registry


# Ensure the TelemetryService has been instantiated at least once so the
# shared registry and metrics exist.
_ensure_service = TelemetryService(config=ObservabilityConfig())

# Access the shared metrics for test assertions
_registry = get_registry()
_request_counter = TelemetryService._shared_request_counter
_error_counter = TelemetryService._shared_error_counter
_latency_histogram = TelemetryService._shared_latency_histogram


class MockSend:
    """Collects ASGI send events for assertion."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def __call__(self, event: dict) -> None:
        self.events.append(event)


async def mock_receive() -> dict:
    """Minimal ASGI receive callable."""
    return {"type": "http.request", "body": b""}


class TestMetricsExporterInit:
    """Tests for MetricsExporter initialization."""

    def test_default_config(self) -> None:
        exporter = MetricsExporter()
        assert exporter.metrics_path == "/metrics"
        assert exporter.metrics_port == 9090

    def test_custom_config(self) -> None:
        config = ObservabilityConfig(metrics_path="/prom", metrics_port=8080)
        exporter = MetricsExporter(config=config)
        assert exporter.metrics_path == "/prom"
        assert exporter.metrics_port == 8080

    def test_get_app_returns_callable(self) -> None:
        exporter = MetricsExporter()
        app = exporter.get_app()
        assert callable(app)


class TestMetricsASGIApp:
    """Tests for the ASGI app returned by MetricsExporter.get_app()."""

    @pytest.fixture
    def exporter(self) -> MetricsExporter:
        return MetricsExporter()

    @pytest.fixture
    def app(self, exporter: MetricsExporter):
        return exporter.get_app()

    async def test_get_metrics_returns_200(self, app) -> None:
        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        assert len(send.events) == 2
        assert send.events[0]["type"] == "http.response.start"
        assert send.events[0]["status"] == 200
        assert send.events[1]["type"] == "http.response.body"

    async def test_metrics_content_type(self, app) -> None:
        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        headers = dict(send.events[0]["headers"])
        assert headers[b"content-type"] == b"text/plain; charset=utf-8"

    async def test_metrics_body_is_prometheus_format(self, app) -> None:
        # Record a metric so there's something to report
        _request_counter.labels(tool_name="test_tool", status="success").inc()

        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        body = send.events[1]["body"]
        assert isinstance(body, bytes)
        text = body.decode("utf-8")
        # Prometheus format includes HELP and TYPE lines
        assert "ceramic_tool_requests_total" in text

    async def test_non_metrics_path_returns_404(self, app) -> None:
        scope = {"type": "http", "path": "/other", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        assert send.events[0]["status"] == 404
        assert send.events[1]["body"] == b"Not Found"

    async def test_non_get_method_returns_404(self, app) -> None:
        scope = {"type": "http", "path": "/metrics", "method": "POST"}
        send = MockSend()

        await app(scope, mock_receive, send)

        assert send.events[0]["status"] == 404

    async def test_non_http_scope_does_nothing(self, app) -> None:
        scope = {"type": "websocket", "path": "/metrics"}
        send = MockSend()

        await app(scope, mock_receive, send)

        assert len(send.events) == 0

    async def test_custom_metrics_path(self) -> None:
        config = ObservabilityConfig(metrics_path="/custom/metrics", metrics_port=9090)
        exporter = MetricsExporter(config=config)
        app = exporter.get_app()

        # Custom path should return 200
        scope = {"type": "http", "path": "/custom/metrics", "method": "GET"}
        send = MockSend()
        await app(scope, mock_receive, send)
        assert send.events[0]["status"] == 200

        # Default path should return 404
        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()
        await app(scope, mock_receive, send)
        assert send.events[0]["status"] == 404

    async def test_content_length_header_matches_body(self, app) -> None:
        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        headers = dict(send.events[0]["headers"])
        content_length = int(headers[b"content-length"].decode())
        body_length = len(send.events[1]["body"])
        assert content_length == body_length

    async def test_metrics_includes_all_metric_families(self, app) -> None:
        # Record some metrics
        _request_counter.labels(tool_name="exporter_test", status="success").inc()
        _error_counter.labels(tool_name="exporter_test").inc()
        _latency_histogram.labels(tool_name="exporter_test").observe(42.0)

        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        text = send.events[1]["body"].decode("utf-8")
        assert "ceramic_tool_requests_total" in text
        assert "ceramic_tool_errors_total" in text
        assert "ceramic_tool_duration_milliseconds" in text

    async def test_uses_shared_registry(self, app) -> None:
        """Ensure the ASGI app uses the same registry from observability module."""
        from prometheus_client import generate_latest

        from ceramic.observability import get_registry

        # The output from the app should match generate_latest with our registry
        scope = {"type": "http", "path": "/metrics", "method": "GET"}
        send = MockSend()

        await app(scope, mock_receive, send)

        app_output = send.events[1]["body"]
        registry = get_registry()
        registry_output = generate_latest(registry)
        assert app_output == registry_output
