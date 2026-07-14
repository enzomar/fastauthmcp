"""Identity context propagation via contextvars."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class IdentityContext:
    """Immutable identity information for the authenticated user."""

    email: str | None
    subject: str | None
    claims: MappingProxyType[str, Any]
    roles: frozenset[str]
    groups: frozenset[str]


_identity_context_var: ContextVar[IdentityContext] = ContextVar(
    "ceramic_identity_context"
)

_access_token_var: ContextVar[str] = ContextVar("ceramic_access_token")


def identity() -> IdentityContext:
    """Return the current request's IdentityContext.

    Returns:
        The IdentityContext for the active request.

    Raises:
        RuntimeError: If called outside of an active request context.
    """
    try:
        return _identity_context_var.get()
    except LookupError:
        raise RuntimeError(
            "identity() called outside of an active request context. "
            "Ensure this function is called within a Ceramic request handler."
        ) from None


def access_token() -> str:
    """Return the current request's raw access token for downstream API calls.

    Use this to propagate the authenticated user's token to downstream
    services. The token is always valid (auto-refreshed by the middleware
    before your tool code runs).

    Example::

        from ceramic import access_token
        import httpx

        @mcp.tool()
        def get_orders() -> list:
            token = access_token()
            resp = httpx.get(
                "https://api.internal.com/v1/orders",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.json()

    Returns:
        The current valid access token string (JWT or opaque).

    Raises:
        RuntimeError: If called outside of an active request context
            or if no token is available (e.g., unauthenticated request).
    """
    try:
        return _access_token_var.get()
    except LookupError:
        raise RuntimeError(
            "access_token() called outside of an active request context "
            "or no token is available. Ensure this function is called within "
            "a Ceramic request handler with authentication enabled."
        ) from None
