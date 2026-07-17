"""Per-tool authorization decorators and policy evaluation.

Provides decorators that attach authorization requirements to individual
tool functions. The AuthorizationMiddleware evaluates these requirements
at request time, rejecting unauthorized calls before the tool body executes.

Usage:

    from fastauthmcp import FastMCP
    from fastauthmcp.authorization import require_roles, require_groups, require_scopes

    mcp = FastMCP("my-server", config="fastauthmcp.yaml")

    @mcp.tool()
    @require_roles("admin", "editor")
    async def admin_tool() -> str:
        return "only admins and editors can see this"

    @mcp.tool()
    @require_groups("ops-team")
    async def deploy() -> str:
        return "deployed"

    @mcp.tool()
    @require_scopes("read:data", "write:data")
    async def manage_data() -> str:
        return "data managed"
"""

from __future__ import annotations

import functools
from typing import Any, Callable

# Attribute name used to store authorization policies on tool functions
_AUTHZ_POLICIES_ATTR = "_fastauthmcp_authz_policies"


class AuthzPolicy:
    """A single authorization requirement attached to a tool function."""

    __slots__ = ("kind", "values")

    def __init__(self, kind: str, values: frozenset[str]) -> None:
        self.kind = kind  # "roles", "groups", or "scopes"
        self.values = values

    def evaluate(
        self,
        user_roles: frozenset[str],
        user_groups: frozenset[str],
        user_scopes: frozenset[str],
    ) -> bool:
        """Return True if the user satisfies this policy."""
        if self.kind == "roles":
            return bool(self.values & user_roles)
        elif self.kind == "groups":
            return bool(self.values & user_groups)
        elif self.kind == "scopes":
            return self.values.issubset(user_scopes)
        return False


def _attach_policy(func: Callable, policy: AuthzPolicy) -> Callable:
    """Attach an authorization policy to a function."""
    existing: list[AuthzPolicy] = getattr(func, _AUTHZ_POLICIES_ATTR, [])
    existing.append(policy)
    setattr(func, _AUTHZ_POLICIES_ATTR, existing)
    return func


def require_roles(*roles: str) -> Callable:
    """Decorator: require the caller to have at least one of the specified roles.

    Multiple roles use OR semantics — user needs any one of the listed roles.
    Stack multiple decorators for AND semantics across different checks.

    Example::

        @mcp.tool()
        @require_roles("admin", "superuser")
        async def admin_action() -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        _attach_policy(func, AuthzPolicy("roles", frozenset(roles)))

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs) if _is_async(func) else func(*args, **kwargs)

        # Preserve policies on the wrapper
        setattr(wrapper, _AUTHZ_POLICIES_ATTR, getattr(func, _AUTHZ_POLICIES_ATTR))
        return wrapper

    return decorator


def require_groups(*groups: str) -> Callable:
    """Decorator: require the caller to be in at least one of the specified groups.

    Multiple groups use OR semantics — user needs membership in any one group.

    Example::

        @mcp.tool()
        @require_groups("engineering", "platform")
        async def internal_tool() -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        _attach_policy(func, AuthzPolicy("groups", frozenset(groups)))

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs) if _is_async(func) else func(*args, **kwargs)

        setattr(wrapper, _AUTHZ_POLICIES_ATTR, getattr(func, _AUTHZ_POLICIES_ATTR))
        return wrapper

    return decorator


def require_scopes(*scopes: str) -> Callable:
    """Decorator: require the token to contain all of the specified scopes.

    Scopes use AND semantics — the token must have every listed scope.

    Example::

        @mcp.tool()
        @require_scopes("read:orders", "write:orders")
        async def manage_orders() -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        _attach_policy(func, AuthzPolicy("scopes", frozenset(scopes)))

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs) if _is_async(func) else func(*args, **kwargs)

        setattr(wrapper, _AUTHZ_POLICIES_ATTR, getattr(func, _AUTHZ_POLICIES_ATTR))
        return wrapper

    return decorator


# Legacy aliases matching the design spec naming
require_role = require_roles
require_group = require_groups


def get_policies(func: Callable) -> list[AuthzPolicy]:
    """Retrieve authorization policies attached to a tool function."""
    return getattr(func, _AUTHZ_POLICIES_ATTR, [])


def _is_async(func: Callable) -> bool:
    """Check if a function is a coroutine function."""
    import asyncio

    return asyncio.iscoroutinefunction(func)
