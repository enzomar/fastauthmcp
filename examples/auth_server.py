"""Authenticated Ceramic server with role-based access control.

Requires a ceramic.yaml with an auth section configured.
See ceramic.yaml.example for reference.

Run with:
    ceramic run
"""

from ceramic import FastMCP, require_role, require_group, identity

mcp = FastMCP("auth-server")


@mcp.tool()
def whoami() -> dict:
    """Return info about the currently authenticated user."""
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": list(user.roles),
        "groups": list(user.groups),
    }


@mcp.tool()
@require_role("analyst")
def get_report(report_id: str) -> dict:
    """Fetch a report. Only accessible to users with the 'analyst' role."""
    user = identity()
    return {
        "report_id": report_id,
        "requested_by": user.email,
        "data": "...",
    }


@mcp.tool()
@require_group("ops-team")
def deploy(service: str, version: str) -> str:
    """Deploy a service. Only accessible to members of 'ops-team'."""
    user = identity()
    return f"{user.email} deployed {service}@{version}"


@mcp.tool()
@require_role("admin")
@require_group("platform")
def admin_action(action: str) -> str:
    """Admin-only action requiring both 'admin' role and 'platform' group."""
    return f"Executed: {action}"


if __name__ == "__main__":
    mcp.run()
