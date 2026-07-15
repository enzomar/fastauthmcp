"""Tests for the fastauthmcp package public API exports."""

from fastauthmcp.server import FastAuthMCP


def test_fastmcp_import():
    """from fastauthmcp import FastMCP works and is FastAuthMCP."""
    from fastauthmcp import FastMCP

    assert FastMCP is FastAuthMCP


def test_identity_import():
    """from fastauthmcp import identity works."""
    from fastauthmcp import identity

    assert callable(identity)


def test_identity_context_import():
    """from fastauthmcp import IdentityContext works."""
    from fastauthmcp import IdentityContext
    from fastauthmcp.identity import IdentityContext as DirectIdentityContext

    assert IdentityContext is DirectIdentityContext


def test_fastauthmcp_test_client_import():
    """from fastauthmcp import FastAuthMCPTestClient works."""
    from fastauthmcp import FastAuthMCPTestClient
    from fastauthmcp.testing import FastAuthMCPTestClient as DirectFastAuthMCPTestClient

    assert FastAuthMCPTestClient is DirectFastAuthMCPTestClient


def test_all_exports_present():
    """__all__ contains all expected public names."""
    import fastauthmcp

    expected = {
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
    }
    assert expected == set(fastauthmcp.__all__)
