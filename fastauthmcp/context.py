"""Request-scoped context propagation for FastAuthMCP.

Provides a request-scoped key-value store that flows through the entire
middleware pipeline and is accessible in tool functions. Useful for
propagating tracing headers, correlation IDs, tenant context, and
custom metadata without threading arguments through every function.

Usage:

    from fastauthmcp.context import request_context, set_context, get_context

    # In middleware or plugin:
    set_context("tenant_id", "acme-corp")
    set_context("correlation_id", "abc-123")

    # In tool code:
    @mcp.tool()
    async def my_tool() -> dict:
        tenant = get_context("tenant_id")
        corr_id = get_context("correlation_id")
        return {"tenant": tenant, "correlation_id": corr_id}
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

# The request-scoped context store
_request_context_var: ContextVar[dict[str, Any]] = ContextVar(
    "fastauthmcp_request_context",
    default=None,  # type: ignore[arg-type]
)


def request_context() -> dict[str, Any]:
    """Get the full request context dictionary.

    Returns:
        The current request's context dict, or an empty dict if not in a request.
    """
    ctx = _request_context_var.get(None)
    return ctx if ctx is not None else {}


def get_context(key: str, default: Any = None) -> Any:
    """Get a value from the request context.

    Args:
        key: The context key to look up.
        default: Value to return if key is not found.

    Returns:
        The value associated with the key, or default.
    """
    ctx = _request_context_var.get(None)
    if ctx is None:
        return default
    return ctx.get(key, default)


def set_context(key: str, value: Any) -> None:
    """Set a value in the request context.

    Args:
        key: The context key.
        value: The value to store.

    Raises:
        RuntimeError: If called outside a request context.
    """
    ctx = _request_context_var.get(None)
    if ctx is None:
        # Initialize a new context dict for this request
        ctx = {}
        _request_context_var.set(ctx)
    ctx[key] = value


def init_request_context(initial: dict[str, Any] | None = None) -> None:
    """Initialize a fresh request context (called by middleware at request start).

    Args:
        initial: Optional initial values to populate.
    """
    _request_context_var.set(initial or {})


def clear_request_context() -> None:
    """Clear the request context (called by middleware at request end)."""
    try:
        _request_context_var.set(None)  # type: ignore[arg-type]
    except Exception:
        pass
