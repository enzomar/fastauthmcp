"""Unit tests for the AuthorizationMiddleware.

Tests cover decorator-based policies (@require_roles, @require_groups, @require_scopes)
and verifies that the middleware correctly grants/denies access.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from fastauthmcp.authorization import (
    require_groups,
    require_roles,
    require_scopes,
)
from fastauthmcp.identity import IdentityContext
from fastauthmcp.middleware.authorization import AuthorizationMiddleware
from fastauthmcp.middleware.pipeline import RequestContext

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_identity(
    *,
    roles: frozenset[str] = frozenset(),
    groups: frozenset[str] = frozenset(),
    scopes: str = "",
) -> IdentityContext:
    """Create an IdentityContext with the given roles, groups, and scopes."""
    claims: dict[str, Any] = {}
    if scopes:
        claims["scope"] = scopes
    return IdentityContext(
        email="user@test.com",
        subject="test-user",
        claims=MappingProxyType(claims),
        roles=roles,
        groups=groups,
    )


def _make_ctx(tool_name: str, identity: IdentityContext | None = None) -> RequestContext:
    """Create a RequestContext for testing."""
    ctx = RequestContext(tool_name=tool_name)
    ctx.identity = identity
    return ctx


async def _next_ok() -> Any:
    """Simulates successful downstream middleware/tool execution."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tests: @require_roles
# ---------------------------------------------------------------------------


class TestRequireRoles:
    """Tests for role-based authorization."""

    async def test_roles_granted_single_match(self) -> None:
        """User with required role is granted access."""

        @require_roles("admin")
        async def admin_tool() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"admin_tool": admin_tool})
        ctx = _make_ctx("admin_tool", _make_identity(roles=frozenset(["admin"])))
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_roles_granted_any_match(self) -> None:
        """User with any one of the required roles is granted access (OR semantics)."""

        @require_roles("admin", "editor")
        async def tool() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"tool": tool})
        ctx = _make_ctx("tool", _make_identity(roles=frozenset(["editor"])))
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_roles_denied(self) -> None:
        """User without any required role is denied access."""

        @require_roles("admin")
        async def admin_tool() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"admin_tool": admin_tool})
        ctx = _make_ctx("admin_tool", _make_identity(roles=frozenset(["viewer"])))
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"
        assert "admin" in result["message"]

    async def test_roles_denied_no_identity(self) -> None:
        """Request with no identity is denied when roles are required."""

        @require_roles("admin")
        async def admin_tool() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"admin_tool": admin_tool})
        ctx = _make_ctx("admin_tool", None)
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_required"


# ---------------------------------------------------------------------------
# Tests: @require_groups
# ---------------------------------------------------------------------------


class TestRequireGroups:
    """Tests for group-based authorization."""

    async def test_groups_granted(self) -> None:
        """User in the required group is granted access."""

        @require_groups("ops-team")
        async def deploy() -> str:
            return "deployed"

        mw = AuthorizationMiddleware(tool_functions={"deploy": deploy})
        ctx = _make_ctx("deploy", _make_identity(groups=frozenset(["ops-team"])))
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_groups_granted_any_match(self) -> None:
        """User in any one of the required groups is granted (OR semantics)."""

        @require_groups("ops-team", "platform")
        async def deploy() -> str:
            return "deployed"

        mw = AuthorizationMiddleware(tool_functions={"deploy": deploy})
        ctx = _make_ctx("deploy", _make_identity(groups=frozenset(["platform"])))
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_groups_denied(self) -> None:
        """User not in any required group is denied access."""

        @require_groups("ops-team")
        async def deploy() -> str:
            return "deployed"

        mw = AuthorizationMiddleware(tool_functions={"deploy": deploy})
        ctx = _make_ctx("deploy", _make_identity(groups=frozenset(["engineering"])))
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"
        assert "ops-team" in result["message"]

    async def test_groups_denied_no_identity(self) -> None:
        """Request with no identity is denied when groups are required."""

        @require_groups("ops-team")
        async def deploy() -> str:
            return "deployed"

        mw = AuthorizationMiddleware(tool_functions={"deploy": deploy})
        ctx = _make_ctx("deploy", None)
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_required"


# ---------------------------------------------------------------------------
# Tests: @require_scopes
# ---------------------------------------------------------------------------


class TestRequireScopes:
    """Tests for scope-based authorization."""

    async def test_scopes_all_present(self) -> None:
        """Token with all required scopes is granted access (AND semantics)."""

        @require_scopes("read:data", "write:data")
        async def manage() -> str:
            return "managed"

        mw = AuthorizationMiddleware(tool_functions={"manage": manage})
        ctx = _make_ctx("manage", _make_identity(scopes="read:data write:data openid"))
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_scopes_missing_one(self) -> None:
        """Token missing one of the required scopes is denied."""

        @require_scopes("read:data", "write:data")
        async def manage() -> str:
            return "managed"

        mw = AuthorizationMiddleware(tool_functions={"manage": manage})
        ctx = _make_ctx("manage", _make_identity(scopes="read:data openid"))
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"

    async def test_scopes_none_present(self) -> None:
        """Token with no matching scopes is denied."""

        @require_scopes("admin:full")
        async def secret() -> str:
            return "secret"

        mw = AuthorizationMiddleware(tool_functions={"secret": secret})
        ctx = _make_ctx("secret", _make_identity(scopes="openid profile"))
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"


# ---------------------------------------------------------------------------
# Tests: No decorator (passthrough)
# ---------------------------------------------------------------------------


class TestNoDecorator:
    """Tests for tools without authorization decorators."""

    async def test_no_policy_allows_access(self) -> None:
        """Tool with no authorization decorator allows any request."""

        async def open_tool() -> str:
            return "open"

        mw = AuthorizationMiddleware(tool_functions={"open_tool": open_tool})
        ctx = _make_ctx("open_tool", _make_identity())
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_no_policy_allows_no_identity(self) -> None:
        """Tool with no decorator allows requests without identity."""

        async def open_tool() -> str:
            return "open"

        mw = AuthorizationMiddleware(tool_functions={"open_tool": open_tool})
        ctx = _make_ctx("open_tool", None)
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_unknown_tool_passthrough(self) -> None:
        """Tool not in tool_functions dict passes through (no policies found)."""
        mw = AuthorizationMiddleware(tool_functions={})
        ctx = _make_ctx("unknown_tool", None)
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_no_tool_name_passthrough(self) -> None:
        """Request without a tool_name passes through."""
        mw = AuthorizationMiddleware(tool_functions={})
        ctx = _make_ctx(None, _make_identity())  # type: ignore[arg-type]
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}


# ---------------------------------------------------------------------------
# Tests: Stacked decorators
# ---------------------------------------------------------------------------


class TestStackedDecorators:
    """Tests for multiple stacked authorization decorators (AND semantics)."""

    async def test_stacked_roles_and_scopes_granted(self) -> None:
        """User satisfying both role AND scope policies is granted."""

        @require_roles("admin")
        @require_scopes("write:config")
        async def restricted() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"restricted": restricted})
        ctx = _make_ctx(
            "restricted",
            _make_identity(roles=frozenset(["admin"]), scopes="write:config read:config"),
        )
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}

    async def test_stacked_roles_pass_scopes_fail(self) -> None:
        """User with required role but missing scope is denied."""

        @require_roles("admin")
        @require_scopes("write:config")
        async def restricted() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"restricted": restricted})
        ctx = _make_ctx(
            "restricted",
            _make_identity(roles=frozenset(["admin"]), scopes="read:config"),
        )
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"

    async def test_stacked_scopes_pass_roles_fail(self) -> None:
        """User with required scopes but wrong role is denied."""

        @require_roles("admin")
        @require_scopes("write:config")
        async def restricted() -> str:
            return "done"

        mw = AuthorizationMiddleware(tool_functions={"restricted": restricted})
        ctx = _make_ctx(
            "restricted",
            _make_identity(roles=frozenset(["viewer"]), scopes="write:config"),
        )
        result = await mw(ctx, _next_ok)
        assert result["error"] == "authorization_denied"

    async def test_stacked_roles_and_groups(self) -> None:
        """User satisfying both role AND group policies is granted."""

        @require_roles("editor")
        @require_groups("content-team")
        async def edit() -> str:
            return "edited"

        mw = AuthorizationMiddleware(tool_functions={"edit": edit})
        ctx = _make_ctx(
            "edit",
            _make_identity(
                roles=frozenset(["editor"]),
                groups=frozenset(["content-team"]),
            ),
        )
        result = await mw(ctx, _next_ok)
        assert result == {"status": "ok"}
