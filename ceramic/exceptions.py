"""Exception hierarchy for the Ceramic framework."""

from __future__ import annotations


class CeramicError(Exception):
    """Base exception for all Ceramic errors."""


class ConfigurationError(CeramicError):
    """Invalid or missing configuration."""


class AuthenticationError(CeramicError):
    """Authentication flow failure."""


class AuthorizationError(CeramicError):
    """Insufficient permissions."""


class ProviderError(CeramicError):
    """Identity provider communication failure."""


class SessionError(CeramicError):
    """Session management failure."""


class PluginError(CeramicError):
    """Plugin loading or execution failure."""
