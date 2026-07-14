"""Ceramic Framework - Enterprise capabilities on top of FastMCP."""

from ceramic.server import CeramicFastMCP
from ceramic.identity import IdentityContext, identity, access_token
from ceramic.downstream import (
    authenticated_client,
    authenticated_async_client,
    authenticated_soap_client,
)
from ceramic.testing import CeramicTestClient

# Public alias: `from ceramic import FastMCP` is the drop-in replacement
FastMCP = CeramicFastMCP

__all__ = [
    "FastMCP",
    "CeramicFastMCP",
    "identity",
    "access_token",
    "IdentityContext",
    "CeramicTestClient",
    "authenticated_client",
    "authenticated_async_client",
    "authenticated_soap_client",
]
