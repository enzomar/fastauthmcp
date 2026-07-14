"""Middleware pipeline: protocols, RequestContext, and pipeline executor."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from ceramic.identity import IdentityContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hook point names supported by the middleware system
# ---------------------------------------------------------------------------

HOOK_POINTS: frozenset[str] = frozenset(
    {
        "before_request",
        "after_request",
        "before_tool",
        "after_tool",
        "on_authentication",
        "on_exception",
        "on_shutdown",
    }
)


# ---------------------------------------------------------------------------
# RequestContext — mutable per-request state carried through the pipeline
# ---------------------------------------------------------------------------


class RequestContext:
    """Mutable request-scoped state passed through the middleware pipeline."""

    __slots__ = ("identity", "session", "request_id", "tool_name", "metadata")

    def __init__(
        self,
        *,
        identity: IdentityContext | None = None,
        session: Any | None = None,
        request_id: str | None = None,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.identity = identity
        self.session = session
        self.request_id = request_id or str(uuid.uuid4())
        self.tool_name = tool_name
        self.metadata = metadata if metadata is not None else {}


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class MiddlewareCallable(Protocol):
    """A single middleware callable.

    Receives the request context and a ``next`` function. The middleware can:
    - Call ``await next()`` to pass control to the next middleware/handler.
    - Return a value directly to short-circuit the chain.
    - Raise an exception (routed to ``on_exception`` hooks).
    """

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any: ...


@runtime_checkable
class MiddlewarePlugin(Protocol):
    """Interface for plugins registered via ``app.use()`` or ceramic.yaml."""

    name: str
    hooks: dict[str, MiddlewareCallable]  # hook_name -> handler


# ---------------------------------------------------------------------------
# Pipeline executor
# ---------------------------------------------------------------------------


class MiddlewarePipeline:
    """Chains middleware callables and executes them in registration order.

    Before-hooks execute first-registered-first.  After-hooks execute in
    reverse order (last-registered-first on the way out).  Unhandled
    exceptions are routed through the ``on_exception`` hook chain.
    """

    def __init__(self) -> None:
        self._before: list[MiddlewareCallable] = []
        self._after: list[MiddlewareCallable] = []
        self._on_exception: list[MiddlewareCallable] = []

    # ------------------------------------------------------------------
    # Registration helpers
    # ------------------------------------------------------------------

    def add_before(self, middleware: MiddlewareCallable) -> None:
        """Register a before-hook middleware (executes in registration order)."""
        self._before.append(middleware)

    def add_after(self, middleware: MiddlewareCallable) -> None:
        """Register an after-hook middleware (executes in reverse registration order)."""
        self._after.append(middleware)

    def add_exception_handler(self, middleware: MiddlewareCallable) -> None:
        """Register an on_exception handler."""
        self._on_exception.append(middleware)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        ctx: RequestContext,
        handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run the full pipeline: before → handler → after.

        Parameters
        ----------
        ctx:
            The mutable request context.
        handler:
            The final callable (e.g. FastMCP delegation) invoked if no
            middleware short-circuits.

        Returns
        -------
        The response value from the handler or a short-circuiting middleware.
        If all error handling fails, returns a generic error dict.
        """
        try:
            # Build the before-middleware chain with the handler at the end.
            response = await self._run_before_chain(ctx, handler)
            # Run after-hooks in reverse registration order.
            response = await self._run_after_hooks(ctx, response)
            return response
        except Exception as exc:
            return await self._handle_exception(ctx, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_before_chain(
        self,
        ctx: RequestContext,
        handler: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Build a nested chain of before-middleware wrapping the handler."""

        async def _build_next(index: int) -> Callable[[], Awaitable[Any]]:
            """Return a next() callable for the middleware at *index*."""

            async def _next() -> Any:
                if index < len(self._before):
                    mw = self._before[index]
                    return await mw(ctx, await _build_next(index + 1))
                # End of chain — invoke the actual handler.
                return await handler()

            return _next

        # Start execution from the first middleware.
        next_fn = await _build_next(0)
        return await next_fn()

    async def _run_after_hooks(self, ctx: RequestContext, response: Any) -> Any:
        """Execute after-hooks in reverse registration order.

        Each after-hook receives ctx and a next() that simply returns the
        current response, allowing it to transform or replace the response.
        """
        current_response = response
        # Reverse order: last registered executes first on the way out.
        for mw in reversed(self._after):

            async def _make_next(resp: Any) -> Callable[[], Awaitable[Any]]:
                async def _next() -> Any:
                    return resp

                return _next

            next_fn = await _make_next(current_response)
            current_response = await mw(ctx, next_fn)
        return current_response

    async def _handle_exception(self, ctx: RequestContext, exc: Exception) -> Any:
        """Route an exception through on_exception handlers.

        If an on_exception handler itself raises, log the secondary exception
        and return a generic error response.  Exceptions must NEVER propagate
        to FastMCP.
        """
        for handler in self._on_exception:

            async def _noop() -> Any:
                return None

            try:
                # Pass the original exception via ctx.metadata so handlers
                # can inspect it.
                ctx.metadata["exception"] = exc
                result = await handler(ctx, _noop)
                if result is not None:
                    return result
            except Exception as secondary:
                logger.error(
                    "on_exception handler raised a secondary exception: %s",
                    secondary,
                    exc_info=True,
                )
                # Fall through to generic error below.
                return _generic_error_response(exc, secondary)

        # No handler recovered — return generic error.
        return _generic_error_response(exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generic_error_response(
    primary: Exception, secondary: Exception | None = None
) -> dict[str, Any]:
    """Return a safe, generic error response that never leaks internals."""
    response: dict[str, Any] = {
        "error": "internal_error",
        "message": "An internal error occurred while processing the request.",
    }
    if secondary is not None:
        logger.error(
            "Primary exception: %s | Secondary exception in on_exception handler: %s",
            primary,
            secondary,
        )
    else:
        logger.error("Unhandled exception in middleware pipeline: %s", primary)
    return response
