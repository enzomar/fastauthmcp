"""FastAuthMCP Framework - Enterprise capabilities on top of FastMCP."""

from fastauthmcp.server import FastAuthMCP
from fastauthmcp.identity import IdentityContext, identity, access_token
from fastauthmcp.downstream import (
    authenticated_client,
    authenticated_async_client,
    authenticated_soap_client,
)
from fastauthmcp.authorization import (
    require_roles,
    require_groups,
    require_scopes,
    require_role,
    require_group,
)
from fastauthmcp.context import get_context, set_context, request_context
from fastauthmcp.testing import FastAuthMCPTestClient

# Public alias: `from fastauthmcp import FastMCP` is the drop-in replacement
FastMCP = FastAuthMCP

__all__ = [
    "FastMCP",
    "FastAuthMCP",
    "identity",
    "access_token",
    "IdentityContext",
    "FastAuthMCPTestClient",
    "authenticated_client",
    "authenticated_async_client",
    "authenticated_soap_client",
    # Authorization decorators
    "require_roles",
    "require_groups",
    "require_scopes",
    "require_role",
    "require_group",
    # Request context propagation
    "get_context",
    "set_context",
    "request_context",
]
