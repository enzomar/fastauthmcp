"""TokenExchangeAdapter protocol definition."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from fastauthmcp.config import AuthConfig
from fastauthmcp.models import OIDCEndpoints, TokenSet


@runtime_checkable
class TokenExchangeAdapter(Protocol):
    """Protocol for provider-specific token exchange implementations.

    Each adapter translates FastAuthMCP's internal exchange request into the
    wire format required by a particular IDP, and normalizes the response
    back into a standard TokenSet.
    """

    @property
    def provider_id(self) -> str:
        """Unique identifier for this adapter (e.g. 'rfc8693', 'google', 'entra')."""
        ...

    async def exchange(
        self,
        subject_token: str,
        config: AuthConfig,
        endpoints: OIDCEndpoints,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange a subject token for a downstream TokenSet.

        Args:
            subject_token: The incoming user token to exchange.
            config: Auth configuration with client credentials and exchange settings.
            endpoints: Discovered OIDC endpoints for the provider.
            audience: Target audience for the exchanged token (overrides config).
            scope: Scopes to request on the exchanged token (overrides config).

        Returns:
            A TokenSet containing the exchanged downstream access token.

        Raises:
            ProviderError: If the IDP rejects the exchange or is unreachable.
            AuthenticationError: If required configuration is missing.
        """
        ...
