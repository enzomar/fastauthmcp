"""Unit tests for the authorization decorators and AuthorizationMiddleware."""

from __future__ import annotations

import pytest
from types import MappingProxyType

from ceramic.authorization import require_role, require_group
from ceramic.config import AuthorizationConfig, AuthorizationPolicy
from ceramic.identity import IdentityContext
from ceramic.middleware.authorization import AuthorizationMiddleware
from ceramic.middleware.pipeline import RequestContext


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_identity(
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    email: str = "user@example.com",
) -> IdentityContext:
    """Create an IdentityContext for testing."""
    return IdentityContext(
        email=email,
        subject="sub-123",
        claims=MappingProxyType({}),
        roles=frozenset(roles or []),
        groups=frozenset(groups or []),
    )


def make_ctx(
    tool_name: str | None = "my_tool",
    identity: IdentityContext | None = None,
) -> RequestContext:
    """Create a RequestContext for testing."""
    return RequestContext(tool_name=tool_name, identity=identity)


# ---------------------------------------------------------------------------
# Decorator Tests
# ---------------------------------------------------------------------------


class TestRequireRoleDecorator:
    """Tests for the @require_role decorator."""

    def test_single_role_stores_metadata(self):
        @require_role("admin")
        async def my_tool():
            pass

        assert my_tool._ceramic_required_roles == ["admin"]

    def test_multiple_roles_stacked(self):
        @require_role("admin")
        @require_role("editor")
        async def my_tool():
            pass

        assert "admin" in my_tool._ceramic_required_roles
        assert "editor" in my_tool._ceramic_required_roles

    def test_preserves_function_name(self):
        @require_role("admin")
        async def my_tool():
            """My docstring."""
            pass

        assert my_tool.__name__ == "my_tool"
        assert my_tool.__doc__ == "My docstring."

    def test_combined_with_require_group(self):
        @require_role("admin")
        @require_group("ops-team")
        async def my_tool():
            pass

        assert my_tool._ceramic_required_roles == ["admin"]
        assert my_tool._ceramic_required_groups == ["ops-team"]


class TestRequireGroupDecorator:
    """Tests for the @require_group decorator."""

    def test_single_group_stores_metadata(self):
        @require_group("ops-team")
        async def my_tool():
            pass

        assert my_tool._ceramic_required_groups == ["ops-team"]

    def test_multiple_groups_stacked(self):
        @require_group("ops-team")
        @require_group("dev-team")
        async def my_tool():
            pass

        assert "ops-team" in my_tool._ceramic_required_groups
        assert "dev-team" in my_tool._ceramic_required_groups

    def test_preserves_function_name(self):
        @require_group("ops-team")
        async def my_tool():
            """My docstring."""
            pass

        assert my_tool.__name__ == "my_tool"
        assert my_tool.__doc__ == "My docstring."


# ---------------------------------------------------------------------------
# AuthorizationMiddleware Tests
# ---------------------------------------------------------------------------


class TestAuthorizationMiddleware:
    """Tests for the AuthorizationMiddleware."""

    @pytest.fixture
    def next_called(self):
        """Track whether next() was called."""
        state = {"called": False, "result": "tool_result"}

        async def _next():
            state["called"] = True
            return state["result"]

        return _next, state

    @pytest.fixture
    def empty_config(self):
        """Authorization config with no policies."""
        return AuthorizationConfig(policies=[])

    # --- Pass-through cases ---

    @pytest.mark.asyncio
    async def test_no_tool_name_passes_through(self, empty_config, next_called):
        """Non-tool requests pass through without checks."""
        next_fn, state = next_called
        middleware = AuthorizationMiddleware(empty_config)
        ctx = make_ctx(tool_name=None)

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_no_policies_passes_through(self, empty_config, next_called):
        """Tool with no policies passes through."""
        next_fn, state = next_called
        middleware = AuthorizationMiddleware(empty_config)
        ctx = make_ctx(tool_name="unprotected_tool", identity=make_identity())

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    # --- Decorator-based policy tests ---

    @pytest.mark.asyncio
    async def test_decorator_role_granted(self, empty_config, next_called):
        """User with required role is granted access."""
        next_fn, state = next_called

        @require_role("admin")
        async def admin_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"admin_tool": admin_tool}
        )
        ctx = make_ctx(tool_name="admin_tool", identity=make_identity(roles=["admin"]))

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_decorator_role_denied(self, empty_config, next_called):
        """User without required role is denied access."""
        next_fn, state = next_called

        @require_role("admin")
        async def admin_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"admin_tool": admin_tool}
        )
        ctx = make_ctx(tool_name="admin_tool", identity=make_identity(roles=["viewer"]))

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert result["message"] == "Insufficient permissions"
        assert "role:admin" in result["required"]

    @pytest.mark.asyncio
    async def test_decorator_group_granted(self, empty_config, next_called):
        """User in required group is granted access."""
        next_fn, state = next_called

        @require_group("ops-team")
        async def deploy_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"deploy_tool": deploy_tool}
        )
        ctx = make_ctx(
            tool_name="deploy_tool", identity=make_identity(groups=["ops-team"])
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_decorator_group_denied(self, empty_config, next_called):
        """User not in required group is denied access."""
        next_fn, state = next_called

        @require_group("ops-team")
        async def deploy_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"deploy_tool": deploy_tool}
        )
        ctx = make_ctx(
            tool_name="deploy_tool", identity=make_identity(groups=["dev-team"])
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert "group:ops-team" in result["required"]

    # --- AND semantics ---

    @pytest.mark.asyncio
    async def test_multiple_decorators_all_pass(self, empty_config, next_called):
        """User satisfying all stacked decorators is granted access."""
        next_fn, state = next_called

        @require_role("admin")
        @require_group("ops-team")
        async def deploy_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"deploy_tool": deploy_tool}
        )
        ctx = make_ctx(
            tool_name="deploy_tool",
            identity=make_identity(roles=["admin"], groups=["ops-team"]),
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_multiple_decorators_partial_fail(self, empty_config, next_called):
        """User satisfying only some stacked decorators is denied."""
        next_fn, state = next_called

        @require_role("admin")
        @require_group("ops-team")
        async def deploy_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"deploy_tool": deploy_tool}
        )
        ctx = make_ctx(
            tool_name="deploy_tool",
            identity=make_identity(roles=["admin"], groups=["dev-team"]),
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert "group:ops-team" in result["required"]

    # --- Identity None with protected tool ---

    @pytest.mark.asyncio
    async def test_none_identity_on_protected_tool(self, empty_config, next_called):
        """None identity on a protected tool returns auth-required error."""
        next_fn, state = next_called

        @require_role("admin")
        async def admin_tool():
            pass

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"admin_tool": admin_tool}
        )
        ctx = make_ctx(tool_name="admin_tool", identity=None)

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert result["message"] == "Authentication is required"
        assert "role:admin" in result["required"]

    # --- YAML policy tests ---

    @pytest.mark.asyncio
    async def test_yaml_policy_role_granted(self, next_called):
        """YAML policy with matching role grants access."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="admin_*", require_role="admin")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(
            tool_name="admin_dashboard", identity=make_identity(roles=["admin"])
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_yaml_policy_role_denied(self, next_called):
        """YAML policy with missing role denies access."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="admin_*", require_role="admin")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(
            tool_name="admin_dashboard", identity=make_identity(roles=["viewer"])
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert "role:admin" in result["required"]

    @pytest.mark.asyncio
    async def test_yaml_policy_group_granted(self, next_called):
        """YAML policy with matching group grants access."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="deploy_*", require_group="ops-team")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(
            tool_name="deploy_server",
            identity=make_identity(groups=["ops-team"]),
        )

        await middleware(ctx, next_fn)

        assert state["called"] is True

    @pytest.mark.asyncio
    async def test_yaml_policy_glob_no_match_passes(self, next_called):
        """Tool name not matching any YAML policy glob passes through."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="admin_*", require_role="admin")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(tool_name="public_info", identity=make_identity(roles=[]))

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_yaml_policy_none_identity(self, next_called):
        """None identity with matching YAML policy returns auth-required."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="admin_*", require_role="admin")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(tool_name="admin_dashboard", identity=None)

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert result["message"] == "Authentication is required"

    # --- Combined decorator + YAML policies ---

    @pytest.mark.asyncio
    async def test_combined_decorator_and_yaml_all_pass(self, next_called):
        """Both decorator and YAML policies satisfied grants access."""
        next_fn, state = next_called

        @require_group("dev-team")
        async def deploy_server():
            pass

        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="deploy_*", require_role="deployer")]
        )
        middleware = AuthorizationMiddleware(
            config, tool_functions={"deploy_server": deploy_server}
        )
        ctx = make_ctx(
            tool_name="deploy_server",
            identity=make_identity(roles=["deployer"], groups=["dev-team"]),
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is True
        assert result == "tool_result"

    @pytest.mark.asyncio
    async def test_combined_decorator_and_yaml_partial_fail(self, next_called):
        """Decorator satisfied but YAML policy not satisfied denies access."""
        next_fn, state = next_called

        @require_group("dev-team")
        async def deploy_server():
            pass

        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="deploy_*", require_role="deployer")]
        )
        middleware = AuthorizationMiddleware(
            config, tool_functions={"deploy_server": deploy_server}
        )
        ctx = make_ctx(
            tool_name="deploy_server",
            identity=make_identity(roles=["viewer"], groups=["dev-team"]),
        )

        result = await middleware(ctx, next_fn)

        assert state["called"] is False
        assert result["error"] == "authorization_denied"
        assert "role:deployer" in result["required"]

    # --- Glob pattern tests ---

    @pytest.mark.asyncio
    async def test_glob_pattern_wildcard(self, next_called):
        """Glob pattern '*' matches all tools."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="*", require_role="authenticated")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(
            tool_name="any_tool",
            identity=make_identity(roles=["authenticated"]),
        )

        await middleware(ctx, next_fn)

        assert state["called"] is True

    @pytest.mark.asyncio
    async def test_glob_pattern_question_mark(self, next_called):
        """Glob pattern '?' matches single character."""
        next_fn, state = next_called
        config = AuthorizationConfig(
            policies=[AuthorizationPolicy(tool="tool_?", require_role="admin")]
        )
        middleware = AuthorizationMiddleware(config)
        ctx = make_ctx(
            tool_name="tool_a",
            identity=make_identity(roles=["admin"]),
        )

        await middleware(ctx, next_fn)
        assert state["called"] is True

    @pytest.mark.asyncio
    async def test_tool_body_never_invoked_on_denial(self, empty_config):
        """Ensure tool function body is never called when authorization fails."""
        invoked = {"count": 0}

        @require_role("admin")
        async def protected_tool():
            invoked["count"] += 1

        async def next_fn():
            invoked["count"] += 1
            return "should_not_reach"

        middleware = AuthorizationMiddleware(
            empty_config, tool_functions={"protected_tool": protected_tool}
        )
        ctx = make_ctx(
            tool_name="protected_tool", identity=make_identity(roles=["viewer"])
        )

        result = await middleware(ctx, next_fn)

        assert invoked["count"] == 0
        assert result["error"] == "authorization_denied"
