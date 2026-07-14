"""Session middleware for the Ceramic framework.

Restores sessions on incoming requests and creates/updates sessions
after successful authentication or token refresh.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from ceramic.config import SessionsConfig
from ceramic.identity import IdentityContext, _identity_context_var
from ceramic.auth.claims import build_identity_context, parse_jwt_claims
from ceramic.middleware.pipeline import RequestContext
from ceramic.sessions import InMemorySessionStore

logger = logging.getLogger(__name__)


class SessionMiddleware:
    """Middleware that manages user sessions across requests.

    On before_request:
    - If a valid session_id is present in ctx.metadata, restore the
      IdentityContext from the stored session (short-circuiting re-auth).
    - If the session_id is invalid or expired, treat as unauthenticated.

    After next() returns:
    - If auth succeeded (ctx.identity populated) and no session existed,
      create a new session record.
    - If a token refresh occurred (token_set updated in metadata),
      update the existing session with the new token set.
    """

    def __init__(self, session_config: SessionsConfig) -> None:
        self.config = session_config
        self.store = InMemorySessionStore()
        self.ttl = session_config.ttl

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        session_id = ctx.metadata.get("session_id")
        had_session = False

        if session_id:
            # Attempt to restore session
            session = await self.store.get(session_id)
            if session is not None:
                # Valid session found — restore identity without re-auth
                had_session = True
                identity = self._restore_identity(session.token_set.access_token)
                if identity is not None:
                    ctx.identity = identity
                    _identity_context_var.set(identity)
                    ctx.session = session
                    # Store pre-existing token_set in metadata for refresh detection
                    ctx.metadata["token_set"] = session.token_set
                else:
                    # Could not parse identity from stored token — treat as invalid
                    await self.store.invalidate(session_id)
                    ctx.metadata.pop("session_id", None)
                    had_session = False
            else:
                # Session not found or expired — treat as unauthenticated
                ctx.metadata.pop("session_id", None)

        # Call downstream middleware (including AuthN if needed)
        response = await next()

        # After-logic: create or update session based on auth outcome
        await self._post_request(ctx, session_id, had_session)

        return response

    async def _post_request(
        self,
        ctx: RequestContext,
        original_session_id: str | None,
        had_session: bool,
    ) -> None:
        """Handle session creation/update after downstream processing."""
        # If authentication succeeded and no valid session existed, create one
        if ctx.identity is not None and not had_session:
            token_set = ctx.metadata.get("token_set")
            if token_set is not None:
                subject = ctx.identity.subject or ""
                new_session_id = await self.store.create(
                    subject=subject,
                    token_set=token_set,
                    ttl=self.ttl,
                )
                ctx.metadata["session_id"] = new_session_id
                logger.debug(
                    "Created new session %s for subject %s",
                    new_session_id,
                    subject,
                )
        elif ctx.identity is not None and had_session and original_session_id:
            # Check if token was refreshed (new token_set differs from stored)
            current_token_set = ctx.metadata.get("token_set")
            session = await self.store.get(original_session_id)
            if (
                session is not None
                and current_token_set is not None
                and current_token_set is not session.token_set
            ):
                await self.store.update(original_session_id, current_token_set)
                logger.debug(
                    "Updated session %s with refreshed token set",
                    original_session_id,
                )

    def _restore_identity(self, access_token: str) -> IdentityContext | None:
        """Build an IdentityContext from a stored access token.

        Returns None if the token cannot be parsed.
        """
        try:
            claims = parse_jwt_claims(access_token)
            return build_identity_context(claims)
        except (ValueError, Exception):
            logger.warning("Failed to parse identity from stored session token")
            return None
