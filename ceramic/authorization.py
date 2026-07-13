"""Authorization decorators for Ceramic tools.

Provides `require_role()` and `require_group()` decorators that store
policy metadata on tool functions. The AuthorizationMiddleware reads this
metadata at request time to enforce access control.
"""

from __future__ import annotations

import functools
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


def require_role(role_name: str) -> Callable[[F], F]:
    """Decorator restricting tool access to users with the specified role.

    Multiple `@require_role` decorators can be stacked on the same function;
    all specified roles must be present (AND semantics).

    The decorator stores metadata on the function as
    ``func._ceramic_required_roles``, which is read by
    :class:`~ceramic.middleware.authorization.AuthorizationMiddleware`.

    Args:
        role_name: The role the caller must possess.

    Returns:
        A decorator that annotates the wrapped function with the role requirement.
    """

    def decorator(func: F) -> F:
        # Preserve any existing roles from previously stacked decorators
        existing: list[str] = getattr(func, "_ceramic_required_roles", [])
        func._ceramic_required_roles = existing + [role_name]  # type: ignore[attr-defined]

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            return await func(*args, **kwargs)

        # Copy metadata to wrapper
        wrapper._ceramic_required_roles = func._ceramic_required_roles  # type: ignore[attr-defined]
        # Preserve any group requirements too
        if hasattr(func, "_ceramic_required_groups"):
            wrapper._ceramic_required_groups = func._ceramic_required_groups  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


def require_group(group_name: str) -> Callable[[F], F]:
    """Decorator restricting tool access to users in the specified group.

    Multiple `@require_group` decorators can be stacked on the same function;
    all specified groups must be present (AND semantics).

    The decorator stores metadata on the function as
    ``func._ceramic_required_groups``, which is read by
    :class:`~ceramic.middleware.authorization.AuthorizationMiddleware`.

    Args:
        group_name: The group the caller must belong to.

    Returns:
        A decorator that annotates the wrapped function with the group requirement.
    """

    def decorator(func: F) -> F:
        # Preserve any existing groups from previously stacked decorators
        existing: list[str] = getattr(func, "_ceramic_required_groups", [])
        func._ceramic_required_groups = existing + [group_name]  # type: ignore[attr-defined]

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
            return await func(*args, **kwargs)

        # Copy metadata to wrapper
        wrapper._ceramic_required_groups = func._ceramic_required_groups  # type: ignore[attr-defined]
        # Preserve any role requirements too
        if hasattr(func, "_ceramic_required_roles"):
            wrapper._ceramic_required_roles = func._ceramic_required_roles  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
