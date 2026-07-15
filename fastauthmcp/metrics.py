"""Prometheus-compatible HTTP endpoint for metrics.

Exposes an ASGI application that serves Prometheus metrics at a configurable
path and port. Uses conditional loading: if observability is disabled and
no registry is available, the endpoint returns an empty response.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from fastauthmcp.config import ObservabilityConfig

logger = logging.getLogger("fastauthmcp.metrics")


class MetricsExporter:
    """Prometheus-compatible HTTP endpoint for metrics.

    Creates an ASGI application that responds to GET requests at the configured
    metrics path with Prometheus-format output. Non-matching paths return 404.

    Prometheus client library is imported lazily only when the endpoint is hit,
    supporting conditional observability loading.

    Args:
        config: ObservabilityConfig with metrics_path and metrics_port settings.
            If None, uses defaults ("/metrics" on port 9090).
    """

    def __init__(self, config: ObservabilityConfig | None = None) -> None:
        self._config = config or ObservabilityConfig()
        self._metrics_path = self._config.metrics_path
        self._metrics_port = self._config.metrics_port

    @property
    def metrics_path(self) -> str:
        """The configured metrics endpoint path."""
        return self._metrics_path

    @property
    def metrics_port(self) -> int:
        """The configured metrics endpoint port."""
        return self._metrics_port

    def get_app(self) -> Callable[..., Any]:
        """Return an ASGI application that serves the metrics endpoint.

        The ASGI app responds to HTTP GET requests at the configured metrics_path
        with Prometheus-format metrics output. All other paths return 404.
        Only HTTP scope type is supported.

        If the Prometheus registry is not available (observability disabled),
        returns an empty 200 response.

        Returns:
            An async callable conforming to the ASGI interface.
        """
        metrics_path = self._metrics_path

        async def app(
            scope: dict[str, Any],
            receive: Callable[..., Any],
            send: Callable[..., Any],
        ) -> None:
            if scope["type"] != "http":
                return

            path = scope.get("path", "")
            method = scope.get("method", "GET")

            if path == metrics_path and method == "GET":
                try:
                    from prometheus_client import generate_latest

                    from fastauthmcp.observability import get_registry

                    registry = get_registry()
                    if registry is not None:
                        body = generate_latest(registry)
                    else:
                        body = b""
                except Exception as exc:
                    logger.warning("Failed to generate metrics: %s", exc)
                    body = b""

                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [
                            [b"content-type", b"text/plain; charset=utf-8"],
                            [b"content-length", str(len(body)).encode()],
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": body,
                    }
                )
            else:
                body = b"Not Found"
                await send(
                    {
                        "type": "http.response.start",
                        "status": 404,
                        "headers": [
                            [b"content-type", b"text/plain; charset=utf-8"],
                            [b"content-length", str(len(body)).encode()],
                        ],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": body,
                    }
                )

        return app
