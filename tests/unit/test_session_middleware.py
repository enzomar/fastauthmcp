"""Unit tests for SessionMiddleware."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from ceramic.config import SessionsConfig
from ceramic.identity import IdentityContext, _identity_context_var
from ceramic.middleware.pipeline import RequestContext
from ceramic.middleware.session import SessionMiddleware
from ceramic.models import TokenSet


# --- Helpers ---


def _make_jwt(claims: dict) -> str:
    """Create a structurally valid JWT (unsigned) with given claims."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    )
    signature = ""
    return f"{header}.{payload}.{signature}"


def _make_token_set(
    *,
    sub: str = "user-123",
    email: str = "user@example.com",
    roles: list[str] | None = None,
    groups: list[str] | None = None,
    expired: bool = False,
) -> TokenSet:
    """Create a TokenSet with a valid JWT access token."""
    claims = {"sub": sub, "email": email}
    if roles:
        claims["realm_access"] = {"roles": roles}
    if groups:
        claims["groups"] = groups
    access_token = _make_jwt(claims)

    if expired:
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    return TokenSet(
        access_token=access_token,
        refresh_token="refresh-token-abc",
        expires_at=expires_at,
        token_type="Bearer",
    )


# --- Fixtures ---


@pytest.fixture
def session_config() -> SessionsConfig:
    """Create default SessionsConfig."""
    return SessionsConfig(enabled=True, ttl=3600, backend="memory")


@pytest.fixture
def middleware(session_config: SessionsConfig) -> SessionMiddleware:
    """Create a SessionMiddleware instance."""
    return SessionMiddleware(session_config=session_config)


@pytest.fixture
def request_ctx() -> RequestContext:
    """Create a fresh RequestContext."""
    return RequestContext()


@pytest.fixture
def next_fn() -> AsyncMock:
    """Create a mock next function that returns a success response."""
    return AsyncMock(return_value={"result": "success"})


# --- Session Restoration Tests ---


class TestSessionRestoration:
    """Tests for restoring a session from a valid session ID."""

    @pytest.mark.asyncio
    async def test_valid_session_restores_identity(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should restore identity from a valid session without re-auth."""
        token_set = _make_token_set(sub="user-456", email="restored@example.com")
        session_id = await middleware.store.create("user-456", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        assert request_ctx.identity is not None
        assert request_ctx.identity.subject == "user-456"
        assert request_ctx.identity.email == "restored@example.com"

    @pytest.mark.asyncio
    async def test_valid_session_sets_contextvar(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should set the _identity_context_var when restoring from session."""
        token_set = _make_token_set(sub="ctx-user")
        session_id = await middleware.store.create("ctx-user", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        identity = _identity_context_var.get()
        assert identity.subject == "ctx-user"

    @pytest.mark.asyncio
    async def test_valid_session_sets_ctx_session(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should populate ctx.session when a valid session is restored."""
        token_set = _make_token_set()
        session_id = await middleware.store.create("user-123", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        assert request_ctx.session is not None
        assert request_ctx.session.session_id == session_id

    @pytest.mark.asyncio
    async def test_valid_session_restores_roles_and_groups(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should restore roles and groups from stored token claims."""
        token_set = _make_token_set(roles=["admin", "editor"], groups=["team-a"])
        session_id = await middleware.store.create("user-123", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        assert request_ctx.identity is not None
        assert request_ctx.identity.roles == frozenset(["admin", "editor"])
        assert request_ctx.identity.groups == frozenset(["team-a"])

    @pytest.mark.asyncio
    async def test_valid_session_calls_next(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should still call next() after restoring session."""
        token_set = _make_token_set()
        session_id = await middleware.store.create("user-123", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        result = await middleware(request_ctx, next_fn)

        next_fn.assert_awaited_once()
        assert result == {"result": "success"}


# --- Invalid/Expired Session Tests ---


class TestInvalidSession:
    """Tests for invalid or expired session IDs."""

    @pytest.mark.asyncio
    async def test_unknown_session_id_treated_as_unauthenticated(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should clear session_id and proceed as unauthenticated."""
        request_ctx.metadata["session_id"] = "nonexistent-session-id"
        await middleware(request_ctx, next_fn)

        # session_id should be removed from metadata
        assert "session_id" not in request_ctx.metadata or request_ctx.metadata.get("session_id") != "nonexistent-session-id"
        # Identity should not be set by session middleware
        # (downstream auth may set it)
        next_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_session_treated_as_unauthenticated(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should treat expired session as unauthenticated."""
        token_set = _make_token_set()
        session_id = await middleware.store.create("user-123", token_set, ttl=60)
        # Backdate session to simulate expiration
        middleware.store._sessions[session_id].created_at = (
            datetime.now(timezone.utc) - timedelta(seconds=61)
        )

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        # Identity should not be set from session
        assert request_ctx.identity is None
        # Should have removed session_id from metadata
        assert request_ctx.metadata.get("session_id") != session_id
        next_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_session_with_malformed_token_invalidated(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should invalidate session if stored token cannot be parsed."""
        # Create a token with a malformed JWT
        bad_token_set = TokenSet(
            access_token="not-a-valid-jwt",
            refresh_token="refresh",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session_id = await middleware.store.create("user-123", bad_token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        # Session should have been invalidated
        assert await middleware.store.get(session_id) is None
        # Should proceed as unauthenticated
        assert request_ctx.identity is None
        next_fn.assert_awaited_once()


# --- No Session Tests ---


class TestNoSession:
    """Tests for requests without a session ID."""

    @pytest.mark.asyncio
    async def test_no_session_id_passes_through(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should simply call next() without setting identity."""
        result = await middleware(request_ctx, next_fn)

        assert result == {"result": "success"}
        next_fn.assert_awaited_once()
        assert request_ctx.identity is None


# --- Session Creation Tests ---


class TestSessionCreation:
    """Tests for creating sessions after successful auth."""

    @pytest.mark.asyncio
    async def test_creates_session_after_auth_succeeds(
        self, middleware: SessionMiddleware, request_ctx: RequestContext
    ) -> None:
        """Should create a session after downstream auth populates identity."""
        token_set = _make_token_set(sub="new-user")

        async def auth_next() -> dict:
            # Simulate downstream auth middleware populating identity
            identity = IdentityContext(
                email="new@example.com",
                subject="new-user",
                claims={},
                roles=frozenset(),
                groups=frozenset(),
            )
            request_ctx.identity = identity
            request_ctx.metadata["token_set"] = token_set
            return {"result": "authenticated"}

        result = await middleware(request_ctx, auth_next)

        assert result == {"result": "authenticated"}
        # A session should have been created
        new_session_id = request_ctx.metadata.get("session_id")
        assert new_session_id is not None
        # Verify the session was stored
        session = await middleware.store.get(new_session_id)
        assert session is not None
        assert session.subject == "new-user"
        assert session.token_set is token_set

    @pytest.mark.asyncio
    async def test_no_session_created_without_token_set(
        self, middleware: SessionMiddleware, request_ctx: RequestContext
    ) -> None:
        """Should not create session if no token_set in metadata."""
        async def auth_next() -> dict:
            # Auth populates identity but no token_set
            identity = IdentityContext(
                email="user@example.com",
                subject="user-123",
                claims={},
                roles=frozenset(),
                groups=frozenset(),
            )
            request_ctx.identity = identity
            return {"result": "authenticated"}

        await middleware(request_ctx, auth_next)

        # No session should be created
        assert request_ctx.metadata.get("session_id") is None

    @pytest.mark.asyncio
    async def test_no_session_created_if_auth_fails(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should not create session if identity is not populated."""
        next_fn.return_value = {"error": "authentication_required"}

        await middleware(request_ctx, next_fn)

        # No session should be created
        assert request_ctx.metadata.get("session_id") is None

    @pytest.mark.asyncio
    async def test_session_created_with_configured_ttl(
        self, request_ctx: RequestContext
    ) -> None:
        """Should use configured TTL when creating session."""
        config = SessionsConfig(enabled=True, ttl=7200, backend="memory")
        mw = SessionMiddleware(session_config=config)
        token_set = _make_token_set()

        async def auth_next() -> dict:
            request_ctx.identity = IdentityContext(
                email="user@example.com",
                subject="user-123",
                claims={},
                roles=frozenset(),
                groups=frozenset(),
            )
            request_ctx.metadata["token_set"] = token_set
            return {"result": "ok"}

        await mw(request_ctx, auth_next)

        session_id = request_ctx.metadata.get("session_id")
        assert session_id is not None
        session = await mw.store.get(session_id)
        assert session is not None
        assert session.ttl == 7200


# --- Session Update Tests ---


class TestSessionUpdate:
    """Tests for updating sessions on token refresh."""

    @pytest.mark.asyncio
    async def test_updates_session_on_token_refresh(
        self, middleware: SessionMiddleware, request_ctx: RequestContext
    ) -> None:
        """Should update session when token_set changes after next()."""
        original_token = _make_token_set(sub="user-123")
        session_id = await middleware.store.create("user-123", original_token, ttl=3600)

        request_ctx.metadata["session_id"] = session_id

        refreshed_token = _make_token_set(sub="user-123")

        async def refresh_next() -> dict:
            # Simulate token refresh downstream updating the token_set
            request_ctx.metadata["token_set"] = refreshed_token
            return {"result": "success"}

        await middleware(request_ctx, refresh_next)

        # The session should be updated with the new token
        session = await middleware.store.get(session_id)
        assert session is not None
        assert session.token_set is refreshed_token

    @pytest.mark.asyncio
    async def test_no_update_when_token_unchanged(
        self, middleware: SessionMiddleware, request_ctx: RequestContext, next_fn: AsyncMock
    ) -> None:
        """Should not update session when token_set hasn't changed."""
        token_set = _make_token_set()
        session_id = await middleware.store.create("user-123", token_set, ttl=3600)

        request_ctx.metadata["session_id"] = session_id
        await middleware(request_ctx, next_fn)

        # Session should still have the original token (unchanged)
        session = await middleware.store.get(session_id)
        assert session is not None
        assert session.token_set is token_set


# --- Builtin Wrapper Tests ---


class TestBuiltinWrapper:
    """Tests for the builtin.py SessionMiddleware wrapper."""

    @pytest.mark.asyncio
    async def test_builtin_wrapper_delegates_when_enabled(self) -> None:
        """The wrapper in builtin.py should delegate to the real implementation."""
        from ceramic.middleware.builtin import SessionMiddleware as BuiltinSession

        config = SessionsConfig(enabled=True, ttl=3600, backend="memory")
        mw = BuiltinSession(config=config)
        assert mw._impl is not None

    @pytest.mark.asyncio
    async def test_builtin_wrapper_passthrough_when_disabled(self) -> None:
        """The wrapper should pass through when sessions are disabled."""
        from ceramic.middleware.builtin import SessionMiddleware as BuiltinSession

        config = SessionsConfig(enabled=False, ttl=3600, backend="memory")
        mw = BuiltinSession(config=config)
        assert mw._impl is None

        ctx = RequestContext()
        next_fn = AsyncMock(return_value={"result": "ok"})
        result = await mw(ctx, next_fn)

        assert result == {"result": "ok"}
        next_fn.assert_awaited_once()
