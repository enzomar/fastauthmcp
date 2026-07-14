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

from ceramic.auth.adapters.base import TokenExchangeAdapter
from ceramic.auth.adapters.entra import EntraOBOAdapter
from ceramic.auth.adapters.google import GoogleSTSAdapter
from ceramic.auth.adapters.registry import AdapterRegistry
from ceramic.auth.adapters.rfc8693 import RFC8693Adapter

__all__ = [
    "TokenExchangeAdapter",
    "AdapterRegistry",
    "RFC8693Adapter",
    "GoogleSTSAdapter",
    "EntraOBOAdapter",
]
