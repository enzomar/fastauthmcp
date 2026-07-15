"""Token exchange adapter system for provider-specific IDP integrations.

Each adapter lives in its own module and can evolve independently.
The AdapterRegistry maps provider identifiers to adapter instances.

Public API:
    TokenExchangeAdapter - Protocol for implementing new adapters
    AdapterRegistry - Registry and lookup for adapters
    RFC8693Adapter - Default RFC 8693 token exchange
    GoogleSTSAdapter - Google Cloud Security Token Service
    EntraOBOAdapter - Microsoft Entra ID On-Behalf-Of flow
"""

from fastauthmcp.auth.adapters.base import TokenExchangeAdapter
from fastauthmcp.auth.adapters.entra import EntraOBOAdapter
from fastauthmcp.auth.adapters.google import GoogleSTSAdapter
from fastauthmcp.auth.adapters.registry import AdapterRegistry
from fastauthmcp.auth.adapters.rfc8693 import RFC8693Adapter

__all__ = [
    "TokenExchangeAdapter",
    "AdapterRegistry",
    "RFC8693Adapter",
    "GoogleSTSAdapter",
    "EntraOBOAdapter",
]
