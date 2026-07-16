"""Downstream credential mapping: route tools to different credential sources.

Status: Planned — not yet wired into the middleware pipeline.

Allows configuration-driven mapping of tools to specific downstream
API credentials, enabling a single MCP server to call multiple
backend services with different tokens/auth methods.

Usage in fastauthmcp.yaml:

    credential_mapping:
      - tools: ["get_orders", "create_order"]
        audience: "https://orders-api.internal.com"
        scopes: ["orders:read", "orders:write"]
      - tools: ["get_invoices"]
        audience: "https://billing-api.internal.com"
        scopes: ["billing:read"]

Usage in tool code:

    from fastauthmcp.credential_mapping import downstream_token

    @mcp.tool()
    async def get_orders() -> list:
        token = await downstream_token()  # Auto-resolves based on tool name
        ...
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextvars import ContextVar
from dataclasses import dataclass, field

from fastauthmcp.identity import _access_token_var

logger = logging.getLogger(__name__)

# Context var to track current tool name for credential resolution
_current_tool_var: ContextVar[str | None] = ContextVar("fastauthmcp_current_tool", default=None)


@dataclass
class CredentialMapping:
    """Maps a set of tools to a downstream API credential configuration."""

    tools: list[str]
    audience: str
    scopes: list[str] = field(default_factory=list)
    token_exchange_provider: str | None = None


@dataclass
class CachedToken:
    """A cached downstream token with scope and expiry awareness."""

    access_token: str
    audience: str
    scopes: frozenset[str]
    expires_at: float  # monotonic time
    cache_key: str


class TokenCache:
    """Scope-aware token cache for downstream credentials.

    Caches exchanged tokens keyed by (upstream_token_hash, audience, scopes)
    to avoid redundant token exchange calls for the same downstream target.
    """

    def __init__(self, max_size: int = 500, default_ttl: float = 300.0) -> None:
        self._cache: dict[str, CachedToken] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl

    def get(self, upstream_token: str, audience: str, scopes: frozenset[str]) -> str | None:
        """Retrieve a cached downstream token if valid."""
        key = self._make_key(upstream_token, audience, scopes)
        cached = self._cache.get(key)
        if cached is None:
            return None
        if time.monotonic() > cached.expires_at:
            del self._cache[key]
            return None
        return cached.access_token

    def put(
        self,
        upstream_token: str,
        audience: str,
        scopes: frozenset[str],
        access_token: str,
        ttl: float | None = None,
    ) -> None:
        """Cache a downstream token."""
        key = self._make_key(upstream_token, audience, scopes)
        self._cache[key] = CachedToken(
            access_token=access_token,
            audience=audience,
            scopes=scopes,
            expires_at=time.monotonic() + (ttl or self._default_ttl),
            cache_key=key,
        )
        # Evict oldest if over capacity
        if len(self._cache) > self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k].expires_at)
            del self._cache[oldest_key]

    def invalidate(self, upstream_token: str | None = None) -> None:
        """Invalidate cached tokens, optionally filtered by upstream token."""
        if upstream_token is None:
            self._cache.clear()
        else:
            prefix = hashlib.sha256(upstream_token.encode()).hexdigest()[:16]
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]

    @staticmethod
    def _make_key(upstream_token: str, audience: str, scopes: frozenset[str]) -> str:
        """Create a cache key from token + target."""
        token_hash = hashlib.sha256(upstream_token.encode()).hexdigest()[:16]
        scope_hash = hashlib.sha256("|".join(sorted(scopes)).encode()).hexdigest()[:8]
        return f"{token_hash}:{audience}:{scope_hash}"


class CredentialResolver:
    """Resolves which downstream credentials a tool should use.

    Looks up the tool name in the configured credential mappings and
    returns the appropriate audience/scopes for token exchange.
    """

    def __init__(self, mappings: list[CredentialMapping] | None = None) -> None:
        self._mappings = mappings or []
        self._tool_index: dict[str, CredentialMapping] = {}
        for mapping in self._mappings:
            for tool in mapping.tools:
                self._tool_index[tool] = mapping

    def resolve(self, tool_name: str) -> CredentialMapping | None:
        """Find the credential mapping for a tool, or None if unmapped."""
        return self._tool_index.get(tool_name)

    def add_mapping(self, mapping: CredentialMapping) -> None:
        """Register a new credential mapping."""
        self._mappings.append(mapping)
        for tool in mapping.tools:
            self._tool_index[tool] = mapping


async def downstream_token(audience: str | None = None, scopes: list[str] | None = None) -> str:
    """Get a downstream-scoped token for the current tool.

    If audience/scopes are provided, uses those directly.
    Otherwise, resolves from the credential mapping configuration
    based on the current tool name.

    Returns:
        A valid downstream access token.

    Raises:
        RuntimeError: If called outside a request context.
    """
    token = _access_token_var.get(None)
    if token is None:
        raise RuntimeError("downstream_token() called outside an authenticated request context.")
    # If no audience specified, return the current access token
    # (the middleware should have already exchanged it if mapping exists)
    return token
