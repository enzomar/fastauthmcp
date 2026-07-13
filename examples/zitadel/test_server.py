"""Tests for the Zitadel example server.

Demonstrates how to test authenticated tool flows without a live IDP
using CeramicTestClient.

Run with:
    pytest examples/zitadel/test_server.py -v
"""

import pytest

from ceramic.testing import CeramicTestClient
from server import mcp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client():
    """Client with admin + editor + viewer roles (superuser)."""
    return CeramicTestClient(
        app=mcp,
        email="admin@company.com",
        subject="zitadel-user-001",
        roles=["admin", "editor", "viewer"],
        groups=["platform-team"],
    )


@pytest.fixture
def editor_client():
    """Client with editor + viewer roles."""
    return CeramicTestClient(
        app=mcp,
        email="dev@company.com",
        subject="zitadel-user-002",
        roles=["editor", "viewer"],
        groups=["dev-team"],
    )


@pytest.fixture
def viewer_client():
    """Client with viewer role only."""
    return CeramicTestClient(
        app=mcp,
        email="readonly@company.com",
        subject="zitadel-user-003",
        roles=["viewer"],
        groups=[],
    )


@pytest.fixture
def unauthenticated_client():
    """Client with no roles — should be rejected from all protected tools."""
    return CeramicTestClient(
        app=mcp,
        email="nobody@company.com",
        subject="zitadel-user-004",
        roles=[],
        groups=[],
    )


# ---------------------------------------------------------------------------
# Tests: whoami (any authenticated user)
# ---------------------------------------------------------------------------


class TestWhoami:
    @pytest.mark.asyncio
    async def test_returns_user_info(self, admin_client):
        result = await admin_client.call_tool("whoami")
        CeramicTestClient.assert_authorized(result)
        assert result["email"] == "admin@company.com"
        assert "admin" in result["roles"]


# ---------------------------------------------------------------------------
# Tests: Viewer role
# ---------------------------------------------------------------------------


class TestViewerAccess:
    @pytest.mark.asyncio
    async def test_viewer_can_list_projects(self, viewer_client):
        result = await viewer_client.call_tool("get_projects")
        CeramicTestClient.assert_authorized(result)
        assert isinstance(result, list)
        assert len(result) >= 3

    @pytest.mark.asyncio
    async def test_viewer_can_get_project_details(self, viewer_client):
        result = await viewer_client.call_tool(
            "get_project_details", project_id="proj-001"
        )
        CeramicTestClient.assert_authorized(result)
        assert result["name"] == "MCP Gateway"

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_project(self, viewer_client):
        result = await viewer_client.call_tool(
            "create_project", name="Test", description="Should fail"
        )
        CeramicTestClient.assert_unauthorized(result)

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_project(self, viewer_client):
        result = await viewer_client.call_tool(
            "delete_project", project_id="proj-001"
        )
        CeramicTestClient.assert_unauthorized(result)


# ---------------------------------------------------------------------------
# Tests: Editor role
# ---------------------------------------------------------------------------


class TestEditorAccess:
    @pytest.mark.asyncio
    async def test_editor_can_create_project(self, editor_client):
        result = await editor_client.call_tool(
            "create_project", name="New Project", description="Created by editor"
        )
        CeramicTestClient.assert_authorized(result)
        assert "created" in result
        assert result["created"]["name"] == "New Project"

    @pytest.mark.asyncio
    async def test_editor_can_update_status(self, editor_client):
        result = await editor_client.call_tool(
            "update_project_status", project_id="proj-002", status="active"
        )
        CeramicTestClient.assert_authorized(result)
        assert result["updated"]["new_status"] == "active"

    @pytest.mark.asyncio
    async def test_editor_cannot_delete_project(self, editor_client):
        result = await editor_client.call_tool(
            "delete_project", project_id="proj-003"
        )
        CeramicTestClient.assert_unauthorized(result)

    @pytest.mark.asyncio
    async def test_editor_cannot_view_audit_log(self, editor_client):
        result = await editor_client.call_tool("get_audit_log")
        CeramicTestClient.assert_unauthorized(result)


# ---------------------------------------------------------------------------
# Tests: Admin role
# ---------------------------------------------------------------------------


class TestAdminAccess:
    @pytest.mark.asyncio
    async def test_admin_can_delete_project(self, admin_client):
        result = await admin_client.call_tool(
            "delete_project", project_id="proj-003"
        )
        CeramicTestClient.assert_authorized(result)
        assert result["deleted"]["name"] == "Auth Service Migration"

    @pytest.mark.asyncio
    async def test_admin_can_view_audit_log(self, admin_client):
        result = await admin_client.call_tool("get_audit_log", limit=10)
        CeramicTestClient.assert_authorized(result)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Tests: No roles
# ---------------------------------------------------------------------------


class TestUnauthenticatedAccess:
    @pytest.mark.asyncio
    async def test_no_roles_rejected_from_viewer_tools(self, unauthenticated_client):
        result = await unauthenticated_client.call_tool("get_projects")
        CeramicTestClient.assert_unauthorized(result)

    @pytest.mark.asyncio
    async def test_no_roles_rejected_from_editor_tools(self, unauthenticated_client):
        result = await unauthenticated_client.call_tool(
            "create_project", name="X", description="Y"
        )
        CeramicTestClient.assert_unauthorized(result)

    @pytest.mark.asyncio
    async def test_no_roles_rejected_from_admin_tools(self, unauthenticated_client):
        result = await unauthenticated_client.call_tool(
            "delete_project", project_id="proj-001"
        )
        CeramicTestClient.assert_unauthorized(result)
