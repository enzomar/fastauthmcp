"""Ceramic Framework - Enterprise capabilities on top of FastMCP."""

from ceramic.server import CeramicFastMCP as FastMCP
from ceramic.authorization import require_role, require_group
from ceramic.identity import identity

__all__ = [
    "FastMCP",
    "require_role",
    "require_group",
    "identity",
]
