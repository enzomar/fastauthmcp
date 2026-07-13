"""Tests for the ceramic package public API exports."""

from ceramic.server import CeramicFastMCP


def test_fastmcp_import():
    """from ceramic import FastMCP works and is CeramicFastMCP."""
    from ceramic import FastMCP

    assert FastMCP is CeramicFastMCP


def test_authorization_imports():
    """from ceramic import require_role, require_group works."""
    from ceramic import require_role, require_group

    assert callable(require_role)
    assert callable(require_group)


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
        "require_role",
        "require_group",
        "identity",
        "IdentityContext",
        "CeramicTestClient",
    }
    assert expected == set(ceramic.__all__)
