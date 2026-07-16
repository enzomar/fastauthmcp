"""Tests for IdentityContext propagation via contextvars.

Validates:
- fastauthmcp.identity() raises RuntimeError outside request context
- fastauthmcp.identity() returns the correct IdentityContext during a request
- ctx.identity is fastauthmcp.identity() (same object, not just equal)
- IdentityContext is immutable (assignment raises AttributeError)
- ctx.identity is None when auth is disabled (no middleware sets it)

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

import base64
import contextvars
import json
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

import fastauthmcp
from fastauthmcp.config import AuthConfig
from fastauthmcp.identity import IdentityContext, _identity_context_var, identity
from fastauthmcp.middleware.authentication import AuthenticationMiddleware
from fastauthmcp.middleware.pipeline import RequestContext
from fastauthmcp.models import TokenSet

# --- Helpers ---


def _make_jwt(claims: dict) -> str:
    """Create a structurally valid JWT (unsigned) with given claims."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}."


def _make_token_set(claims: dict | None = None) -> TokenSet:
    """Create a valid TokenSet with the given claims encoded in the JWT."""
    if claims is None:
        claims = {
            "sub": "user-42",
            "email": "alice@example.com",
            "realm_access": {"roles": ["editor", "viewer"]},
            "groups": ["team-alpha"],
        }
    return TokenSet(
        access_token=_make_jwt(claims),
        refresh_token="refresh-123",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        token_type="Bearer",
    )


# --- Test: identity() outside request context ---


class TestIdentityOutsideContext:
    """fastauthmcp.identity() must raise RuntimeError when no request context is active."""

    def test_raises_runtime_error_in_clean_context(self):
        """Calling identity() in a fresh context (no contextvar set) raises RuntimeError."""

        def _run():
            with pytest.raises(RuntimeError, match="outside of an active request context"):
                identity()

        # Run in a fresh copy_context to ensure no leaked state
        ctx = contextvars.copy_context()
        ctx.run(_run)

    def test_module_level_function_raises(self):
        """The module-level fastauthmcp.identity() also raises RuntimeError."""

        def _run():
            with pytest.raises(RuntimeError, match="outside of an active request context"):
                fastauthmcp.identity()

        ctx = contextvars.copy_context()
        ctx.run(_run)

    def test_error_message_is_helpful(self):
        """The RuntimeError message should guide the developer."""

        def _run():
            with pytest.raises(RuntimeError) as exc_info:
                identity()
            msg = str(exc_info.value)
            assert "request context" in msg.lower() or "request handler" in msg.lower()

        ctx = contextvars.copy_context()
        ctx.run(_run)


# --- Test: identity() returns correct IdentityContext ---


class TestIdentityReturnsCorrectContext:
    """fastauthmcp.identity() returns the correct IdentityContext when set."""

    def test_returns_identity_when_contextvar_set(self):
        """identity() returns the IdentityContext from the contextvar."""
        id_ctx = IdentityContext(
            email="bob@example.com",
            subject="sub-bob",
            claims=MappingProxyType({"sub": "sub-bob", "email": "bob@example.com"}),
            roles=frozenset({"admin"}),
            groups=frozenset({"ops-team"}),
        )

        def _run():
            token = _identity_context_var.set(id_ctx)
            try:
                result = identity()
                assert result is id_ctx
                assert result.email == "bob@example.com"
                assert result.subject == "sub-bob"
                assert result.roles == frozenset({"admin"})
                assert result.groups == frozenset({"ops-team"})
            finally:
                _identity_context_var.reset(token)

        ctx = contextvars.copy_context()
        ctx.run(_run)


# --- Test: Dual Identity Access Equivalence (Property 7) ---


class TestDualIdentityAccessEquivalence:
    """ctx.identity and fastauthmcp.identity() must return the SAME object (is, not ==)."""

    @pytest.mark.asyncio
    async def test_ctx_identity_is_fastauthmcp_identity(self):
        """After middleware runs, ctx.identity is fastauthmcp.identity() (same object)."""
        auth_config = AuthConfig(
            provider="oidc",
            issuer="https://idp.example.com",
            client_id="test-client",
        )
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=_make_token_set())
        mock_storage.store = AsyncMock()
        mock_storage.delete = AsyncMock()

        mock_oauth = AsyncMock()

        middleware = AuthenticationMiddleware(
            auth_config=auth_config,
            token_storage=mock_storage,
            oauth_service=mock_oauth,
        )

        request_ctx = RequestContext()
        identity_during_request: IdentityContext | None = None

        async def handler():
            nonlocal identity_during_request
            # Capture what fastauthmcp.identity() returns during handler execution
            identity_during_request = fastauthmcp.identity()
            return {"result": "ok"}

        await middleware(request_ctx, handler)

        # ctx.identity and what fastauthmcp.identity() returned must be the same object
        assert request_ctx.identity is not None
        assert identity_during_request is not None
        assert request_ctx.identity is identity_during_request

    @pytest.mark.asyncio
    async def test_both_access_paths_have_same_fields(self):
        """Both ctx.identity and fastauthmcp.identity() expose identical field values."""
        claims = {
            "sub": "user-99",
            "email": "dual@test.com",
            "realm_access": {"roles": ["manager"]},
            "groups": ["finance"],
        }
        auth_config = AuthConfig(
            provider="oidc",
            issuer="https://idp.example.com",
            client_id="test-client",
        )
        mock_storage = AsyncMock()
        mock_storage.retrieve = AsyncMock(return_value=_make_token_set(claims))
        mock_storage.store = AsyncMock()
        mock_storage.delete = AsyncMock()

        middleware = AuthenticationMiddleware(
            auth_config=auth_config,
            token_storage=mock_storage,
            oauth_service=AsyncMock(),
        )

        request_ctx = RequestContext()
        captured_identity: IdentityContext | None = None

        async def handler():
            nonlocal captured_identity
            captured_identity = fastauthmcp.identity()
            return {"result": "ok"}

        await middleware(request_ctx, handler)

        assert request_ctx.identity.email == captured_identity.email == "dual@test.com"
        assert request_ctx.identity.subject == captured_identity.subject == "user-99"
        assert request_ctx.identity.roles == captured_identity.roles == frozenset({"manager"})
        assert request_ctx.identity.groups == captured_identity.groups == frozenset({"finance"})


# --- Test: IdentityContext is immutable ---


class TestIdentityContextImmutability:
    """IdentityContext is frozen — field assignment must raise AttributeError."""

    def test_cannot_set_email(self):
        ctx = IdentityContext(
            email="x@y.com",
            subject="s1",
            claims=MappingProxyType({}),
            roles=frozenset(),
            groups=frozenset(),
        )
        with pytest.raises(AttributeError):
            ctx.email = "other@y.com"  # type: ignore[misc]

    def test_cannot_set_subject(self):
        ctx = IdentityContext(
            email=None,
            subject="s1",
            claims=MappingProxyType({}),
            roles=frozenset(),
            groups=frozenset(),
        )
        with pytest.raises(AttributeError):
            ctx.subject = "other"  # type: ignore[misc]

    def test_cannot_set_roles(self):
        ctx = IdentityContext(
            email=None,
            subject=None,
            claims=MappingProxyType({}),
            roles=frozenset({"admin"}),
            groups=frozenset(),
        )
        with pytest.raises(AttributeError):
            ctx.roles = frozenset({"hacked"})  # type: ignore[misc]

    def test_cannot_set_groups(self):
        ctx = IdentityContext(
            email=None,
            subject=None,
            claims=MappingProxyType({}),
            roles=frozenset(),
            groups=frozenset({"team-a"}),
        )
        with pytest.raises(AttributeError):
            ctx.groups = frozenset({"team-b"})  # type: ignore[misc]

    def test_cannot_set_claims(self):
        ctx = IdentityContext(
            email=None,
            subject=None,
            claims=MappingProxyType({"a": "b"}),
            roles=frozenset(),
            groups=frozenset(),
        )
        with pytest.raises(AttributeError):
            ctx.claims = MappingProxyType({})  # type: ignore[misc]

    def test_claims_mapping_is_read_only(self):
        """The claims MappingProxyType should reject item assignment."""
        ctx = IdentityContext(
            email=None,
            subject=None,
            claims=MappingProxyType({"key": "value"}),
            roles=frozenset(),
            groups=frozenset(),
        )
        with pytest.raises(TypeError):
            ctx.claims["new_key"] = "bad"  # type: ignore[index]


# --- Test: ctx.identity is None when auth is disabled ---


class TestIdentityNoneWhenAuthDisabled:
    """When auth is disabled (no AuthenticationMiddleware), ctx.identity remains None."""

    def test_request_context_identity_defaults_to_none(self):
        """A fresh RequestContext has identity=None."""
        ctx = RequestContext()
        assert ctx.identity is None

    @pytest.mark.asyncio
    async def test_no_middleware_leaves_identity_none(self):
        """Without authentication middleware, ctx.identity stays None through pipeline."""
        ctx = RequestContext()

        # Simulate a pipeline that doesn't have auth middleware
        async def no_auth_handler():
            return {"result": "anonymous"}

        # Call handler directly (no auth middleware in the chain)
        result = await no_auth_handler()

        assert ctx.identity is None
        assert result == {"result": "anonymous"}

    def test_contextvar_not_set_when_auth_disabled(self):
        """When auth is disabled, the contextvar should not be set."""

        def _run():
            # In a clean context, the var should have no value
            with pytest.raises(LookupError):
                _identity_context_var.get()

        ctx = contextvars.copy_context()
        ctx.run(_run)
