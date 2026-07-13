"""Zitadel + Ceramic example: Project Management API.

A simulated HTTP API with role-based access control using Zitadel as the
identity provider. Demonstrates authentication, authorization, identity
context access, and session management.

Setup:
    1. Configure Zitadel (see README.md)
    2. Copy ceramic.yaml.example to ceramic.yaml and fill in your details
    3. Run: ceramic login && ceramic run

Or directly:
    python server.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ceramic import FastMCP, identity, require_role

# ---------------------------------------------------------------------------
# Simulated database (in-memory)
# ---------------------------------------------------------------------------

_projects_db: dict[str, dict[str, Any]] = {
    "proj-001": {
        "id": "proj-001",
        "name": "MCP Gateway",
        "description": "Unified MCP gateway for all internal services",
        "status": "active",
        "owner": "alice@example.com",
        "created_at": "2024-11-15T10:30:00Z",
    },
    "proj-002": {
        "id": "proj-002",
        "name": "Data Pipeline v2",
        "description": "Real-time data pipeline with CDC support",
        "status": "planning",
        "owner": "bob@example.com",
        "created_at": "2024-12-01T08:00:00Z",
    },
    "proj-003": {
        "id": "proj-003",
        "name": "Auth Service Migration",
        "description": "Migrate legacy auth to Zitadel OIDC",
        "status": "completed",
        "owner": "alice@example.com",
        "created_at": "2024-10-20T14:00:00Z",
    },
}

_audit_log: list[dict[str, Any]] = []


def _audit(action: str, user: str, details: str) -> None:
    """Record an action in the audit log."""
    _audit_log.append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "user": user,
            "details": details,
        }
    )


# ---------------------------------------------------------------------------
# Ceramic MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP("project-api", config="ceramic.yaml")


# --- Public (any authenticated user) ---


@mcp.tool()
def whoami() -> dict[str, Any]:
    """Show the current authenticated user's identity and roles."""
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
    }


# --- Viewer role ---


@mcp.tool()
@require_role("viewer")
def get_projects() -> list[dict[str, Any]]:
    """List all projects. Requires 'viewer' role."""
    user = identity()
    _audit("list_projects", user.email or "unknown", "Listed all projects")
    return [
        {"id": p["id"], "name": p["name"], "status": p["status"]}
        for p in _projects_db.values()
    ]


@mcp.tool()
@require_role("viewer")
def get_project_details(project_id: str) -> dict[str, Any]:
    """Get full details of a specific project. Requires 'viewer' role.

    Args:
        project_id: The project ID (e.g., "proj-001")
    """
    user = identity()

    if project_id not in _projects_db:
        return {"error": "not_found", "message": f"Project {project_id} not found"}

    _audit(
        "view_project",
        user.email or "unknown",
        f"Viewed project {project_id}",
    )
    return _projects_db[project_id]


# --- Editor role ---


@mcp.tool()
@require_role("editor")
def create_project(name: str, description: str) -> dict[str, Any]:
    """Create a new project. Requires 'editor' role.

    Args:
        name: Project name
        description: Project description
    """
    user = identity()

    project_id = f"proj-{len(_projects_db) + 1:03d}"
    project = {
        "id": project_id,
        "name": name,
        "description": description,
        "status": "planning",
        "owner": user.email,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _projects_db[project_id] = project

    _audit(
        "create_project",
        user.email or "unknown",
        f"Created project {project_id}: {name}",
    )
    return {"created": project}


@mcp.tool()
@require_role("editor")
def update_project_status(project_id: str, status: str) -> dict[str, Any]:
    """Update a project's status. Requires 'editor' role.

    Args:
        project_id: The project ID
        status: New status (planning, active, paused, completed, archived)
    """
    user = identity()
    valid_statuses = {"planning", "active", "paused", "completed", "archived"}

    if project_id not in _projects_db:
        return {"error": "not_found", "message": f"Project {project_id} not found"}

    if status not in valid_statuses:
        return {
            "error": "invalid_status",
            "message": f"Status must be one of: {', '.join(sorted(valid_statuses))}",
        }

    old_status = _projects_db[project_id]["status"]
    _projects_db[project_id]["status"] = status

    _audit(
        "update_status",
        user.email or "unknown",
        f"Project {project_id}: {old_status} → {status}",
    )
    return {
        "updated": {"id": project_id, "old_status": old_status, "new_status": status}
    }


# --- Admin role ---


@mcp.tool()
@require_role("admin")
def delete_project(project_id: str) -> dict[str, Any]:
    """Delete a project permanently. Requires 'admin' role.

    Args:
        project_id: The project ID to delete
    """
    user = identity()

    if project_id not in _projects_db:
        return {"error": "not_found", "message": f"Project {project_id} not found"}

    deleted = _projects_db.pop(project_id)

    _audit(
        "delete_project",
        user.email or "unknown",
        f"Deleted project {project_id}: {deleted['name']}",
    )
    return {"deleted": {"id": project_id, "name": deleted["name"]}}


@mcp.tool()
@require_role("admin")
def get_audit_log(limit: int = 20) -> list[dict[str, Any]]:
    """View the audit trail. Requires 'admin' role.

    Args:
        limit: Maximum number of entries to return (default: 20)
    """
    user = identity()
    _audit("view_audit_log", user.email or "unknown", f"Viewed last {limit} entries")
    return _audit_log[-limit:]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os

    transport = os.environ.get("CERAMIC_TRANSPORT", "stdio")
    host = os.environ.get("CERAMIC_HOST", "localhost")
    port = int(os.environ.get("CERAMIC_PORT", "8000"))
    mcp.run(transport=transport, host=host, port=port)
