"""Ceramic Framework - Enterprise capabilities on top of FastMCP."""

from ceramic.server import CeramicFastMCP
from ceramic.authorization import require_role, require_group
from ceramic.identity import IdentityContext, identity
from ceramic.testing import CeramicTestClient

# Public alias: `from ceramic import FastMCP` is the drop-in replacement
FastMCP = CeramicFastMCP

__all__ = [
    "FastMCP",
    "CeramicFastMCP",
    "require_role",
    "require_group",
    "identity",
    "IdentityContext",
    "CeramicTestClient",
]
