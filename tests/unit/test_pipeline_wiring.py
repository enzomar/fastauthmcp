"""Tests for middleware pipeline wiring in CeramicFastMCP.

Verifies that:
- Empty config → empty pipeline (passthrough)
- Config with `observability` section → pipeline contains observability middleware
- Config with `auth` section → pipeline contains auth middleware
- Config with all sections → pipeline contains all middleware in correct order
- Custom plugins are added after built-in middleware
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from unittest.mock import patch

import pytest

from ceramic.config import (
    AuthConfig,
    AuthorizationConfig,
    CeramicConfig,
    ObservabilityConfig,
    SessionsConfig,
)
from ceramic.middleware.builtin import (
    AuthenticationMiddleware,
    AuthorizationMiddleware,
    ObservabilityMiddleware,
    SessionMiddleware,
)
from ceramic.middleware.pipeline import MiddlewarePipeline, RequestContext
from ceramic.server import CeramicFastMCP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_config() -> CeramicConfig:
    """Return a CeramicConfig with no sections configured."""
    return CeramicConfig()


def _config_with_observability() -> CeramicConfig:
    """Return a CeramicConfig with only observability enabled."""
    return CeramicConfig(observability=ObservabilityConfig())


def _config_with_auth() -> CeramicConfig:
    """Return a CeramicConfig with only auth configured."""
    return CeramicConfig(
        auth=AuthConfig(issuer="https://idp.example.com", client_id="test-app")
    )


def _config_with_sessions() -> CeramicConfig:
    """Return a CeramicConfig with only sessions enabled."""
    return CeramicConfig(sessions=SessionsConfig())


def _config_with_authorization() -> CeramicConfig:
    """Return a CeramicConfig with only authorization configured."""
    return CeramicConfig(authorization=AuthorizationConfig())


def _full_config() -> CeramicConfig:
    """Return a CeramicConfig with all sections enabled."""
    return CeramicConfig(
        observability=ObservabilityConfig(),
        sessions=SessionsConfig(),
        auth=AuthConfig(issuer="https://idp.example.com", client_id="test-app"),
        authorization=AuthorizationConfig(),
    )


def _make_ceramic(config: CeramicConfig) -> CeramicFastMCP:
    """Create a CeramicFastMCP with a given config, bypassing file loading."""
    with patch("ceramic.server.ConfigLoader") as mock_loader_cls:
        mock_loader = mock_loader_cls.return_value
        mock_loader.load.return_value = config
        return CeramicFastMCP(name="test")


class _TrackingPlugin:
    """A simple plugin that tracks its registration for testing."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._before_called = False

        async def before_request(
            ctx: RequestContext, next: Callable[[], Awaitable[Any]]
        ) -> Any:
            self._before_called = True
            return await next()

        self.hooks: dict[str, Any] = {"before_request": before_request}


# ---------------------------------------------------------------------------
# Tests: Empty config → passthrough
# ---------------------------------------------------------------------------


class TestEmptyConfigPassthrough:
    """When no config sections are active, the pipeline should be empty."""

    def test_empty_config_produces_empty_pipeline(self) -> None:
        server = _make_ceramic(_empty_config())
        pipeline = server._pipeline
        assert isinstance(pipeline, MiddlewarePipeline)
        assert len(pipeline._before) == 0
        assert len(pipeline._after) == 0
        assert len(pipeline._on_exception) == 0

    def test_passthrough_flag_is_true(self) -> None:
        server = _make_ceramic(_empty_config())
        assert server._passthrough is True


# ---------------------------------------------------------------------------
# Tests: Individual config sections activate corresponding middleware
# ---------------------------------------------------------------------------


class TestObservabilitySection:
    """Config with observability section should include ObservabilityMiddleware."""

    def test_observability_middleware_added(self) -> None:
        server = _make_ceramic(_config_with_observability())
        assert len(server._pipeline._before) == 1
        assert isinstance(server._pipeline._before[0], ObservabilityMiddleware)

    def test_observability_middleware_receives_config(self) -> None:
        config = _config_with_observability()
        server = _make_ceramic(config)
        mw = server._pipeline._before[0]
        assert isinstance(mw, ObservabilityMiddleware)
        assert mw.config is config.observability


class TestAuthSection:
    """Config with auth section should include AuthenticationMiddleware."""

    def test_auth_middleware_added(self) -> None:
        server = _make_ceramic(_config_with_auth())
        assert len(server._pipeline._before) == 1
        assert isinstance(server._pipeline._before[0], AuthenticationMiddleware)

    def test_auth_middleware_receives_config(self) -> None:
        config = _config_with_auth()
        server = _make_ceramic(config)
        mw = server._pipeline._before[0]
        assert isinstance(mw, AuthenticationMiddleware)
        assert mw.config is config.auth


class TestSessionsSection:
    """Config with sessions section should include SessionMiddleware."""

    def test_session_middleware_added(self) -> None:
        server = _make_ceramic(_config_with_sessions())
        assert len(server._pipeline._before) == 1
        assert isinstance(server._pipeline._before[0], SessionMiddleware)

    def test_session_middleware_receives_config(self) -> None:
        config = _config_with_sessions()
        server = _make_ceramic(config)
        mw = server._pipeline._before[0]
        assert isinstance(mw, SessionMiddleware)
        assert mw.config is config.sessions


class TestAuthorizationSection:
    """Config with authorization section should include AuthorizationMiddleware."""

    def test_authorization_middleware_added(self) -> None:
        server = _make_ceramic(_config_with_authorization())
        assert len(server._pipeline._before) == 1
        assert isinstance(server._pipeline._before[0], AuthorizationMiddleware)

    def test_authorization_middleware_receives_config(self) -> None:
        config = _config_with_authorization()
        server = _make_ceramic(config)
        mw = server._pipeline._before[0]
        assert isinstance(mw, AuthorizationMiddleware)
        assert mw.config is config.authorization


# ---------------------------------------------------------------------------
# Tests: Full config → all middleware in correct order
# ---------------------------------------------------------------------------


class TestFullConfigOrder:
    """Config with all sections produces middleware in design-specified order."""

    def test_all_middleware_present_in_order(self) -> None:
        server = _make_ceramic(_full_config())
        before = server._pipeline._before
        assert len(before) == 4
        assert isinstance(before[0], ObservabilityMiddleware)
        assert isinstance(before[1], SessionMiddleware)
        assert isinstance(before[2], AuthenticationMiddleware)
        assert isinstance(before[3], AuthorizationMiddleware)

    def test_passthrough_flag_is_false(self) -> None:
        server = _make_ceramic(_full_config())
        assert server._passthrough is False


# ---------------------------------------------------------------------------
# Tests: Custom plugins are added after built-in middleware
# ---------------------------------------------------------------------------


class TestCustomPluginsAfterBuiltins:
    """Plugins registered via use() appear after built-in middleware."""

    def test_plugin_hooks_appended_after_builtins(self) -> None:
        config = _full_config()
        server = _make_ceramic(config)

        plugin = _TrackingPlugin("test-plugin")
        server.use(plugin)

        # Rebuild pipeline to include the new plugin
        server._pipeline = server._build_pipeline()

        before = server._pipeline._before
        # 4 built-ins + 1 plugin before_request hook
        assert len(before) == 5
        # First 4 are built-ins
        assert isinstance(before[0], ObservabilityMiddleware)
        assert isinstance(before[1], SessionMiddleware)
        assert isinstance(before[2], AuthenticationMiddleware)
        assert isinstance(before[3], AuthorizationMiddleware)
        # Last is the plugin hook
        assert before[4] is plugin.hooks["before_request"]

    def test_multiple_plugins_maintain_registration_order(self) -> None:
        server = _make_ceramic(_empty_config())

        plugin_a = _TrackingPlugin("plugin-a")
        plugin_b = _TrackingPlugin("plugin-b")
        server.use(plugin_a)
        server.use(plugin_b)

        # Rebuild pipeline
        server._pipeline = server._build_pipeline()

        before = server._pipeline._before
        assert len(before) == 2
        assert before[0] is plugin_a.hooks["before_request"]
        assert before[1] is plugin_b.hooks["before_request"]


# ---------------------------------------------------------------------------
# Tests: Pipeline execution (integration)
# ---------------------------------------------------------------------------


class TestPipelineExecution:
    """Verify that the wired pipeline actually executes middleware."""

    @pytest.mark.asyncio
    async def test_empty_pipeline_calls_handler_directly(self) -> None:
        server = _make_ceramic(_empty_config())
        ctx = RequestContext(tool_name="test_tool")
        result = await server._pipeline.execute(ctx, self._handler("direct"))
        assert result == "direct"

    @pytest.mark.asyncio
    async def test_full_pipeline_passes_through_to_handler(self) -> None:
        import base64
        import json
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock

        from ceramic.models import TokenSet

        # Create a valid (non-expired) token so AuthenticationMiddleware passes through
        claims = {"sub": "user-123", "email": "test@example.com"}
        header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        jwt_token = f"{header}.{payload}."
        valid_token = TokenSet(
            access_token=jwt_token,
            refresh_token="refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        server = _make_ceramic(_full_config())
        # Patch the token storage on the auth middleware to return a valid token
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=valid_token)
        server._pipeline._before[2]._impl.token_storage = mock_storage

        ctx = RequestContext(tool_name="test_tool")
        result = await server._pipeline.execute(ctx, self._handler("delegated"))
        assert result == "delegated"

    @staticmethod
    def _handler(value: str) -> Callable[[], Awaitable[str]]:
        async def _h() -> str:
            return value

        return _h
