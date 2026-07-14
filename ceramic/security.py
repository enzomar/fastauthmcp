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

        Uses certifi's CA bundle for certificate verification, which provides
        a reliable set of root certificates across all platforms.

        Returns:
            An ssl.SSLContext configured with TLS_CLIENT protocol and
            minimum version set to TLS 1.2.
        """
        import certifi

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_verify_locations(certifi.where())
        return context

    def get_mtls_ssl_context(
        self,
        client_cert: str,
        client_key: str | None = None,
        ca_bundle: str | None = None,
    ) -> ssl.SSLContext:
        """Create an SSLContext with mutual TLS (client certificate authentication).

        Loads the client certificate (and optionally a separate private key)
        for mTLS communication with the identity provider. Enforces TLS 1.2+.

        Args:
            client_cert: Path to the PEM-encoded client certificate file.
            client_key: Path to the PEM-encoded client private key file.
                If None, the key is expected to be bundled in client_cert.
            ca_bundle: Path to a custom CA bundle (PEM) for server cert
                verification. If None, uses the system/certifi CA bundle.

        Returns:
            An ssl.SSLContext configured for mTLS with TLS 1.2 minimum.

        Raises:
            ConfigurationError: If the certificate/key files cannot be loaded.
        """
        import os

        import certifi

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_2

        # Load CA bundle for verifying the IDP's server certificate
        ca_path = ca_bundle or certifi.where()
        if not os.path.isfile(ca_path):
            raise ConfigurationError(f"CA bundle not found at: {ca_path!r}")
        context.load_verify_locations(ca_path)

        # Load client certificate + key for mTLS
        if not os.path.isfile(client_cert):
            raise ConfigurationError(
                f"mTLS client certificate not found at: {client_cert!r}"
            )
        if client_key and not os.path.isfile(client_key):
            raise ConfigurationError(f"mTLS client key not found at: {client_key!r}")

        try:
            context.load_cert_chain(
                certfile=client_cert,
                keyfile=client_key,
            )
        except ssl.SSLError as exc:
            raise ConfigurationError(
                f"Failed to load mTLS client certificate/key: {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigurationError(
                f"Failed to read mTLS certificate files: {exc}"
            ) from exc

        return context
