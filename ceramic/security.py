"""Security utilities for the Ceramic framework."""

from __future__ import annotations

import ssl
from typing import Any, ClassVar
from urllib.parse import urlparse

from ceramic.exceptions import ConfigurationError


class LogRedactor:
    """Scans and redacts sensitive fields from log output.

    Recursively scans dictionary keys for sensitive patterns and replaces
    matching values with '[REDACTED]'.
    """

    SENSITIVE_PATTERNS: ClassVar[set[str]] = {
        "token",
        "secret",
        "credential",
        "password",
        "authorization",
    }

    REDACTED: ClassVar[str] = "[REDACTED]"

    def redact(self, record: dict[str, Any]) -> dict[str, Any]:
        """Return a new dict with sensitive field values replaced.

        Args:
            record: The log record or span attributes dict to redact.

        Returns:
            A new dict with sensitive values replaced by '[REDACTED]'.
            The original dict is not modified.
        """
        return self._redact_dict(record)

    def _redact_dict(self, d: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact a dictionary."""
        result: dict[str, Any] = {}
        for key, value in d.items():
            if self._is_sensitive(key):
                result[key] = self.REDACTED
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value)
            else:
                result[key] = value
        return result

    def _is_sensitive(self, field_name: str) -> bool:
        """Check if a field name contains any sensitive pattern (case-insensitive)."""
        lower_name = field_name.lower()
        return any(pattern in lower_name for pattern in self.SENSITIVE_PATTERNS)


class TLSEnforcer:
    """Validates that all configured endpoints use HTTPS and TLS >= 1.2."""

    def validate_url(self, url: str) -> None:
        """Validate that the given URL uses the HTTPS scheme.

        Args:
            url: The URL string to validate.

        Raises:
            ConfigurationError: If the URL does not use the HTTPS scheme.
        """
        parsed = urlparse(url)
        if parsed.scheme.lower() != "https":
            raise ConfigurationError(
                f"Non-TLS endpoint detected: {url!r} uses scheme {parsed.scheme!r} instead of 'https'"
            )

    def get_ssl_context(self) -> ssl.SSLContext:
        """Create and return an SSLContext enforcing TLS 1.2 minimum.

        Returns:
            An ssl.SSLContext configured with TLS_CLIENT protocol and
            minimum version set to TLS 1.2.
        """
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        return context
