"""Exception hierarchy for the FastAuthMCP framework."""

from __future__ import annotations


class FastAuthMCPError(Exception):
    """Base exception for all FastAuthMCP errors."""


class ConfigurationError(FastAuthMCPError):
    """Invalid or missing configuration."""


class AuthenticationError(FastAuthMCPError):
    """Authentication flow failure."""


class AuthorizationError(FastAuthMCPError):
    """Authorization policy evaluation failure."""


class ProviderError(FastAuthMCPError):
    """Identity provider communication failure."""


class SessionError(FastAuthMCPError):
    """Session management failure."""


class PluginError(FastAuthMCPError):
    """Plugin loading or execution failure."""
