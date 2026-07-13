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

    def __init__(
        self,
        config: Any,
        role_claim_path: str = "realm_access.roles",
        group_claim_path: str = "groups",
    ) -> None:
        from ceramic.middleware.authentication import (
            AuthenticationMiddleware as _RealAuthMiddleware,
        )

        self.config = config
        self._impl = _RealAuthMiddleware(
            auth_config=config,
            role_claim_path=role_claim_path,
            group_claim_path=group_claim_path,
        )

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        return await self._impl(ctx, next)


class AuthorizationMiddleware:
    """Authorization middleware: evaluates decorator and YAML policies.

    This is a thin wrapper that delegates to the full implementation in
    ceramic.middleware.authorization for backward-compatible instantiation
    from config sections (which pass a single `config` argument).
    """

    def __init__(self, config: Any, tool_functions: dict | None = None) -> None:
        from ceramic.middleware.authorization import (
            AuthorizationMiddleware as _RealAuthzMiddleware,
        )

        self.config = config
        self._tool_functions = tool_functions or {}
        self._impl = _RealAuthzMiddleware(
            authz_config=config, tool_functions=self._tool_functions
        )

    def set_tool_functions(self, tool_functions: dict) -> None:
        """Update the tool functions mapping (called after tools are registered)."""
        self._tool_functions = tool_functions
        self._impl._tool_functions = tool_functions

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        return await self._impl(ctx, next)
