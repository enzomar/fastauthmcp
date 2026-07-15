"""Session storage backends for the FastAuthMCP framework."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from fastauthmcp.exceptions import SessionError
from fastauthmcp.models import Session, TokenSet


class SessionStore(Protocol):
    """Pluggable session storage backend."""

    async def create(self, subject: str, token_set: TokenSet, ttl: int) -> str:
        """Create a new session and return its ID."""
        ...

    async def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID, or None if not found or expired."""
        ...

    async def update(self, session_id: str, token_set: TokenSet) -> None:
        """Update the token set for an existing session."""
        ...

    async def invalidate(self, session_id: str) -> None:
        """Remove a session from storage."""
        ...


class InMemorySessionStore:
    """Default session store for single-process deployments.

    Stores sessions in a plain dict. Suitable for development and
    single-process production deployments where session persistence
    across restarts is not required.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    async def create(self, subject: str, token_set: TokenSet, ttl: int) -> str:
        """Create a new session and return its unique ID."""
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            subject=subject,
            token_set=token_set,
            created_at=datetime.now(timezone.utc),
            ttl=ttl,
        )
        self._sessions[session_id] = session
        return session_id

    async def get(self, session_id: str) -> Session | None:
        """Retrieve a session by ID.

        Returns None if the session does not exist or has exceeded its TTL.
        Expired sessions are automatically invalidated.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return None

        elapsed = (datetime.now(timezone.utc) - session.created_at).total_seconds()
        if elapsed > session.ttl:
            await self.invalidate(session_id)
            return None

        return session

    async def update(self, session_id: str, token_set: TokenSet) -> None:
        """Replace the token set on an existing session.

        Raises SessionError if the session does not exist.
        """
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionError(f"Session not found: {session_id}")
        session.token_set = token_set

    async def invalidate(self, session_id: str) -> None:
        """Remove a session from storage.

        Silently succeeds if the session does not exist.
        """
        self._sessions.pop(session_id, None)
