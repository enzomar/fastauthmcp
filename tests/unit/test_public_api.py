"""Tests for the ceramic package public API exports."""

from ceramic.server import CeramicFastMCP


def test_fastmcp_import():
    """from ceramic import FastMCP works and is CeramicFastMCP."""
    from ceramic import FastMCP

    assert FastMCP is CeramicFastMCP


def test_identity_import():
    """from ceramic import identity works."""
    from ceramic import identity

    assert callable(identity)


def test_identity_context_import():
    """from ceramic import IdentityContext works."""
    from ceramic import IdentityContext
    from ceramic.identity import IdentityContext as DirectIdentityContext

    assert IdentityContext is DirectIdentityContext


def test_ceramic_test_client_import():
    """from ceramic import CeramicTestClient works."""
    from ceramic import CeramicTestClient
    from ceramic.testing import CeramicTestClient as DirectCeramicTestClient

    assert CeramicTestClient is DirectCeramicTestClient


def test_all_exports_present():
    """__all__ contains all expected public names."""
    import ceramic

    expected = {
        "FastMCP",
        "CeramicFastMCP",
        "identity",
        "access_token",
        "IdentityContext",
        "CeramicTestClient",
        "authenticated_client",
        "authenticated_async_client",
        "authenticated_soap_client",
    }
    assert expected == set(ceramic.__all__)
