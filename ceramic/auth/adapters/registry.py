"""Adapter registry for token exchange provider selection."""

from __future__ import annotations

from ceramic.auth.adapters.base import TokenExchangeAdapter
from ceramic.auth.adapters.entra import EntraOBOAdapter
from ceramic.auth.adapters.google import GoogleSTSAdapter
from ceramic.auth.adapters.rfc8693 import RFC8693Adapter
from ceramic.exceptions import ConfigurationError
from ceramic.resilience import ResilientHttpClient


class AdapterRegistry:
    """Registry mapping provider identifiers to adapter instances.

    Manages built-in and custom token exchange adapters. The default
    adapter (RFC 8693) is returned when no provider is specified.
    """

    def __init__(self, http_client: ResilientHttpClient) -> None:
        self._adapters: dict[str, TokenExchangeAdapter] = {}
        self._http_client = http_client
        # Register built-in adapters
        self.register(RFC8693Adapter(http_client))
        self.register(GoogleSTSAdapter(http_client))
        self.register(EntraOBOAdapter(http_client))

    def register(self, adapter: TokenExchangeAdapter) -> None:
        """Register an adapter, keyed by its provider_id."""
        self._adapters[adapter.provider_id] = adapter

    def get_adapter(self, provider_id: str | None) -> TokenExchangeAdapter:
        """Get an adapter by provider identifier.

        Returns the RFC 8693 adapter if provider_id is None (default behavior).
        Raises ConfigurationError if the provider_id is not recognized.
        """
        if provider_id is None:
            return self._adapters["rfc8693"]
        if provider_id not in self._adapters:
            raise ConfigurationError(
                f"Unknown token exchange provider: '{provider_id}'. "
                f"Available: {sorted(self._adapters.keys())}"
            )
        return self._adapters[provider_id]
