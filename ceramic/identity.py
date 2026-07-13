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
