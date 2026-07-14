"""Authenticated Ceramic server with identity access.

Requires a ceramic.yaml with an auth section configured.
See ceramic.yaml.example for reference.

Run with:
    ceramic run
"""

from ceramic import FastMCP, identity

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
def get_report(report_id: str) -> dict:
    """Fetch a report. Requires authentication."""
    user = identity()
    return {
        "report_id": report_id,
        "requested_by": user.email,
        "data": "...",
    }


@mcp.tool()
def deploy(service: str, version: str) -> str:
    """Deploy a service. Requires authentication."""
    user = identity()
    return f"{user.email} deployed {service}@{version}"


if __name__ == "__main__":
    mcp.run()
