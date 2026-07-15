"""Secret management integration for FastAuthMCP.

Provides a unified interface for resolving secrets from various backends
(environment variables, AWS Secrets Manager, HashiCorp Vault, etc.)
used in fastauthmcp.yaml configuration values.

Secrets are referenced in config with the syntax:
    ${SECRET:backend:key}

Examples:
    client_secret: ${SECRET:env:FASTAUTHMCP_CLIENT_SECRET}
    client_secret: ${SECRET:aws:prod/fastauthmcp/client-secret}
    client_secret: ${SECRET:vault:secret/data/fastauthmcp#client_secret}

Usage in fastauthmcp.yaml:

    secrets:
      backend: env          # env | aws | vault
      cache_ttl: 300        # Cache resolved secrets for 5 minutes
      aws_region: us-east-1 # For AWS Secrets Manager
      vault_addr: https://vault.internal.com
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any, Protocol

logger = logging.getLogger(__name__)

# Pattern to match secret references: ${SECRET:backend:key}
_SECRET_PATTERN = re.compile(r"\$\{SECRET:([a-zA-Z0-9_]+):([^}]+)\}")


class SecretBackend(Protocol):
    """Protocol for secret resolution backends."""

    def resolve(self, key: str) -> str | None:
        """Resolve a secret by key. Returns None if not found."""
        ...


class EnvSecretBackend:
    """Resolve secrets from environment variables."""

    def resolve(self, key: str) -> str | None:
        return os.environ.get(key)


class SecretResolver:
    """Resolves secret references in configuration values.

    Supports pluggable backends and caches resolved values to avoid
    repeated lookups within the cache TTL.
    """

    def __init__(self, cache_ttl: float = 300.0) -> None:
        self._backends: dict[str, SecretBackend] = {
            "env": EnvSecretBackend(),
        }
        self._cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl = cache_ttl

    def register_backend(self, name: str, backend: SecretBackend) -> None:
        """Register a custom secret backend."""
        self._backends[name] = backend

    def resolve_value(self, value: str) -> str:
        """Resolve all secret references in a string value.

        Replaces ${SECRET:backend:key} patterns with resolved values.
        Raises ValueError if a secret cannot be resolved.
        """
        if not isinstance(value, str):
            return value

        def _replace(match: re.Match) -> str:
            backend_name = match.group(1)
            key = match.group(2)
            resolved = self._resolve_single(backend_name, key)
            if resolved is None:
                raise ValueError(
                    f"Secret not found: backend='{backend_name}', key='{key}'"
                )
            return resolved

        return _SECRET_PATTERN.sub(_replace, value)

    def resolve_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve all secret references in a config dict."""
        resolved: dict[str, Any] = {}
        for key, value in config.items():
            if isinstance(value, str):
                resolved[key] = self.resolve_value(value)
            elif isinstance(value, dict):
                resolved[key] = self.resolve_config(value)
            elif isinstance(value, list):
                resolved[key] = [
                    self.resolve_value(v) if isinstance(v, str) else v for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _resolve_single(self, backend_name: str, key: str) -> str | None:
        """Resolve a single secret, checking cache first."""
        cache_key = f"{backend_name}:{key}"

        # Check cache
        cached = self._cache.get(cache_key)
        if cached is not None:
            cached_value, cached_at = cached
            if time.monotonic() - cached_at < self._cache_ttl:
                return cached_value
            del self._cache[cache_key]

        # Resolve
        backend = self._backends.get(backend_name)
        if backend is None:
            logger.error("Unknown secret backend: '%s'", backend_name)
            return None

        resolved = backend.resolve(key)
        if resolved is not None:
            self._cache[cache_key] = (resolved, time.monotonic())

        return resolved
