"""Unit tests for SessionStore protocol and InMemorySessionStore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from fastauthmcp.exceptions import SessionError
from fastauthmcp.models import Session, TokenSet
from fastauthmcp.sessions import InMemorySessionStore


def _make_token_set(access: str = "access-123") -> TokenSet:
    """Create a TokenSet fixture."""
    return TokenSet(
        access_token=access,
        refresh_token="refresh-456",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )


@pytest.fixture
def store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def token_set() -> TokenSet:
    return _make_token_set()


class TestCreate:
    async def test_returns_unique_session_id(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        id1 = await store.create("user-1", token_set, ttl=3600)
        id2 = await store.create("user-2", token_set, ttl=3600)
        assert id1 != id2

    async def test_returns_string_uuid(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        import uuid

        session_id = await store.create("user-1", token_set, ttl=3600)
        # Should be a valid UUID string
        uuid.UUID(session_id)

    async def test_session_retrievable_after_creation(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        session = await store.get(session_id)
        assert session is not None
        assert session.session_id == session_id
        assert session.subject == "user-1"
        assert session.token_set is token_set
        assert session.ttl == 3600

    async def test_created_at_is_utc(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        session = await store.get(session_id)
        assert session is not None
        assert session.created_at.tzinfo is not None


class TestGet:
    async def test_returns_none_for_nonexistent(self, store: InMemorySessionStore) -> None:
        result = await store.get("nonexistent-id")
        assert result is None

    async def test_returns_session_when_valid(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        session = await store.get(session_id)
        assert session is not None
        assert isinstance(session, Session)

    async def test_returns_none_for_expired_session(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        # Manually backdate the session to simulate expiration
        session = store._sessions[session_id]
        session.created_at = datetime.now(timezone.utc) - timedelta(seconds=3601)

        result = await store.get(session_id)
        assert result is None

    async def test_expired_session_is_invalidated(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=60)
        # Backdate to expire
        store._sessions[session_id].created_at = datetime.now(timezone.utc) - timedelta(seconds=61)

        await store.get(session_id)
        # Session should be removed from storage
        assert session_id not in store._sessions

    async def test_session_not_expired_just_under_ttl(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=100)
        # Set created_at to just under TTL (99 seconds ago) — should still be valid
        store._sessions[session_id].created_at = datetime.now(timezone.utc) - timedelta(seconds=99)

        result = await store.get(session_id)
        assert result is not None


class TestUpdate:
    async def test_updates_token_set(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        new_token_set = _make_token_set(access="new-access-789")

        await store.update(session_id, new_token_set)

        session = await store.get(session_id)
        assert session is not None
        assert session.token_set is new_token_set
        assert session.token_set.access_token == "new-access-789"

    async def test_raises_session_error_for_nonexistent(self, store: InMemorySessionStore) -> None:
        new_token_set = _make_token_set()
        with pytest.raises(SessionError):
            await store.update("nonexistent-id", new_token_set)

    async def test_preserves_other_session_fields(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        session_before = await store.get(session_id)
        assert session_before is not None

        new_token_set = _make_token_set(access="updated")
        await store.update(session_id, new_token_set)

        session_after = await store.get(session_id)
        assert session_after is not None
        assert session_after.subject == session_before.subject
        assert session_after.created_at == session_before.created_at
        assert session_after.ttl == session_before.ttl


class TestInvalidate:
    async def test_removes_existing_session(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        session_id = await store.create("user-1", token_set, ttl=3600)
        await store.invalidate(session_id)

        result = await store.get(session_id)
        assert result is None

    async def test_silently_succeeds_for_nonexistent(self, store: InMemorySessionStore) -> None:
        # Should not raise
        await store.invalidate("nonexistent-id")

    async def test_does_not_affect_other_sessions(
        self, store: InMemorySessionStore, token_set: TokenSet
    ) -> None:
        id1 = await store.create("user-1", token_set, ttl=3600)
        id2 = await store.create("user-2", token_set, ttl=3600)

        await store.invalidate(id1)

        assert await store.get(id1) is None
        assert await store.get(id2) is not None
