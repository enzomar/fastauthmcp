"""Trimmed session middleware tests (5 tests).

Covers: session created on auth, session restored on next call,
session expired rejected, TTL enforced, disabled passthrough.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from ceramic.config import SessionsConfig
from ceramic.identity import IdentityContext
from ceramic.middleware.pipeline import RequestContext
from ceramic.middleware.session import SessionMiddleware
from ceramic.models import TokenSet

import base64
import json


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
    return f"{header}.{payload}."


def _make_token_set(*, sub="user-123", email="user@example.com", expired=False):
    claims = {"sub": sub, "email": email}
    access_token = _make_jwt(claims)
    expires_at = (
        datetime.now(timezone.utc) - timedelta(hours=1)
        if expired
        else datetime.now(timezone.utc) + timedelta(hours=1)
    )
    return TokenSet(
        access_token=access_token,
        refresh_token="refresh-token",
        expires_at=expires_at,
        token_type="Bearer",
    )


@pytest.fixture
def middleware():
    return SessionMiddleware(session_config=SessionsConfig(enabled=True, ttl=3600))


# ---------------------------------------------------------------------------


class TestSessionMiddleware:
    @pytest.mark.asyncio
    async def test_session_created_on_auth(self, middleware):
        """After successful auth, a session is created in the store."""
        ctx = RequestContext()
        token_set = _make_token_set(sub="new-user")

        async def auth_next():
            ctx.identity = IdentityContext(
                email="new@example.com",
                subject="new-user",
                claims={},
                roles=frozenset(),
                groups=frozenset(),
            )
            ctx.metadata["token_set"] = token_set
            return {"result": "ok"}

        await middleware(ctx, auth_next)

        session_id = ctx.metadata.get("session_id")
        assert session_id is not None
        session = await middleware.store.get(session_id)
        assert session is not None
        assert session.subject == "new-user"

    @pytest.mark.asyncio
    async def test_session_restored_on_next_call(self, middleware):
        """A valid session restores identity without re-authentication."""
        token_set = _make_token_set(sub="user-456", email="restored@example.com")
        session_id = await middleware.store.create("user-456", token_set, ttl=3600)

        ctx = RequestContext()
        ctx.metadata["session_id"] = session_id
        next_fn = AsyncMock(return_value={"result": "ok"})

        await middleware(ctx, next_fn)

        assert ctx.identity is not None
        assert ctx.identity.subject == "user-456"
        assert ctx.identity.email == "restored@example.com"

    @pytest.mark.asyncio
    async def test_session_expired_rejected(self, middleware):
        """An expired session is treated as unauthenticated."""
        token_set = _make_token_set()
        session_id = await middleware.store.create("user-123", token_set, ttl=60)
        # Backdate session to expire it
        middleware.store._sessions[session_id].created_at = datetime.now(
            timezone.utc
        ) - timedelta(seconds=61)

        ctx = RequestContext()
        ctx.metadata["session_id"] = session_id
        next_fn = AsyncMock(return_value={"result": "ok"})

        await middleware(ctx, next_fn)

        assert ctx.identity is None

    @pytest.mark.asyncio
    async def test_ttl_enforced(self):
        """Session uses configured TTL from SessionsConfig."""
        config = SessionsConfig(enabled=True, ttl=7200)
        mw = SessionMiddleware(session_config=config)
        token_set = _make_token_set()
        ctx = RequestContext()

        async def auth_next():
            ctx.identity = IdentityContext(
                email="user@example.com",
                subject="user-123",
                claims={},
                roles=frozenset(),
                groups=frozenset(),
            )
            ctx.metadata["token_set"] = token_set
            return {"result": "ok"}

        await mw(ctx, auth_next)

        session_id = ctx.metadata["session_id"]
        session = await mw.store.get(session_id)
        assert session.ttl == 7200

    @pytest.mark.asyncio
    async def test_disabled_passthrough(self):
        """Disabled session middleware passes through without touching identity."""
        from ceramic.middleware.builtin import SessionMiddleware as BuiltinSession

        mw = BuiltinSession(config=SessionsConfig(enabled=False, ttl=3600))
        ctx = RequestContext()
        next_fn = AsyncMock(return_value={"result": "ok"})

        result = await mw(ctx, next_fn)

        assert result == {"result": "ok"}
        next_fn.assert_awaited_once()
