"""Multi-IdP support: route authentication to different providers per tool or tenant.

Allows a single FastAuthMCP server to trust tokens from multiple identity providers,
routing validation to the correct provider based on the token's issuer claim
or tool-level configuration.

Usage in fastauthmcp.yaml:

    auth:
      multi_idp:
        enabled: true
        providers:
          - id: corporate
            issuer: https://login.corporate.com
            client_id: fastauthmcp-corp
            audiences: ["fastauthmcp-corp"]
          - id: partner
            issuer: https://auth.partner.io
            client_id: fastauthmcp-partner
            audiences: ["fastauthmcp-partner", "api://fastauthmcp"]
        routing:
          strategy: issuer_claim   # issuer_claim | tool_mapping | header
          tool_mapping:
            internal_*: corporate
            partner_*: partner
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class IdPConfig:
    """Configuration for a single identity provider."""

    id: str
    issuer: str
    client_id: str
    audiences: list[str] = field(default_factory=list)
    jwks_uri: str | None = None
    scopes: list[str] = field(default_factory=lambda: ["openid"])


@dataclass
class MultiIdPConfig:
    """Multi-IdP routing configuration."""

    enabled: bool = False
    providers: list[IdPConfig] = field(default_factory=list)
    routing_strategy: str = "issuer_claim"  # issuer_claim | tool_mapping | header
    tool_mapping: dict[str, str] = field(default_factory=dict)  # pattern -> provider_id
    header_name: str = "x-idp-hint"  # For header-based routing


class IdPRouter:
    """Routes token validation to the correct identity provider.

    Supports three routing strategies:
    1. issuer_claim: Decode token, read 'iss' claim, match to provider
    2. tool_mapping: Map tool names (glob) to providers
    3. header: Use a request header to select the provider
    """

    def __init__(self, config: MultiIdPConfig) -> None:
        self._config = config
        self._providers: dict[str, IdPConfig] = {p.id: p for p in config.providers}
        self._issuer_index: dict[str, IdPConfig] = {
            p.issuer.rstrip("/"): p for p in config.providers
        }

    def resolve_provider(
        self,
        *,
        token: str | None = None,
        tool_name: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> IdPConfig | None:
        """Determine which IdP should validate this request.

        Args:
            token: The raw JWT (for issuer_claim strategy).
            tool_name: The tool being called (for tool_mapping strategy).
            headers: Request headers (for header strategy).

        Returns:
            The matched IdPConfig, or None if no match found.
        """
        strategy = self._config.routing_strategy

        if strategy == "issuer_claim" and token:
            return self._route_by_issuer(token)
        elif strategy == "tool_mapping" and tool_name:
            return self._route_by_tool(tool_name)
        elif strategy == "header" and headers:
            return self._route_by_header(headers)

        # Fallback: try issuer claim if token is available
        if token:
            return self._route_by_issuer(token)

        return None

    def get_provider(self, provider_id: str) -> IdPConfig | None:
        """Get a provider by ID."""
        return self._providers.get(provider_id)

    def _route_by_issuer(self, token: str) -> IdPConfig | None:
        """Extract issuer from token and match to provider."""
        import base64
        import json

        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload_b64 = parts[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            issuer = payload.get("iss", "").rstrip("/")
            return self._issuer_index.get(issuer)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _route_by_tool(self, tool_name: str) -> IdPConfig | None:
        """Match tool name against configured patterns."""
        import fnmatch

        for pattern, provider_id in self._config.tool_mapping.items():
            if fnmatch.fnmatch(tool_name, pattern):
                return self._providers.get(provider_id)
        return None

    def _route_by_header(self, headers: dict[str, str]) -> IdPConfig | None:
        """Use a header value to select the provider."""
        hint = headers.get(self._config.header_name)
        if hint:
            return self._providers.get(hint)
        return None
