"""Core data models for the Ceramic framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class TokenSet:
    """OAuth2 token set returned from the identity provider."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    token_type: str = "Bearer"
    id_token: str | None = None


@dataclass
class Session:
    """User session record linking a subject to a token set."""

    session_id: str
    subject: str
    token_set: TokenSet
    created_at: datetime
    ttl: int  # seconds

    @property
    def is_expired(self) -> bool:
        """Return True if the session has exceeded its TTL."""
        return (datetime.utcnow() - self.created_at).total_seconds() > self.ttl


@dataclass
class OIDCEndpoints:
    """OIDC provider endpoints discovered from .well-known/openid-configuration."""

    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str | None
    jwks_uri: str


@dataclass
class LogEntry:
    """Structured log entry for observability."""

    timestamp: str  # ISO 8601
    request_id: str
    tool_name: str | None
    subject: str | None
    duration_ms: float | None
    status: Literal["success", "error", "unauthorized"]
    level: str
    message: str
    extra: dict[str, Any] = field(default_factory=dict)
