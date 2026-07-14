"""Built-in middleware placeholders for the Ceramic framework.

Each class accepts its relevant config section and implements the
MiddlewareCallable protocol. These are placeholder implementations that
simply forward to the next middleware — real logic will be added in later tasks.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ceramic.middleware.pipeline import RequestContext


class ObservabilityMiddleware:
    """Observability middleware: spans, metrics, structured logging, and redaction.

    Delegates to the full implementation in ceramic.middleware.observability.
    If observability is disabled, acts as a passthrough without importing
    telemetry libraries.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        # Determine if observability is enabled
        self._enabled = getattr(config, "enabled", True) if config else True

        if self._enabled:
            from ceramic.middleware.observability import (
                ObservabilityMiddleware as _RealObsMiddleware,
            )

            self._impl = _RealObsMiddleware(config=config)
        else:
            self._impl = None

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        if self._impl is not None:
            return await self._impl(ctx, next)
        # Disabled: passthrough without importing telemetry libraries
        return await next()


class SessionMiddleware:
    """Session middleware: restores sessions or creates new ones after auth.

    Delegates to the full implementation in ceramic.middleware.session.
    If sessions are disabled, acts as a passthrough.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self._enabled = getattr(config, "enabled", True) if config else True

        if self._enabled:
            from ceramic.middleware.session import (
                SessionMiddleware as _RealSessionMiddleware,
            )

            self._impl = _RealSessionMiddleware(session_config=config)
        else:
            self._impl = None

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        if self._impl is not None:
            return await self._impl(ctx, next)
        return await next()


class AuthenticationMiddleware:
    """Authentication middleware: validates/refreshes token, populates identity.

    This is a thin wrapper that delegates to the full implementation in
    ceramic.middleware.authentication for backward-compatible instantiation
    from config sections (which pass a single `config` argument).
    """

    def __init__(self, config: Any, ssl_context: Any = None) -> None:
        from ceramic.middleware.authentication import (
            AuthenticationMiddleware as _RealAuthMiddleware,
        )

        self.config = config
        self._impl = _RealAuthMiddleware(auth_config=config, ssl_context=ssl_context)

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        return await self._impl(ctx, next)
